from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path


APP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_NAME = "PostureCompanion"


class WindowsStartup:
    @staticmethod
    def command() -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --background'
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        executable = pythonw if pythonw.exists() else Path(sys.executable)
        return f'"{executable}" -m posture_companion.app --background'

    @staticmethod
    def is_enabled() -> bool:
        if os.name != "nt":
            return False
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, APP_RUN_NAME)
            return bool(value)
        except OSError:
            return False

    @staticmethod
    def set_enabled(enabled: bool) -> None:
        if os.name != "nt":
            return
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(
                    key, APP_RUN_NAME, 0, winreg.REG_SZ, WindowsStartup.command()
                )
            else:
                try:
                    winreg.DeleteValue(key, APP_RUN_NAME)
                except FileNotFoundError:
                    pass


class Notifier:
    def __init__(self) -> None:
        try:
            import windows_toasts  # noqa: F401

            self._native_available = os.name == "nt"
        except ImportError:
            self._native_available = False

    def send(self, title: str, message: str) -> None:
        def _show() -> None:
            if self._native_available:
                try:
                    from windows_toasts import Toast, WindowsToaster

                    toast = Toast()
                    toast.text_fields = [title, message]
                    WindowsToaster("坐直助手").show_toast(toast)
                    return
                except Exception:
                    pass
            if os.name == "nt":
                try:
                    import winsound

                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except RuntimeError:
                    pass

        threading.Thread(target=_show, daemon=True).start()


class TrayController:
    def __init__(
        self, show_window: Callable[[], None], quit_app: Callable[[], None]
    ) -> None:
        self.show_window = show_window
        self.quit_app = quit_app
        self.icon = None
        self.thread: threading.Thread | None = None

    @staticmethod
    def _image():
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill="#5B5FEF")
        draw.ellipse((25, 12, 39, 26), fill="white")
        draw.line((32, 27, 32, 47), fill="white", width=6)
        draw.arc((18, 27, 46, 52), 190, 350, fill="white", width=5)
        return image

    def start(self) -> bool:
        try:
            import pystray
        except ImportError:
            return False
        menu = pystray.Menu(
            pystray.MenuItem("打开坐直助手", lambda: self.show_window(), default=True),
            pystray.MenuItem("退出", lambda: self.quit_app()),
        )
        self.icon = pystray.Icon("posture_companion", self._image(), "坐直助手", menu)
        self.thread = threading.Thread(target=self.icon.run, daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
