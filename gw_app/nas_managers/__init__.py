from gw_app.nas_managers.mod_mikrotik import MikrotikTransmitter
from gw_app.nas_managers.core import NasNetworkError, NasFailedResult
from gw_app.nas_managers.structs import SubnetQueue

# Указываем какие реализации шлюзов у нас есть, это будет использоваться в
# web интерфейсе
NAS_TYPES = (
    # ('mktk', MikrotikTransmitter),
    (0, MikrotikTransmitter),
)
