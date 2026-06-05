from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from PIL import Image

from .contracts import WindowMetadata
from .errors import LBHError


class DesktopAdapter:
    def screenshot(self) -> Image.Image:
        raise NotImplementedError

    def screen_size(self) -> tuple[int, int]:
        raise NotImplementedError

    def active_window(self) -> WindowMetadata | None:
        raise NotImplementedError

    def click(self, x: int, y: int, *, clicks: int, button: str, interval: float) -> dict[str, Any]:
        raise NotImplementedError

    def move_to(self, x: int, y: int) -> dict[str, Any]:
        raise NotImplementedError

    def mouse_down(self, *, x: int | None = None, y: int | None = None, button: str = "left") -> dict[str, Any]:
        raise NotImplementedError

    def mouse_up(self, *, x: int | None = None, y: int | None = None, button: str = "left") -> dict[str, Any]:
        raise NotImplementedError

    def drag_to(self, x: int, y: int, *, duration: float, button: str) -> dict[str, Any]:
        raise NotImplementedError

    def scroll(self, amount: int) -> dict[str, Any]:
        raise NotImplementedError

    def type_text(self, text: str, *, interval: float) -> dict[str, Any]:
        raise NotImplementedError

    def press(self, key: str) -> dict[str, Any]:
        raise NotImplementedError

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        raise NotImplementedError

    def wait(self, seconds: float) -> dict[str, Any]:
        raise NotImplementedError

    def set_clipboard(self, text: str) -> dict[str, Any]:
        raise NotImplementedError

    def get_clipboard(self) -> dict[str, Any]:
        raise NotImplementedError

    def window_action(self, action: str, *, title_contains: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class PyAutoGUIDesktopAdapter(DesktopAdapter):
    pause_after_window_action: float = 0.2

    def _pyautogui(self):
        import pyautogui

        # The runtime controls the desktop directly; leave PyAutoGUI fail-safe off
        # so a stale cursor position in a screen corner does not block every action.
        pyautogui.FAILSAFE = False
        return pyautogui

    def _pygetwindow(self):
        import pygetwindow

        return pygetwindow

    def _pyperclip(self):
        import pyperclip

        return pyperclip

    def screenshot(self) -> Image.Image:
        return self._pyautogui().screenshot()

    def screen_size(self) -> tuple[int, int]:
        size = self._pyautogui().size()
        return int(size.width), int(size.height)

    def active_window(self) -> WindowMetadata | None:
        gw = self._pygetwindow()
        window = gw.getActiveWindow()
        if not window:
            return None
        return WindowMetadata(
            title=window.title,
            left=int(window.left),
            top=int(window.top),
            width=int(window.width),
            height=int(window.height),
            right=int(window.right),
            bottom=int(window.bottom),
            is_active=bool(window.isActive),
            is_minimized=bool(window.isMinimized),
            is_maximized=bool(window.isMaximized),
        )

    def _find_window(self, title_contains: str | None = None):
        gw = self._pygetwindow()
        if title_contains:
            matches = [
                window
                for window in gw.getAllWindows()
                if title_contains.lower() in (window.title or "").lower()
            ]
            if not matches:
                raise LBHError(f"No window title contains '{title_contains}'.")
            return matches[0]
        window = gw.getActiveWindow()
        if not window:
            raise LBHError("No active window is available.")
        return window

    def click(self, x: int, y: int, *, clicks: int, button: str, interval: float) -> dict[str, Any]:
        self._pyautogui().click(x=x, y=y, clicks=clicks, button=button, interval=interval)
        return {
            "status": "success",
            "desktop_x": x,
            "desktop_y": y,
            "clicks": clicks,
            "button": button,
            "interval": interval,
        }

    def move_to(self, x: int, y: int) -> dict[str, Any]:
        self._pyautogui().moveTo(x=x, y=y)
        return {"status": "success", "desktop_x": x, "desktop_y": y}

    def mouse_down(self, *, x: int | None = None, y: int | None = None, button: str = "left") -> dict[str, Any]:
        self._pyautogui().mouseDown(x=x, y=y, button=button)
        return {"status": "success", "desktop_x": x, "desktop_y": y, "button": button}

    def mouse_up(self, *, x: int | None = None, y: int | None = None, button: str = "left") -> dict[str, Any]:
        self._pyautogui().mouseUp(x=x, y=y, button=button)
        return {"status": "success", "desktop_x": x, "desktop_y": y, "button": button}

    def drag_to(self, x: int, y: int, *, duration: float, button: str) -> dict[str, Any]:
        self._pyautogui().dragTo(x=x, y=y, duration=duration, button=button)
        return {"status": "success", "desktop_x": x, "desktop_y": y, "duration": duration, "button": button}

    def scroll(self, amount: int) -> dict[str, Any]:
        self._pyautogui().scroll(amount)
        return {"status": "success", "amount": amount}

    def type_text(self, text: str, *, interval: float) -> dict[str, Any]:
        self._pyautogui().write(text, interval=interval)
        return {"status": "success", "text_length": len(text), "interval": interval}

    def press(self, key: str) -> dict[str, Any]:
        self._pyautogui().press(key)
        return {"status": "success", "key": key}

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        self._pyautogui().hotkey(*keys)
        return {"status": "success", "keys": keys}

    def wait(self, seconds: float) -> dict[str, Any]:
        time.sleep(seconds)
        return {"status": "success", "seconds": seconds}

    def set_clipboard(self, text: str) -> dict[str, Any]:
        self._pyperclip().copy(text)
        return {"status": "success", "text_length": len(text)}

    def get_clipboard(self) -> dict[str, Any]:
        text = self._pyperclip().paste()
        return {"status": "success", "text": text, "text_length": len(text)}

    def window_action(self, action: str, *, title_contains: str | None = None) -> dict[str, Any]:
        window = self._find_window(title_contains)
        if action == "activate":
            window.activate()
        elif action == "minimize":
            window.minimize()
        elif action == "maximize":
            window.maximize()
        elif action == "restore":
            window.restore()
        elif action == "close":
            if hasattr(window, "close"):
                window.close()
            else:
                self.hotkey(["alt", "f4"])
        else:
            raise LBHError(f"Unsupported window action: {action}")
        time.sleep(self.pause_after_window_action)
        return {
            "status": "success",
            "action": action,
            "window": self.active_window().to_dict() if self.active_window() else None,
        }
