"""
The interfaces to call system-level APIs of the target device.
Can reuse many from the droidbot library.
"""

from mobileclaw.device.phone import WebsocketController
from mobileclaw.device.browser import BrowserDeviceController
from mobileclaw.device.computer import get_computer_device
from mobileclaw.device.device_manager import DeviceManager
