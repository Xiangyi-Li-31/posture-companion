from __future__ import annotations

import argparse
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk

from .config import (
    AppSettings,
    CalibrationStore,
    SettingsStore,
    default_data_dir,
    resource_path,
)
from .notifications import AlertThrottle
from .pet import PetCompanionWindow, activity_action
from .pet_art import draw_pet
from .posture import PostureBaseline, PostureMonitor, PostureReading, PostureState
from .presence import PresenceMonitor, PresenceReading, PresenceState
from .storage import DailyStats, TodoRepository
from .system import Notifier, TrayController, WindowsStartup
from .timers import SittingTimer, TimerState
from .vision import PoseCamera, VisionResult, list_available_cameras


MODEL_PATH = resource_path("models", "pose_landmarker_lite.task")
BG = "#F4F3EE"
CARD = "#FFFEFB"
INK = "#233D38"
MUTED = "#536862"
ACCENT = "#286B5D"
GREEN = "#217654"
RED = "#AD3D46"
AMBER = "#8F551B"
LINE = "#E3E8E0"
SOFT = "#E5EEE8"
RAIL = "#203B35"


class PostureCompanionApp(tk.Tk):
    def __init__(
        self,
        data_dir=None,
        start_hidden: bool = False,
        enable_camera: bool = True,
        enable_tray: bool = True,
    ) -> None:
        super().__init__()
        self.title("坐直小伙伴")
        self.geometry("1200x760")
        self.minsize(1010, 680)
        self.configure(bg=BG)

        self.data_dir = data_dir or default_data_dir()
        self.settings_store = SettingsStore(self.data_dir / "settings.json")
        self.calibration_store = CalibrationStore(self.data_dir / "calibration.json")
        self.settings = self.settings_store.load()
        self.repository = TodoRepository(self.data_dir / "posture_companion.sqlite3")

        self.sitting_timer = SittingTimer(self.settings.work_minutes * 60)
        self.posture_monitor = PostureMonitor(
            threshold=self.settings.posture_sensitivity,
            alert_after_seconds=self.settings.posture_alert_seconds,
            baseline=self._load_baseline(self.settings.camera_index),
        )
        self.presence_monitor = PresenceMonitor(self.settings.away_seconds)
        self.notifier = Notifier()
        self.posture_alert = AlertThrottle(
            15.0,
            lambda: self.notifier.send(
                "该坐直啦", "检测到你的整体高度下降或头部前伸，请轻轻坐直。"
            ),
        )

        self.camera_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=3)
        self.camera_stop = threading.Event()
        self.camera_thread: threading.Thread | None = None
        self.camera_retry = None
        self.camera_paused = False
        self.preview_photo = None
        self.latest_reading: PostureReading | None = None
        self.latest_presence = PresenceReading(PresenceState.MAYBE_AWAY, 0.0)
        self.break_notified = False
        self.posture_popup_shown = False
        self.todo_day = date.today()
        self.last_stats_at = time.monotonic()
        self.away_auto_paused = False
        self.timer_was_running_before_away = False
        self.saved_baseline: PostureBaseline | None = self.posture_monitor.baseline
        self.camera_choices: dict[str, int] = {
            f"摄像头 {self.settings.camera_index}": self.settings.camera_index
        }
        self._closing = False

        self._configure_style()
        self._build_ui()
        self._load_settings_into_form()
        self._refresh_day_lists()
        self._refresh_stats()
        self.pet = PetCompanionWindow(
            self,
            kind=self.settings.pet_kind,
            visible=self.settings.pet_enabled,
            toggle_camera=lambda: self.after(0, self._toggle_camera_capture),
        )

        self.tray = TrayController(
            lambda: self.after(0, self._show_window),
            lambda: self.after(0, self._really_quit),
        )
        self.tray_available = self.tray.start() if enable_tray else False
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._tick)
        if enable_camera:
            self.after(350, self.start_camera)
        if start_hidden and self.tray_available:
            self.after(50, self.withdraw)

    def _load_baseline(self, camera_index: int) -> PostureBaseline | None:
        raw = self.calibration_store.load(camera_index)
        if raw is None:
            return None
        try:
            return PostureBaseline.from_dict(raw)
        except (KeyError, TypeError, ValueError):
            return None

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background=BG)
        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Card.TLabel", background=CARD, foreground=INK)
        style.configure("Muted.Card.TLabel", background=CARD, foreground=MUTED)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 23, "bold"), foreground=INK)
        style.configure("Hero.Card.TLabel", font=("Segoe UI", 38, "bold"))
        style.configure("Score.Card.TLabel", font=("Segoe UI", 42, "bold"))
        style.configure("Section.Card.TLabel", font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Metric.Card.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="white",
            padding=(18, 10),
            borderwidth=0,
        )
        style.map("Primary.TButton", background=[("active", "#20584B")])
        style.configure("Soft.TButton", background=SOFT, foreground=ACCENT, padding=(12, 8))
        style.map("Soft.TButton", background=[("active", "#D5E6DB")])
        style.configure("TButton", padding=(10, 7), background=CARD, foreground=INK,
                        bordercolor=LINE, lightcolor=CARD, darkcolor=CARD)
        style.map("TButton", background=[("active", SOFT)])
        style.configure("TEntry", padding=6, fieldbackground="#F6F8F4", bordercolor=LINE)
        style.configure("Card.TCheckbutton", background=CARD, foreground=INK)
        style.map("Card.TCheckbutton", background=[("active", CARD)])
        style.configure("Pages.TNotebook", background=BG, borderwidth=0, padding=0)
        style.layout("Pages.TNotebook.Tab", [])
        style.configure(
            "Treeview",
            background=CARD,
            fieldbackground=CARD,
            foreground=INK,
            borderwidth=0,
            rowheight=38,
        )
        style.configure("Treeview.Heading", background=SOFT, foreground=INK, relief="flat")
        style.map("Treeview", background=[("selected", SOFT)], foreground=[("selected", INK)])
        style.configure("Accent.Horizontal.TProgressbar", background=ACCENT,
                        troughcolor=SOFT, bordercolor=SOFT, thickness=7)

    def _card(self, parent, padding: int = 18) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame", padding=padding)

    def _build_ui(self) -> None:
        rail = tk.Frame(self, bg=RAIL, width=174)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Label(rail, text="坐直小伙伴", bg=RAIL, fg="#FFF8E8",
                 font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=18, pady=(27, 23))
        self.header_presence = tk.Label(rail, text="● 摄像头准备中", bg=RAIL, fg="#C2D4CA",
                                       font=("Microsoft YaHei UI", 9))
        self.header_presence.pack(side="bottom", anchor="w", padx=18, pady=22)

        body = ttk.Frame(self, style="App.TFrame", padding=(22, 18, 22, 20))
        body.pack(side="left", fill="both", expand=True)
        heading = ttk.Frame(body, style="App.TFrame")
        heading.pack(fill="x", pady=(0, 13))
        self.page_title = ttk.Label(heading, style="Title.TLabel")
        self.page_title.pack(side="left")
        self.camera_button = ttk.Button(heading, text="暂停摄像头", style="Soft.TButton",
                                        command=self._toggle_camera_capture)
        self.camera_button.pack(side="right")

        self.notebook = ttk.Notebook(body, style="Pages.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.today_tab, self.posture_tab, self.stats_tab, self.settings_tab = (
            ttk.Frame(self.notebook, style="App.TFrame") for _ in range(4)
        )
        self.navigation = {}
        for title, page in zip(("今天", "坐直监测", "趋势统计", "设置"),
                               (self.today_tab, self.posture_tab, self.stats_tab, self.settings_tab)):
            self.notebook.add(page, text=title)
            button = tk.Button(rail, text=title, anchor="w", padx=12, pady=9,
                               bg=RAIL, fg="#C2D4CA", activebackground="#365A50",
                               activeforeground="white", bd=0, highlightthickness=0,
                               font=("Microsoft YaHei UI", 11),
                               command=lambda page=page: self.notebook.select(page))
            button.pack(fill="x", padx=12, pady=3)
            self.navigation[str(page)] = (title, button)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_page_changed)
        self._build_today_tab()
        self._build_posture_tab()
        self._build_stats_tab()
        self._build_settings_tab()
        self._on_page_changed()

    def _on_page_changed(self, _event=None) -> None:
        selected = self.notebook.select()
        for page, (title, button) in self.navigation.items():
            active = page == selected
            button.configure(bg="#365A50" if active else RAIL,
                             fg="#FFFFFF" if active else "#C2D4CA")
            if active:
                self.page_title.configure(text=title)
        if selected == str(self.stats_tab):
            self._refresh_stats()

    def _build_today_tab(self) -> None:
        self.today_tab.columnconfigure(1, weight=1)
        self.today_tab.columnconfigure(2, weight=1)
        self.today_tab.rowconfigure(0, weight=1)

        timer = self._card(self.today_tab, 22)
        timer.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(timer, text="久坐计时", style="Section.Card.TLabel").pack(anchor="w")
        self.timer_label = ttk.Label(timer, text="45:00", style="Hero.Card.TLabel")
        self.timer_label.pack(pady=(38, 2))
        self.timer_state_label = ttk.Label(timer, text="距离下次活动", style="Muted.Card.TLabel")
        self.timer_state_label.pack()
        self.timer_progress = ttk.Progressbar(timer, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.timer_progress.pack(fill="x", pady=(14, 0))
        self.seat_status = ttk.Label(timer, text="正在确认是否在座", style="Card.TLabel")
        self.seat_status.pack(pady=(28, 6))
        self.pause_button = ttk.Button(timer, text="暂停计时", style="Soft.TButton", command=self._toggle_timer)
        self.pause_button.pack(fill="x", pady=(24, 8))
        ttk.Button(timer, text="完成一次活动", style="Primary.TButton", command=self._complete_break).pack(fill="x")

        activity = self._card(self.today_tab)
        activity.grid(row=0, column=1, sticky="nsew", padx=6)
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(2, weight=1)
        ttk.Label(activity, text="今日活动", style="Section.Card.TLabel").grid(row=0, column=0, sticky="w")
        self.activity_progress = ttk.Label(activity, text="0 / 0 完成", style="Muted.Card.TLabel")
        self.activity_progress.grid(row=0, column=1, sticky="e")
        self.activity_entry = ttk.Entry(activity)
        self.activity_entry.grid(row=1, column=0, sticky="ew", pady=12, padx=(0, 8))
        self.activity_entry.bind("<Return>", lambda _event: self._add_activity())
        ttk.Button(activity, text="添加", command=self._add_activity).grid(row=1, column=1)
        self.activity_tree = self._make_list_tree(activity)
        self.activity_tree.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.activity_tree.bind("<Double-1>", lambda _event: self._toggle_activity())
        buttons = ttk.Frame(activity, style="Card.TFrame")
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="完成 / 撤销", command=self._toggle_activity).pack(side="left")
        ttk.Button(buttons, text="删除", command=self._delete_activity).pack(side="right")

        todos = self._card(self.today_tab)
        todos.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        todos.columnconfigure(0, weight=1)
        todos.rowconfigure(2, weight=1)
        ttk.Label(todos, text="今日待办", style="Section.Card.TLabel").grid(row=0, column=0, sticky="w")
        self.todo_progress = ttk.Label(todos, text="0 / 0 完成", style="Muted.Card.TLabel")
        self.todo_progress.grid(row=0, column=1, sticky="e")
        self.todo_entry = ttk.Entry(todos)
        self.todo_entry.grid(row=1, column=0, sticky="ew", pady=12, padx=(0, 8))
        self.todo_entry.bind("<Return>", lambda _event: self._add_todo())
        ttk.Button(todos, text="添加", command=self._add_todo).grid(row=1, column=1)
        self.todo_tree = self._make_list_tree(todos)
        self.todo_tree.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.todo_tree.bind("<Double-1>", lambda _event: self._toggle_todo())
        buttons = ttk.Frame(todos, style="Card.TFrame")
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="完成 / 撤销", command=self._toggle_todo).pack(side="left")
        ttk.Button(buttons, text="删除", command=self._delete_todo).pack(side="right")

    def _make_list_tree(self, parent) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=("done", "title"), show="headings", selectmode="browse")
        tree.heading("done", text="状态")
        tree.heading("title", text="内容")
        tree.column("done", width=58, anchor="center", stretch=False)
        tree.column("title", width=138, minwidth=95, anchor="w")
        tree.tag_configure("completed", foreground="#98A2B3")
        return tree

    def _build_posture_tab(self) -> None:
        self.posture_tab.columnconfigure(0, weight=3)
        self.posture_tab.columnconfigure(1, weight=2)
        self.posture_tab.rowconfigure(0, weight=1)
        preview_card = self._card(self.posture_tab, 8)
        preview_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        preview_card.columnconfigure(0, weight=1)
        preview_card.rowconfigure(0, weight=1)
        self.preview_label = tk.Label(
            preview_card,
            text="摄像头准备中…",
            bg="#101522",
            fg="#D0D5DD",
            font=("Microsoft YaHei UI", 14),
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        panel = self._card(self.posture_tab, 22)
        panel.grid(row=0, column=1, sticky="nsew")
        ttk.Label(panel, text="未坐直分数", style="Section.Card.TLabel").pack(anchor="w")
        self.posture_score_label = ttk.Label(panel, text="--", style="Score.Card.TLabel")
        self.posture_score_label.pack(anchor="w", pady=(14, 0))
        self.posture_status = ttk.Label(panel, text="等待摄像头", style="Muted.Card.TLabel")
        self.posture_status.pack(anchor="w", pady=(0, 16))
        self.signal_widgets: dict[str, tuple[ttk.Label, ttk.Progressbar]] = {}
        for key, label in (
            ("height_drop", "整体高度下降"),
            ("head_enlargement", "头部靠近 / 变大"),
            ("shoulder_drop", "肩膀下沉"),
            ("torso_collapse", "躯干缩短"),
            ("neck_compression", "颈肩距离缩短"),
            ("depth_advance", "头部向前"),
        ):
            row = ttk.Frame(panel, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            name = ttk.Label(row, text=label, style="Muted.Card.TLabel")
            name.pack(anchor="w")
            bar = ttk.Progressbar(row, maximum=100, style="Accent.Horizontal.TProgressbar")
            bar.pack(fill="x", pady=(3, 0))
            self.signal_widgets[key] = (name, bar)
        self.calibration_button = ttk.Button(
            panel, text="校准坐直姿势", style="Primary.TButton", command=self._calibrate
        )
        self.calibration_button.pack(fill="x", pady=(12, 6))
        ttk.Button(panel, text="重启摄像头", style="Soft.TButton", command=self.restart_camera).pack(fill="x")
        ttk.Label(
            panel,
            text="固定摄像头后自然坐直约 3 秒。蓝线表示校准时的头部高度。",
            style="Muted.Card.TLabel",
            wraplength=285,
        ).pack(anchor="w", pady=(9, 0))

    def _build_stats_tab(self) -> None:
        self.stats_tab.columnconfigure((0, 1, 2), weight=1)
        self.stats_tab.rowconfigure(1, weight=1)
        self.stats_values = {}
        for column, (key, title) in enumerate((
            ("upright", "今日坐直率"),
            ("seated", "今日在座时长"),
            ("breaks", "今日活动次数"),
        )):
            card = self._card(self.stats_tab)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
            ttk.Label(card, text=title, style="Muted.Card.TLabel").pack(anchor="w")
            value = ttk.Label(card, text="--", style="Metric.Card.TLabel")
            value.pack(anchor="w", pady=(6, 0))
            self.stats_values[key] = value
        chart_card = self._card(self.stats_tab)
        chart_card.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        ttk.Label(chart_card, text="最近 7 天坐直率", style="Section.Card.TLabel").pack(anchor="w")
        self.stats_canvas = tk.Canvas(chart_card, bg=CARD, highlightthickness=0)
        self.stats_canvas.pack(fill="both", expand=True, pady=(12, 0))
        self.stats_canvas.bind("<Configure>", lambda _event: self._draw_stats_chart())
        self.stats_rows: list[DailyStats] = []

    def _build_settings_tab(self) -> None:
        self.settings_tab.columnconfigure((0, 1), weight=1)
        left = self._card(self.settings_tab, 22)
        right = self._card(self.settings_tab, 22)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        left.columnconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        ttk.Label(left, text="检测与计时", style="Section.Card.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.work_minutes_var = tk.StringVar()
        self.alert_seconds_var = tk.StringVar()
        self.popup_seconds_var = tk.StringVar()
        self.away_seconds_var = tk.StringVar()
        self.sensitivity_var = tk.DoubleVar()
        self.camera_var = tk.StringVar()
        self.mirror_var = tk.BooleanVar()
        self.preview_var = tk.BooleanVar()
        self.auto_away_var = tk.BooleanVar()
        self.startup_var = tk.BooleanVar()
        self.tray_var = tk.BooleanVar()
        self.pet_enabled_var = tk.BooleanVar()
        self.pet_kind_var = tk.StringVar()

        for row, (label, variable) in enumerate((
            ("久坐提醒（分钟）", self.work_minutes_var),
            ("快速通知确认（秒）", self.alert_seconds_var),
            ("连续未坐直弹窗（秒）", self.popup_seconds_var),
            ("离座确认时间（秒）", self.away_seconds_var),
        ), start=1):
            ttk.Label(left, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=7)
            ttk.Entry(left, textvariable=variable, width=16).grid(row=row, column=1, sticky="ew", pady=7)

        ttk.Label(left, text="未坐直提醒阈值", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=7)
        ttk.Scale(
            left,
            from_=15,
            to=75,
            variable=self.sensitivity_var,
            command=lambda value: self.sensitivity_value.configure(
                text=f"{float(value):.0f} 分"
            ),
        ).grid(row=5, column=1, sticky="ew", pady=7)
        self.sensitivity_value = ttk.Label(left, text="40 分", style="Muted.Card.TLabel")
        self.sensitivity_value.grid(row=5, column=2, padx=(8, 0))
        ttk.Label(left, text="摄像头", style="Card.TLabel").grid(row=6, column=0, sticky="w", pady=7)
        self.camera_combo = ttk.Combobox(left, textvariable=self.camera_var, state="readonly")
        self.camera_combo.grid(row=6, column=1, sticky="ew", pady=7)
        ttk.Button(left, text="刷新", command=self._refresh_cameras).grid(row=6, column=2, padx=(8, 0))

        for row, (text, variable) in enumerate((
            ("自动识别离座并重新计时", self.auto_away_var),
            ("镜像摄像头画面", self.mirror_var),
            ("显示摄像头预览", self.preview_var),
            ("显示桌面姿势小宠物", self.pet_enabled_var),
            ("关闭窗口时缩到托盘", self.tray_var),
            ("登录 Windows 后自动启动", self.startup_var),
        ), start=7):
            ttk.Checkbutton(left, text=text, variable=variable, style="Card.TCheckbutton").grid(
                row=row, column=0, columnspan=3, sticky="w", pady=3
            )

        ttk.Label(left, text="小宠物", style="Card.TLabel").grid(row=13, column=0, sticky="w", pady=7)
        pet_combo = ttk.Combobox(
            left,
            textvariable=self.pet_kind_var,
            state="readonly",
            values=("猫猫", "狗狗"),
        )
        pet_combo.grid(row=13, column=1, sticky="ew", pady=7)
        pet_combo.bind("<<ComboboxSelected>>", self._update_pet_preview)

        ttk.Label(right, text="每日活动模板", style="Section.Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(right, text="每行一项；每天会生成可分别完成的清单。", style="Muted.Card.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 10))
        self.activity_templates_text = tk.Text(
            right,
            height=6,
            bg="#F6F8F4",
            fg=INK,
            insertbackground=INK,
            relief="flat",
            padx=12,
            pady=10,
            font=("Microsoft YaHei UI", 10),
        )
        self.activity_templates_text.grid(row=2, column=0, sticky="nsew")
        ttk.Label(right, text="宠物预览", style="Section.Card.TLabel").grid(
            row=3, column=0, sticky="w", pady=(16, 0)
        )
        self.pet_preview = tk.Label(right, bg=CARD)
        self.pet_preview.grid(row=4, column=0, sticky="nsew")
        right.rowconfigure(4, weight=1)
        ttk.Button(right, text="保存全部设置", style="Primary.TButton", command=self._save_settings).grid(
            row=5, column=0, sticky="ew", pady=(12, 0)
        )

    def _update_pet_preview(self, _event=None) -> None:
        from PIL import ImageTk

        kind = "cat" if self.pet_kind_var.get() == "猫猫" else "dog"
        self.pet_preview_photo = ImageTk.PhotoImage(draw_pet(kind), master=self)
        self.pet_preview.configure(image=self.pet_preview_photo)

    def _load_settings_into_form(self) -> None:
        self.work_minutes_var.set(str(self.settings.work_minutes))
        self.alert_seconds_var.set(str(self.settings.posture_alert_seconds))
        self.popup_seconds_var.set(str(self.settings.posture_popup_seconds))
        self.away_seconds_var.set(str(self.settings.away_seconds))
        self.sensitivity_var.set(self.settings.posture_sensitivity)
        self.sensitivity_value.configure(text=f"{self.settings.posture_sensitivity} 分")
        choice = f"摄像头 {self.settings.camera_index}"
        self.camera_combo.configure(values=list(self.camera_choices))
        self.camera_var.set(choice)
        self.mirror_var.set(self.settings.mirror_camera)
        self.preview_var.set(self.settings.show_camera_preview)
        self.auto_away_var.set(self.settings.auto_away_detection)
        self.startup_var.set(WindowsStartup.is_enabled())
        self.tray_var.set(self.settings.minimize_to_tray)
        self.pet_enabled_var.set(self.settings.pet_enabled)
        self.pet_kind_var.set("猫猫" if self.settings.pet_kind == "cat" else "狗狗")
        self._update_pet_preview()
        self.activity_templates_text.delete("1.0", "end")
        self.activity_templates_text.insert("1.0", "\n".join(self.settings.activity_templates))

    def _save_settings(self) -> None:
        templates = [line.strip() for line in self.activity_templates_text.get("1.0", "end").splitlines() if line.strip()]
        try:
            camera_index = self.camera_choices.get(self.camera_var.get(), int(self.settings.camera_index))
            updated = AppSettings(
                work_minutes=int(self.work_minutes_var.get()),
                activity_text=templates[0] if templates else self.settings.activity_text,
                activity_templates=templates,
                posture_alert_seconds=float(self.alert_seconds_var.get()),
                posture_popup_seconds=float(self.popup_seconds_var.get()),
                posture_sensitivity=round(self.sensitivity_var.get()),
                camera_index=camera_index,
                mirror_camera=self.mirror_var.get(),
                show_camera_preview=self.preview_var.get(),
                auto_away_detection=self.auto_away_var.get(),
                away_seconds=int(self.away_seconds_var.get()),
                start_with_windows=self.startup_var.get(),
                minimize_to_tray=self.tray_var.get(),
                pet_enabled=self.pet_enabled_var.get(),
                pet_kind="cat" if self.pet_kind_var.get() == "猫猫" else "dog",
            ).validate()
        except ValueError:
            messagebox.showerror("设置有误", "请检查时间和阈值是否为有效数字。")
            return
        camera_changed = updated.camera_index != self.settings.camera_index or updated.mirror_camera != self.settings.mirror_camera
        self.settings = updated
        self.settings_store.save(updated)
        try:
            WindowsStartup.set_enabled(updated.start_with_windows)
        except OSError as exc:
            messagebox.showwarning("开机启动设置失败", str(exc))
        self.sitting_timer.set_duration(updated.work_minutes * 60)
        self.presence_monitor.set_away_after(updated.away_seconds)
        self.posture_monitor.set_threshold(updated.posture_sensitivity, updated.posture_alert_seconds)
        self.pet.configure_pet(updated.pet_kind, updated.pet_enabled)
        self.repository.ensure_activities(date.today(), updated.activity_templates)
        self._refresh_day_lists()
        if camera_changed:
            self.posture_monitor.baseline = self._load_baseline(updated.camera_index)
            self.saved_baseline = self.posture_monitor.baseline
            self.restart_camera()
        self.notifier.send("设置已保存", "新的计时、活动和检测设置已经生效。")

    def _tick(self) -> None:
        if self._closing:
            return
        if date.today() != self.todo_day:
            self._refresh_day_lists()
        self._update_timer_ui()
        self._drain_camera_queue()
        self._record_stats_if_due()
        self.after(150, self._tick)

    def _update_timer_ui(self) -> None:
        snapshot = self.sitting_timer.snapshot()
        minutes, seconds = divmod(int(snapshot.remaining_seconds), 60)
        self.timer_label.configure(text=f"{minutes:02d}:{seconds:02d}")
        self.timer_progress["value"] = 100 * (
            1 - snapshot.remaining_seconds / (self.settings.work_minutes * 60)
        )
        if self.away_auto_paused:
            self.timer_state_label.configure(text="离座中，计时已暂停", foreground=GREEN)
            self.pause_button.configure(text="继续计时")
        elif snapshot.state == TimerState.PAUSED:
            self.timer_state_label.configure(text="计时已暂停", foreground=MUTED)
            self.pause_button.configure(text="继续计时")
        elif snapshot.state == TimerState.DUE:
            self.timer_state_label.configure(text="该起来活动了", foreground=RED)
            if not self.break_notified:
                self.break_notified = True
                remaining = [item.title for item in self.repository.list_activities(date.today()) if not item.completed]
                suggestion = remaining[0] if remaining else self.settings.activity_text
                self.notifier.send("活动时间到", suggestion)
                self.pet.show_message(
                    f"该{suggestion}啦！",
                    activity_action(suggestion),
                    seconds=12,
                )
        else:
            self.timer_state_label.configure(text="距离下次活动", foreground=MUTED)
            self.pause_button.configure(text="暂停计时")

    def _handle_presence(self, reading: PresenceReading) -> None:
        previous = self.latest_presence
        self.latest_presence = reading
        if reading.state == PresenceState.PRESENT:
            self.header_presence.configure(text="● 已在座", fg="#68D9B0")
            self.seat_status.configure(text="已在座，正在守护坐姿", foreground=GREEN)
        elif reading.state == PresenceState.AWAY:
            self.header_presence.configure(text="● 已离座", fg="#F8C26A")
            self.seat_status.configure(text="已自动识别离座", foreground=AMBER)
        else:
            self.header_presence.configure(text="● 正在确认", fg="#AEB5C7")
            self.seat_status.configure(text=f"未见人 {reading.absent_for_seconds:.0f} 秒", foreground=MUTED)

        if not self.settings.auto_away_detection:
            return
        if reading.just_left:
            self.timer_was_running_before_away = self.sitting_timer.snapshot().state != TimerState.PAUSED
            self.sitting_timer.reset()
            self.sitting_timer.pause()
            self.away_auto_paused = True
            self.break_notified = False
            self.repository.record_stats(date.today(), away_breaks=1)
            self.notifier.send("离座已识别", "本轮久坐计时已经自动重置。回来后会重新开始。")
            self._refresh_stats()
        elif reading.just_returned and self.away_auto_paused:
            if self.timer_was_running_before_away:
                self.sitting_timer.resume()
            self.away_auto_paused = False
            self.notifier.send("欢迎回来", "新的久坐计时已经开始。")
        elif previous.state == PresenceState.AWAY and reading.state != PresenceState.AWAY:
            self.away_auto_paused = False

    def _toggle_timer(self) -> None:
        if self.sitting_timer.snapshot().state == TimerState.PAUSED:
            self.sitting_timer.resume()
            self.away_auto_paused = False
        else:
            self.sitting_timer.pause()

    def _complete_break(self) -> None:
        self.sitting_timer.reset()
        self.break_notified = False
        self.repository.record_stats(date.today(), manual_breaks=1)
        self._refresh_stats()
        self.notifier.send("活动完成", "做得好，新的专注周期开始了。")
        self.pet.show_message("活动完成！我们继续精神满满～", "stretch", seconds=7)

    def _refresh_day_lists(self) -> None:
        self.todo_day = date.today()
        self.repository.ensure_activities(self.todo_day, self.settings.activity_templates)
        self._fill_tree(self.todo_tree, self.repository.list_for_day(self.todo_day), self.todo_progress)
        self._fill_tree(self.activity_tree, self.repository.list_activities(self.todo_day), self.activity_progress)

    @staticmethod
    def _fill_tree(tree: ttk.Treeview, items, progress: ttk.Label) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for value in items:
            tree.insert("", "end", iid=str(value.id), values=("✓" if value.completed else "○", value.title), tags=("completed",) if value.completed else ())
        done = sum(value.completed for value in items)
        progress.configure(text=f"{done} / {len(items)} 完成")

    def _add_todo(self) -> None:
        try:
            self.repository.add(self.todo_entry.get(), date.today())
            self.todo_entry.delete(0, "end")
            self._refresh_day_lists()
        except ValueError as exc:
            messagebox.showwarning("无法添加", str(exc))

    def _add_activity(self) -> None:
        try:
            self.repository.add_activity(self.activity_entry.get(), date.today())
            self.activity_entry.delete(0, "end")
            self._refresh_day_lists()
        except Exception as exc:
            messagebox.showwarning("无法添加", f"活动为空或已存在：{exc}")

    @staticmethod
    def _selected_id(tree: ttk.Treeview) -> int | None:
        selected = tree.selection()
        return int(selected[0]) if selected else None

    def _toggle_todo(self) -> None:
        item_id = self._selected_id(self.todo_tree)
        if item_id is not None:
            completed = self.todo_tree.item(str(item_id), "values")[0] == "✓"
            self.repository.set_completed(item_id, not completed)
            self._refresh_day_lists()

    def _delete_todo(self) -> None:
        item_id = self._selected_id(self.todo_tree)
        if item_id is not None:
            self.repository.delete(item_id)
            self._refresh_day_lists()

    def _toggle_activity(self) -> None:
        item_id = self._selected_id(self.activity_tree)
        if item_id is not None:
            completed = self.activity_tree.item(str(item_id), "values")[0] == "✓"
            title = str(self.activity_tree.item(str(item_id), "values")[1])
            self.repository.set_activity_completed(item_id, not completed)
            self._refresh_day_lists()
            if not completed:
                self.pet.show_message(
                    f"完成：{title}", activity_action(title), seconds=7
                )

    def _delete_activity(self) -> None:
        item_id = self._selected_id(self.activity_tree)
        if item_id is not None:
            self.repository.delete_activity(item_id)
            self._refresh_day_lists()

    def _calibrate(self) -> None:
        self.posture_monitor.start_calibration()
        self.posture_status.configure(text="请自然坐直并保持约 3 秒", foreground=ACCENT)

    def start_camera(self) -> None:
        if self._closing or self.camera_paused:
            return
        if self.camera_thread and self.camera_thread.is_alive():
            if self.camera_stop.is_set() and self.camera_retry is None:
                self.camera_retry = self.after(150, self._retry_camera)
            return
        self._clear_camera_queue()
        self.camera_stop.clear()
        self.pet.set_camera_paused(False)
        self.header_presence.configure(text="● 摄像头启动中", fg="#C2D4CA")
        self.preview_label.configure(text="正在打开摄像头…", image="")
        self.camera_thread = threading.Thread(target=self._camera_worker, daemon=True)
        self.camera_thread.start()

    def _retry_camera(self) -> None:
        self.camera_retry = None
        self.start_camera()

    def restart_camera(self) -> None:
        self.stop_camera()
        if not self.camera_paused:
            self.start_camera()

    def _toggle_camera_capture(self) -> None:
        self.camera_paused = not self.camera_paused
        self.pet.set_camera_paused(self.camera_paused)
        if not self.camera_paused:
            self.camera_button.configure(text="暂停摄像头")
            self.calibration_button.state(["!disabled"])
            self.posture_status.configure(text="正在重新打开摄像头", foreground=ACCENT)
            self.start_camera()
            return

        self.stop_camera()
        self.camera_button.configure(text="继续摄像头")
        self.calibration_button.state(["disabled"])
        self.header_presence.configure(text="● 摄像头已暂停", fg="#F8C26A")
        self.seat_status.configure(text="摄像头已暂停", foreground=MUTED)
        self.posture_status.configure(text="摄像头监测已暂停", foreground=AMBER)
        self.preview_label.configure(text="摄像头已暂停", image="")
        if self.away_auto_paused and self.timer_was_running_before_away:
            self.sitting_timer.resume()
        self.away_auto_paused = False

    def stop_camera(self) -> None:
        self.camera_stop.set()
        if self.camera_retry is not None:
            self.after_cancel(self.camera_retry)
            self.camera_retry = None
        self._clear_camera_queue()
        self._clear_posture_display()

    def _clear_camera_queue(self) -> None:
        while True:
            try:
                self.camera_queue.get_nowait()
            except queue.Empty:
                return

    def _clear_posture_display(self) -> None:
        self.latest_reading = None
        self.latest_presence = PresenceReading(PresenceState.MAYBE_AWAY, 0.0)
        self.posture_popup_shown = False
        self.posture_score_label.configure(text="—", foreground=MUTED)
        for _label, bar in self.signal_widgets.values():
            bar["value"] = 0
        self.pet.sync(None, self.settings.posture_sensitivity, person_visible=False)

    def _camera_worker(self) -> None:
        camera = None
        try:
            self.posture_monitor.update(None, time.monotonic())
            camera = PoseCamera(self.settings.camera_index, MODEL_PATH, self.settings.mirror_camera)
            self._queue_camera("status", "摄像头已启动")
            while not self.camera_stop.is_set():
                result = camera.read()
                if self.camera_stop.is_set():
                    break
                if result is None:
                    time.sleep(0.05)
                    continue
                reading = self.posture_monitor.update(result.landmarks, result.timestamp)
                presence = self.presence_monitor.update(reading.state != PostureState.NO_PERSON, result.timestamp)
                color = (72, 190, 119) if reading.state != PostureState.BAD else (75, 70, 230)
                baseline_y = self.posture_monitor.baseline.head_top_y if self.posture_monitor.baseline else None
                camera.draw_overlay(result.frame_bgr, result.landmarks, color, baseline_y)
                self._queue_camera("frame", (result, reading, presence))
        except Exception as exc:
            self._queue_camera("error", str(exc))
        finally:
            if camera is not None:
                camera.close()

    def _queue_camera(self, kind: str, value: object) -> None:
        try:
            self.camera_queue.put_nowait((kind, value))
        except queue.Full:
            try:
                self.camera_queue.get_nowait()
                self.camera_queue.put_nowait((kind, value))
            except queue.Empty:
                pass

    def _drain_camera_queue(self) -> None:
        if self.camera_stop.is_set():
            self._clear_camera_queue()
            return
        latest = None
        while True:
            try:
                latest = self.camera_queue.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            return
        kind, value = latest
        if kind == "error":
            self._clear_posture_display()
            self.header_presence.configure(text="● 摄像头不可用", fg="#F8C26A")
            self.seat_status.configure(text="摄像头不可用", foreground=AMBER)
            self.preview_label.configure(text=str(value), image="", wraplength=350)
            self.posture_status.configure(text="摄像头不可用", foreground=RED)
            return
        if kind == "frame":
            vision, reading, presence = value
            self._update_posture_ui(vision, reading)
            self._handle_presence(presence)

    def _update_posture_ui(self, vision: VisionResult, reading: PostureReading) -> None:
        self.latest_reading = reading
        person_visible = reading.state != PostureState.NO_PERSON
        self.pet.sync(
            reading.score,
            self.settings.posture_sensitivity,
            person_visible=person_visible,
        )
        score_over_threshold = (
            reading.score is not None
            and reading.score >= self.settings.posture_sensitivity
        )
        if not score_over_threshold:
            self.posture_popup_shown = False
        elif (
            reading.bad_for_seconds >= self.settings.posture_popup_seconds
            and not self.posture_popup_shown
        ):
            self.posture_popup_shown = True
            seconds = round(self.settings.posture_popup_seconds)
            self.pet.show_message(
                f"已经连续 {seconds} 秒没有坐直啦，和我一起抬头挺背！",
                "wave",
                seconds=14,
            )
            self.notifier.send(
                "坐直小伙伴提醒",
                f"你已经连续 {seconds} 秒没有坐直，请调整一下姿势。",
            )
        labels = {
            PostureState.NO_PERSON: ("未识别到人", MUTED),
            PostureState.NEEDS_CALIBRATION: ("请先校准坐直姿势", AMBER),
            PostureState.CALIBRATING: (f"正在校准 {reading.calibration_progress:.0%}", ACCENT),
            PostureState.GOOD: ("坐得不错，继续保持", GREEN),
            PostureState.BAD: ("身体正在下沉，请坐直", RED),
        }
        text, color = labels[reading.state]
        if score_over_threshold and not self.posture_popup_shown:
            remaining = max(
                0,
                round(
                    self.settings.posture_popup_seconds
                    - reading.bad_for_seconds
                ),
            )
            text = f"正在下沉 · 已持续 {reading.bad_for_seconds:.0f} 秒 · {remaining} 秒后弹窗"
            color = AMBER
        self.posture_status.configure(text=text, foreground=color)
        self.posture_score_label.configure(text="--" if reading.score is None else f"{reading.score:.0f}", foreground=color)
        if reading.breakdown:
            for key, (_label, bar) in self.signal_widgets.items():
                bar["value"] = getattr(reading.breakdown, key)
        else:
            for _label, bar in self.signal_widgets.values():
                bar["value"] = 0
        if reading.state == PostureState.BAD:
            self.posture_alert.trigger(vision.timestamp)

        if self.posture_monitor.baseline is not None and self.posture_monitor.baseline != self.saved_baseline:
            self.calibration_store.save(self.settings.camera_index, self.posture_monitor.baseline.to_dict())
            self.saved_baseline = self.posture_monitor.baseline
            self.notifier.send("校准完成", "新的坐直高度与头部大小基线已经保存。")

        if not self.settings.show_camera_preview:
            self.preview_label.configure(text="预览已隐藏，检测仍在本机运行", image="")
            return
        if self.notebook.select() != str(self.posture_tab):
            return
        try:
            from PIL import Image, ImageTk

            image = Image.fromarray(vision.frame_bgr[:, :, ::-1])
            image.thumbnail(
                (max(1, self.preview_label.winfo_width() - 12),
                 max(1, self.preview_label.winfo_height() - 12)),
                Image.Resampling.BILINEAR,
            )
            self.preview_photo = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.preview_photo, text="")
        except ImportError:
            self.preview_label.configure(text="缺少 Pillow，无法显示预览", image="")

    def _record_stats_if_due(self) -> None:
        now = time.monotonic()
        elapsed = int(now - self.last_stats_at)
        if elapsed < 5:
            return
        self.last_stats_at = now
        seated = self.latest_presence.state == PresenceState.PRESENT
        reading = self.latest_reading
        has_posture = seated and reading is not None and reading.score is not None
        self.repository.record_stats(
            date.today(),
            posture_samples=int(has_posture),
            upright_samples=int(has_posture and reading.state == PostureState.GOOD),
            needs_attention_samples=int(has_posture and reading.state == PostureState.BAD),
            seated_seconds=elapsed if seated else 0,
        )

    def _refresh_stats(self) -> None:
        if not hasattr(self, "stats_canvas"):
            return
        end = date.today()
        start = end - timedelta(days=6)
        existing = {row.day: row for row in self.repository.list_stats(start, end)}
        self.stats_rows = [existing.get((start + timedelta(days=i)).isoformat(), DailyStats((start + timedelta(days=i)).isoformat())) for i in range(7)]
        today = self.stats_rows[-1]
        upright = (
            f"{today.upright_samples / today.posture_samples:.0%}"
            if today.posture_samples else "—"
        )
        hours, rem = divmod(today.seated_seconds, 3600)
        minutes = rem // 60
        self.stats_values["upright"].configure(text=upright)
        self.stats_values["seated"].configure(text=f"{hours} 小时 {minutes} 分")
        self.stats_values["breaks"].configure(text=str(today.away_breaks + today.manual_breaks))
        self._draw_stats_chart()

    def _draw_stats_chart(self) -> None:
        if not hasattr(self, "stats_canvas") or not self.stats_rows:
            return
        canvas = self.stats_canvas
        canvas.delete("all")
        width = max(600, canvas.winfo_width())
        height = max(260, canvas.winfo_height())
        base_y = height - 42
        chart_height = height - 72
        slot = (width - 72) / 7
        for mark in (0, 50, 100):
            y = base_y - chart_height * mark / 100
            canvas.create_line(50, y, width - 15, y, fill=LINE)
            canvas.create_text(43, y, text=f"{mark}%", anchor="e", fill=MUTED,
                               font=("Segoe UI", 9))
        for index, row in enumerate(self.stats_rows):
            ratio = row.upright_samples / row.posture_samples if row.posture_samples else 0
            bar_height = ratio * chart_height
            x0 = 53 + index * slot + slot * 0.24
            x1 = x0 + slot * 0.52
            if bar_height:
                canvas.create_rectangle(x0, base_y - bar_height, x1, base_y, fill=ACCENT, outline="")
            day_value = date.fromisoformat(row.day)
            canvas.create_text((x0 + x1) / 2, base_y + 18, text=day_value.strftime("%m/%d"), fill=MUTED, font=("Segoe UI", 9))
            value = f"{ratio:.0%}" if row.posture_samples else "—"
            canvas.create_text((x0 + x1) / 2, max(14, base_y - bar_height - 12),
                               text=value, fill=INK, font=("Segoe UI", 9, "bold"))

    def _refresh_cameras(self) -> None:
        self.camera_combo.configure(values=("正在扫描…",))
        self.camera_var.set("正在扫描…")

        def worker() -> None:
            found = list_available_cameras()
            self.after(0, lambda: self._apply_camera_choices(found))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_camera_choices(self, found: list[tuple[int, str]]) -> None:
        if not any(index == self.settings.camera_index for index, _label in found):
            found.insert(
                0,
                (
                    self.settings.camera_index,
                    f"摄像头 {self.settings.camera_index}（当前）",
                ),
            )
        self.camera_choices = {label: index for index, label in found}
        self.camera_combo.configure(values=list(self.camera_choices))
        current = next((label for label, index in self.camera_choices.items() if index == self.settings.camera_index), list(self.camera_choices)[0])
        self.camera_var.set(current)

    def _show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self) -> None:
        if self.settings.minimize_to_tray and self.tray_available:
            self.withdraw()
            self.notifier.send("坐直助手仍在运行", "可从系统托盘重新打开或退出。")
        else:
            self._really_quit()

    def _really_quit(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.stop_camera()
        if self.camera_thread and self.camera_thread.is_alive():
            self.camera_thread.join(timeout=1)
        self.tray.stop()
        self.pet.shutdown()
        self.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    args, _ = parser.parse_known_args()
    if args.smoke_test:
        from pathlib import Path

        smoke_log = Path.cwd() / "smoke-test.log"
        smoke_log.parent.mkdir(parents=True, exist_ok=True)

        def stage(message: str) -> None:
            with smoke_log.open("a", encoding="utf-8") as output:
                output.write(message + "\n")

        smoke_log.write_text("smoke start\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            stage("before tkinter")
            app = PostureCompanionApp(
                data_dir=Path(directory), enable_camera=False, enable_tray=False
            )
            stage("after tkinter")
            app.geometry("1010x680")
            for page in (app.today_tab, app.posture_tab, app.stats_tab, app.settings_tab):
                app.notebook.select(page)
                app.update()
                if not page.winfo_ismapped():
                    raise RuntimeError("UI smoke test could not open a page")
            app.pet_kind_var.set("狗狗")
            app._update_pet_preview()
            app.pet.configure_pet("dog", True)
            app.pet.show_message("该接杯水了", "drink")
            app._toggle_camera_capture()
            app.update()
            if not (app.camera_paused and app.pet.camera_paused):
                raise RuntimeError("Camera pause did not reach the pet")
            stage("after ui update")
            import mediapipe as mp

            stage("after mediapipe import")
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
            )
            detector = mp.tasks.vision.PoseLandmarker.create_from_options(options)
            stage("after model init")
            detector.close()
            stage("after model close")
            app._really_quit()
            stage("after ui close")
        stage("smoke success")
        os._exit(0)
    app = PostureCompanionApp(start_hidden=args.background)
    app.mainloop()


if __name__ == "__main__":
    main()
