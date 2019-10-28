from netaddr import EUI, mac_unix
from netaddr.core import AddrFormatError
from netfields.fields import MACAddressField
from django.core.exceptions import ValidationError


class MACAddressFieldUnixDialect(MACAddressField):

    def to_python(self, value):
        if not value:
            return value

        try:
            return EUI(value, dialect=mac_unix)
        except AddrFormatError as e:
            raise ValidationError(e)
