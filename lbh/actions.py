from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any

from .coordinates import ResizeTransform, ensure_desktop_point
from .models import AtomicAction, CoordSpace, Point


class ActionExecutionError(RuntimeError):
    pass


class PyAutoGuiExecutor:
    """Execute atomic GUI actions.

    The executor only clicks desktop coordinates. If a model returns resized-image
    coordinates, pass a ResizeTransform so the runtime can convert them.
    """

    def __init__(self, pause: float = 0.05):
        self.pause = pause

    def _pyautogui(self):
        try:
            import pyautogui  # type: ignore
        except ImportError as exc:
            raise ActionExecutionError("pyautogui is required for action execution") from exc
        return pyautogui

    def _desktop_point(self, action: AtomicAction, transform: ResizeTransform | None) -> Point:
        if not action.point:
            raise ActionExecutionError(f"Action {action.type} requires point")
        if action.point.space == CoordSpace.DESKTOP:
            return action.point
        if not transform:
            raise ActionExecutionError(f"Need transform for point in {action.point.space}")
        return ensure_desktop_point(action.point, transform)

    def execute(self, action: AtomicAction, transform: ResizeTransform | None = None) -> dict[str, Any]:
        pyautogui = self._pyautogui()
        started = time.perf_counter()
        result: dict[str, Any] = {"action": action.to_dict(), "status": "success"}

        if action.type == "click":
            point = self._desktop_point(action, transform)
            pyautogui.click(x=point.x, y=point.y, clicks=action.clicks, button=action.button)
            result["desktop_point"] = point.to_dict()

        elif action.type == "double_click":
            point = self._desktop_point(action, transform)
            pyautogui.click(x=point.x, y=point.y, clicks=2, interval=0.2, button=action.button)
            result["desktop_point"] = point.to_dict()

        elif action.type == "type_text":
            if action.text is None:
                raise ActionExecutionError("type_text requires text")
            pyautogui.write(action.text, interval=0.02)

        elif action.type == "press":
            if not action.key:
                raise ActionExecutionError("press requires key")
            pyautogui.press(action.key)

        elif action.type == "hotkey":
            if not action.keys:
                raise ActionExecutionError("hotkey requires keys")
            pyautogui.hotkey(*action.keys, interval=0.02)

        elif action.type == "wait":
            time.sleep(float(action.seconds or 0.0))

        elif action.type == "clipboard_set":
            if action.text is None:
                raise ActionExecutionError("clipboard_set requires text")
            try:
                import pyperclip  # type: ignore

                pyperclip.copy(action.text)
            except ImportError as exc:
                raise ActionExecutionError("pyperclip is required for clipboard_set") from exc

        elif action.type == "window_activate":
            if not action.title_contains:
                raise ActionExecutionError("window_activate requires title_contains")
            import pygetwindow as gw  # type: ignore

            matches = [w for w in gw.getAllWindows() if action.title_contains.lower() in w.title.lower()]
            if not matches:
                raise ActionExecutionError(f"No window title contains {action.title_contains!r}")
            matches[0].activate()

        elif action.type == "noop":
            pass

        else:
            raise ActionExecutionError(f"Unknown action type: {action.type}")

        if self.pause:
            time.sleep(self.pause)
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        return result

    def execute_many(self, actions: list[AtomicAction], transform: ResizeTransform | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        results = []
        for action in actions:
            results.append(self.execute(action, transform=transform))
        return {
            "status": "success",
            "count": len(results),
            "results": results,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
