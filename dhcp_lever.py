#!/usr/bin/env python3
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from hashlib import sha256

API_AUTH_SECRET = 'yourapikey'
SERVER_DOMAIN = 'http://localhost:8000'


def die(text):
    print(text)
    exit(1)


'''
obj = {
    'client_ip': ip_address('127.0.0.1'),
    'client_mac': 'aa:bb:cc:dd:ee:ff',
    'switch_mac': 'aa:bb:cc:dd:ee:ff',
    'switch_port': 3,
    'cmd': 'commit'
}
'''


def calc_hash(data):
    if type(data) is str:
        result_data = data.encode('utf-8')
    else:
        result_data = bytes(data)
    return sha256(result_data).hexdigest()


def make_sign(data: dict):
    vars_to_hash = [str(v) for v in data.values()]
    vars_to_hash.sort()
    vars_to_hash.append(API_AUTH_SECRET)
    return calc_hash('_'.join(vars_to_hash))


def send_to(data, server=SERVER_DOMAIN):
    sign = make_sign(data)
    data.update({'sign': sign})
    try:
        with urlopen("%s/abons/api/dhcp_lever/?%s" % (server, urlencode(data))) as r:
            html = r.read()
        print(html)
    except ConnectionRefusedError:
        print('ERROR: connection refused')
    except HTTPError as e:
        print('ERROR:', e)


if __name__ == "__main__":
    argv = sys.argv
    if len(argv) < 3:
        die(
            'Too few arguments, exiting...\n'
            'Usage:\n'
            'COMMIT: ./dhcp_lever.py commit 192.168.1.100 ff:12:c5:9f:12:56 98:45:28:85:25:1a 3\n'
            'EXPIRY or RELEASE: ./dhcp_lever.py [release |commit]'
        )
    if API_AUTH_SECRET == 'your api key':
        raise NotImplementedError('You must specified secret api key')

    action = argv[1]
    if action == 'commit':
        if len(argv) < 6:
            die('Too few arguments, exiting...')
        dat = {
            'client_ip': argv[2],
            'client_mac': argv[3],
            'switch_mac': argv[4],
            'switch_port': int(argv[5]),
            'cmd': 'commit'
        }
        send_to(dat)
    elif action == 'expiry' or action == 'release':
        dat = {
            'client_ip': argv[2],
            'cmd': action
        }
        send_to(dat)
