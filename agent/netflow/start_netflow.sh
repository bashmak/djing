#!/usr/bin/env bash

PATH=/bin:/usr/local/sbin:/usr/local/bin:/usr/bin

if ! [[ -n "$1" ]]; then
    echo 'Missing port parameter'
    exit
fi

port=$1
DIRECTORY=`dirname $(readlink -e "$0")`

tdir="/tmp/djing_flow/${port}"
if [[ -d "${tdir}" ]]; then
    echo "Warning: directory '${tdir}' exists, clean all"
    rm -f ${tdir}/ft*
else
    mkdir -p "${tdir}"
fi


flow-capture -R ${DIRECTORY}/netflow_handler.sh -p /run/flow.pid -w ${tdir} -n1 -N0 0/0/${port}
