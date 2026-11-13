from __future__ import annotations

import os
import time
import tkinter as tk
from collections.abc import Callable
from enum import Enum

from PIL import Image, ImageTk

from .pet_art import draw_pet


class PetPose(str, Enum):
    UPRIGHT = "upright"
    LEANING = "leaning"
    SLOUCHED = "slouched"
    AWAY = "away"


def pet_pose_for_score(
    score: float | None, threshold: float, person_visible: bool = True
) -> PetPose:
    if not person_visible or score is None:
        return PetPose.AWAY
    if score >= threshold:
        return PetPose.SLOUCHED
    if score >= max(12.0, threshold * 0.55):
        return PetPose.LEANING
    return PetPose.UPRIGHT


def activity_action(title: str) -> str:
    return "drink" if any(word in title.lower() for word in ("水", "喝", "water")) else "stretch"


class PetCompanionWindow(tk.Toplevel):
    WIDTH = 260
    HEIGHT = 298
    TRANSPARENT = "#010203"

    def __init__(
        self,
        master: tk.Misc,
        kind: str = "cat",
        visible: bool = True,
        toggle_camera: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self.kind = kind
        self.enabled = visible
        self.pose = PetPose.AWAY
        self.lean = 0.0
        self.target_lean = 0.0
        self.camera_paused = False
        self.toggle_camera = toggle_camera
        self.message = ""
        self.action = "idle"
        self.message_until = 0.0
        self.started = time.monotonic()
        self.drag_origin = None
        self.pressed_control = None
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        if os.name == "nt":
            self.attributes("-transparentcolor", self.TRANSPARENT)
        x = max(8, self.winfo_screenwidth() - self.WIDTH - 24)
        y = max(8, self.winfo_screenheight() - self.HEIGHT - 56)
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        self.canvas = tk.Canvas(self, bg=self.TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.pet_item = self.canvas.create_image(130, 166)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Motion>", self._cursor)
        self._draw_controls()
        self._draw_pet(self.started)
        if visible:
            self.deiconify()
        self.animation = self.after(67, self._animate)

    @staticmethod
    def _control_at(x: int, y: int) -> str | None:
        if 42 <= x <= 178 and 244 <= y <= 276:
            return "camera"
        if 187 <= x <= 219 and 244 <= y <= 276:
            return "hide"
        return None

    def _press(self, event) -> None:
        self.pressed_control = self._control_at(event.x, event.y)
        if self.pressed_control is None:
            self.drag_origin = event.x_root, event.y_root, self.winfo_x(), self.winfo_y()

    def _drag(self, event) -> None:
        if self.drag_origin is not None:
            x, y, left, top = self.drag_origin
            self.geometry(f"+{left + event.x_root - x}+{top + event.y_root - y}")

    def _release(self, event) -> None:
        self.drag_origin = None
        control = self._control_at(event.x, event.y)
        if control != self.pressed_control:
            return
        if control == "camera" and self.toggle_camera is not None:
            self.toggle_camera()
        elif control == "hide":
            self.withdraw()

    def _cursor(self, event) -> None:
        cursor = "hand2" if self._control_at(event.x, event.y) else "fleur"
        self.canvas.configure(cursor=cursor)

    def set_camera_paused(self, paused: bool) -> None:
        self.camera_paused = paused
        if paused:
            self.pose = PetPose.AWAY
            self.target_lean = 0.0
        self._draw_controls()

    def configure_pet(self, kind: str, enabled: bool) -> None:
        self.kind = kind
        self.enabled = enabled
        if enabled:
            self._draw_pet(time.monotonic())
            self.deiconify()
        else:
            self.withdraw()

    def sync(self, score: float | None, threshold: float, person_visible: bool = True) -> None:
        self.pose = pet_pose_for_score(score, threshold, person_visible)
        self.target_lean = (
            0.0 if self.pose is PetPose.AWAY or score is None
            else min(1.0, max(0.0, (score - 8) / max(1, threshold - 8)))
        )

    def show_message(self, message: str, action: str = "wave", seconds: float = 10) -> None:
        self.message = message.strip()
        self.action = action
        self.message_until = time.monotonic() + seconds
        self._draw_bubble()
        if self.enabled:
            self.deiconify()
            self.lift()

    def shutdown(self) -> None:
        self.after_cancel(self.animation)
        self.destroy()

    def _animate(self) -> None:
        now = time.monotonic()
        if self.message and now >= self.message_until:
            self.message = ""
            self.action = "idle"
            self._draw_bubble()
        if self.enabled and self.state() != "withdrawn":
            self._draw_pet(now)
        self.animation = self.after(67, self._animate)

    def _draw_pet(self, now: float) -> None:
        self.lean += (self.target_lean - self.lean) * 0.26
        image = draw_pet(
            self.kind, self.lean, now - self.started, self.action,
            self.pose is PetPose.AWAY,
        )
        # Windows Tk uses a color key for the transparent desktop window.
        background = Image.new("RGBA", image.size, self.TRANSPARENT)
        mask = image.getchannel("A")
        background.paste(image, mask=mask.point(lambda a: 255 if a >= 105 else 0))
        self.photo = ImageTk.PhotoImage(background.convert("RGB"), master=self)
        self.canvas.itemconfigure(self.pet_item, image=self.photo)

    def _draw_controls(self) -> None:
        c = self.canvas
        c.delete("controls")
        fill = "#35766A" if self.camera_paused else "#233D38"
        c.create_oval(42, 244, 74, 276, fill=fill, outline="", tags="controls")
        c.create_rectangle(58, 244, 162, 276, fill=fill, outline="", tags="controls")
        c.create_oval(146, 244, 178, 276, fill=fill, outline="", tags="controls")
        label = "继续摄像头" if self.camera_paused else "暂停摄像头"
        c.create_text(110, 260, text=label, fill="white",
                      font=("Microsoft YaHei UI", 9, "bold"), tags="controls")
        c.create_oval(187, 244, 219, 276, fill="#F5EFE5", outline="#D8C9B9", tags="controls")
        c.create_text(203, 259, text="×", fill="#50453C", font=("Segoe UI", 14), tags="controls")

    def _draw_bubble(self) -> None:
        c = self.canvas
        c.delete("bubble")
        if not self.message:
            return
        c.create_polygon(15, 4, 245, 4, 245, 64, 145, 64, 130, 78, 117, 64, 15, 64,
                         smooth=True, fill="#FFF9ED", outline="#DBCCB8", tags="bubble")
        message = self.message if len(self.message) <= 54 else self.message[:53] + "…"
        c.create_text(130, 34, text=message, width=200, justify="center",
                      fill="#38473C", font=("Microsoft YaHei UI", 10, "bold"), tags="bubble")
