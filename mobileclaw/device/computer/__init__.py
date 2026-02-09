from .base import ComputerDeviceBase
from .windows_device import WindowsComputerDevice
from .mac_device import MacComputerDevice

import sys

def get_computer_device(agent) -> ComputerDeviceBase:
    if sys.platform.startswith("win"):
        return WindowsComputerDevice(agent)
    elif sys.platform == "darwin":
        return MacComputerDevice(agent)
    else:
        raise NotImplementedError("Unsupported platform for ComputerDevice") 