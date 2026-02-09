from mobileclaw.device.device_base import DeviceControllerBase
from typing import Tuple, Optional
import requests

class ComputerDeviceBase(DeviceControllerBase):  # type: ignore
    def __init__(self, agent, device_name: str, device_id: str):
        super().__init__(agent, device_name, device_id)
        self.device_bound = (0, 0, 0, 0)

    def __str__(self) -> str:
        return f"Computer Device: {self.device_name}"

    def _open_device(self):
        width, height = self.get_width_height()
        self.device_bound = (0, 0, width, height)
        self.width, self.height = width, height

    def show_execution_overlay(self) -> bool:
        try:
            flask_port = getattr(self.agent.config, 'flask_port', None) or self.agent.config.get('flask_port')
            requests.post(f"http://localhost:{flask_port}/overlay/show", timeout=1)
            return True
        except Exception:
            return False

    def hide_execution_overlay(self) -> bool:
        try:
            flask_port = getattr(self.agent.config, 'flask_port', None) or self.agent.config.get('flask_port')
            requests.post(f"http://localhost:{flask_port}/overlay/hide", timeout=1)
            return True
        except Exception:
            return False

    def overlay_clickthrough(self, enable: bool) -> bool:
        try:
            flask_port = getattr(self.agent.config, 'flask_port', None) or self.agent.config.get('flask_port')
            requests.post(f"http://localhost:{flask_port}/overlay/clickthrough", json={"enable": bool(enable)}, timeout=1)
            return True
        except Exception:
            return False

    def overlay_clickthrough_on(self) -> bool:
        return self.overlay_clickthrough(True)

    def overlay_clickthrough_off(self) -> bool:
        return self.overlay_clickthrough(False)

    # Abstracts to be implemented by platform-specific subclasses
    def start_app(self, app_name: str) -> bool:
        raise NotImplementedError

    def kill_app(self, app_name: str) -> bool:
        raise NotImplementedError

    def click(self, x: int, y: int, duration: int = 200):
        raise NotImplementedError

    def long_touch(self, x: int, y: int, duration: Optional[float] = None):
        raise NotImplementedError

    # New desktop-specific interactions
    def right_click(self, x: int, y: int, duration: int = 200):
        raise NotImplementedError

    def double_click(self, x: int, y: int, interval_ms: int = 50):
        raise NotImplementedError

    def move_mouse(self, x: int, y: int):
        raise NotImplementedError

    def scroll_wheel(self, dx: int = 0, dy: int = -1):
        raise NotImplementedError

    def snap_click(self, x: int, y: int, duration: int = 200):
        """Snap click to nearest clickable element.

        Default implementation calls click directly; subclasses can override for coordinate snapping.

        Args:
            x: X coordinate.
            y: Y coordinate.
            duration: Click duration in milliseconds.

        Returns:
            Click result.
        """
        return self.click(x, y, duration)

    def _do_drag(self, start_xy: Tuple[int, int], end_xy: Tuple[int, int], duration: Optional[float] = None):
        raise NotImplementedError

    def scroll(self, start_xy: Tuple[int, int], end_xy: Tuple[int, int], duration: int = 1000):
        """Scroll from start to end coordinates.

        Default implementation uses drag; subclasses can override for native scrolling.

        Args:
            start_xy: Start coordinates (x, y).
            end_xy: End coordinates (x, y).
            duration: Scroll duration in milliseconds.

        Returns:
            Scroll result.
        """
        return self._do_drag(start_xy, end_xy, duration)

    def get_current_state(self):
        """Get current device state.

        Returns device width and height for computer devices.

        Returns:
            DeviceState object with views, width, and height.
        """
        return type("DeviceState", (), {"views": [], "width": self.width, "height": self.height})()

    def view_set_text(self, text: str, x: int = None, y: int = None):
        raise NotImplementedError

    def view_append_text(self, text: str, x: int = None, y: int = None):
        raise NotImplementedError

    def view_clear_text(self) -> bool:
        """Clear all text in the currently selected input field.

        Returns:
            bool: True if successful, False otherwise.
        """
        raise NotImplementedError

    def start_screen_record(self):
        raise NotImplementedError

    def stop_screen_record(self):
        raise NotImplementedError

    def show_highlight(self, x: int, y: int, radius: int):
        """Draw a temporary circle on screen at specified coordinates.

        Optional implementation; default raises NotImplementedError.

        Args:
            x: X coordinate.
            y: Y coordinate.
            radius: Circle radius in pixels.
        """
        raise NotImplementedError

    def hide_highlight(self):
        raise NotImplementedError

    def get_clipboard(self) -> str:
        raise NotImplementedError

    def set_clipboard(self, text: str) -> bool:
        raise NotImplementedError

    def expand_notification_panel(self):
        """Expand system notification panel.

        Desktop systems typically don't have notification panels.
        macOS can call Notification Center, Windows can call Action Center.
        """
        raise NotImplementedError

    def hotkey(self, keys: str) -> bool:
        """Simulate hotkey combination press.

        Args:
            keys: Space-separated key combination, e.g., 'ctrl c', 'alt tab'.

        Returns:
            bool: True if successful, False otherwise.
        """
        raise NotImplementedError

    def get_width_height(self) -> Tuple[int, int]:
        raise NotImplementedError

    def _do_device_switch(self, device_name: str, device_id: str) -> bool:
        """Execute device switch operation.

        Local computer devices typically don't need switching.

        Args:
            device_name: Device name.
            device_id: Device ID.

        Returns:
            bool: True (always successful for computer devices).
        """
        return True
