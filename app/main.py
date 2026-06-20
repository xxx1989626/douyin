import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import LikeEngine
from stats import Stats
from app_config import load_config, save_config


# ---------- 主题 ----------
DARK_BG = "#1a1d23"
DARK_CARD = "#252830"
DARK_CARD_HOVER = "#2f333d"
DARK_BORDER = "#3a3f4a"
TEXT_PRIMARY = "#e8eaf0"
TEXT_SECONDARY = "#9ba3b5"
ACCENT = "#ff2d55"
ACCENT_HOVER = "#ff4d70"
GREEN = "#34c759"
BLUE = "#0a84ff"
PURPLE = "#bf5af2"
GOLD = "#ff9500"


class DouyinApp:
    def __init__(self):
        self.config = load_config()
        self.stats = Stats()
        self.like_pos = [None, None]

        threshold = self.config.get("auto_like_threshold", 0.60)
        cooldown = 3.0
        self.engine = LikeEngine(
            on_log=self._on_log,
            on_state_update=self._on_state_update,
            threshold=threshold,
            cooldown=cooldown,
        )

        self.running = False
        self.monitor_thread = None
        self._log_messages = []

        self._build_ui()

    # ---------- UI 构建 ----------
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("抖音自动点赞助手")
        self.root.geometry("1100x720")
        self.root.configure(bg=DARK_BG)
        self.root.minsize(980, 640)

        # 样式
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=DARK_BG)
        style.configure("Card.TFrame", background=DARK_CARD)
        style.configure("TLabel", background=DARK_BG, foreground=TEXT_PRIMARY, font=("Microsoft YaHei", 10))
        style.configure("Card.TLabel", background=DARK_CARD, foreground=TEXT_PRIMARY, font=("Microsoft YaHei", 10))
        style.configure("Title.TLabel", background=DARK_CARD, foreground=TEXT_PRIMARY, font=("Microsoft YaHei", 14, "bold"))
        style.configure("Sub.TLabel", background=DARK_CARD, foreground=TEXT_SECONDARY, font=("Microsoft YaHei", 9))
        style.configure("Big.TLabel", background=DARK_CARD, foreground=ACCENT, font=("Segoe UI", 28, "bold"))
        style.configure("Green.TLabel", background=DARK_CARD, foreground=GREEN, font=("Segoe UI", 22, "bold"))
        style.configure("Blue.TLabel", background=DARK_CARD, foreground=BLUE, font=("Segoe UI", 22, "bold"))
        style.configure("Gold.TLabel", background=DARK_CARD, foreground=GOLD, font=("Segoe UI", 22, "bold"))
        style.configure("Purple.TLabel", background=DARK_CARD, foreground=PURPLE, font=("Segoe UI", 22, "bold"))
        style.configure("TButton", background=DARK_CARD, foreground=TEXT_PRIMARY, padding=(16, 8), font=("Microsoft YaHei", 10), borderwidth=0)
        style.map("TButton", background=[("active", DARK_CARD_HOVER)])
        style.configure("Accent.TButton", background=ACCENT, foreground="white", padding=(20, 10), font=("Microsoft YaHei", 10, "bold"), borderwidth=0)
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER)])
        style.configure("TProgressbar", troughcolor=DARK_BORDER, background=ACCENT, bordercolor=DARK_CARD, lightcolor=ACCENT, darkcolor=ACCENT, thickness=14)
        style.configure("TNotebook", background=DARK_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=DARK_CARD, foreground=TEXT_SECONDARY, padding=(20, 10), font=("Microsoft YaHei", 10))
        style.map("TNotebook.Tab", background=[("selected", DARK_BG)], foreground=[("selected", TEXT_PRIMARY)])
        style.configure("Treeview", background=DARK_CARD, foreground=TEXT_PRIMARY, fieldbackground=DARK_CARD, borderwidth=0, rowheight=32, font=("Microsoft YaHei", 9))
        style.configure("Treeview.Heading", background=DARK_CARD_HOVER, foreground=TEXT_PRIMARY, font=("Microsoft YaHei", 9, "bold"), borderwidth=0)
        style.map("Treeview", background=[("selected", DARK_CARD_HOVER)])

        # 顶部栏
        header = tk.Frame(self.root, bg=DARK_BG, height=64)
        header.pack(fill="x", pady=(16, 8), padx=20)
        header.pack_propagate(False)

        title_label = tk.Label(
            header,
            text="🎬 抖音自动点赞助手",
            bg=DARK_BG,
            fg=TEXT_PRIMARY,
            font=("Microsoft YaHei", 20, "bold"),
        )
        title_label.pack(side="left")

        status_dot = tk.Label(header, text="●", bg=DARK_BG, fg=TEXT_SECONDARY, font=("Segoe UI", 12))
        status_dot.pack(side="right", padx=(0, 4))
        status_text = tk.Label(header, text="未启动", bg=DARK_BG, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 10))
        status_text.pack(side="right")
        self.status_dot = status_dot
        self.status_text = status_text

        # Tab 控制
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        tab_main = ttk.Frame(notebook, style="TFrame")
        tab_stats = ttk.Frame(notebook, style="TFrame")
        tab_settings = ttk.Frame(notebook, style="TFrame")

        notebook.add(tab_main, text="  实时监控  ")
        notebook.add(tab_stats, text="  数据统计  ")
        notebook.add(tab_settings, text="  设置  ")

        self._build_main_tab(tab_main)
        self._build_stats_tab(tab_stats)
        self._build_settings_tab(tab_settings)

        # 窗口关闭
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_main_tab(self, parent):
        # 左侧：当前视频信息 + 进度
        left = tk.Frame(parent, bg=DARK_BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        # 卡片：当前视频
        card_video = tk.Frame(left, bg=DARK_CARD, highlightthickness=1, highlightbackground=DARK_BORDER)
        card_video.pack(fill="x", pady=(0, 12))
        self._round_style(card_video)

        header = tk.Frame(card_video, bg=DARK_CARD)
        header.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(header, text="当前视频", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 14, "bold")).pack(side="left")
        tk.Label(header, text="实时同步抖音窗口", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9)).pack(side="right")

        body = tk.Frame(card_video, bg=DARK_CARD)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # 博主
        row1 = tk.Frame(body, bg=DARK_CARD)
        row1.pack(fill="x", pady=4)
        tk.Label(row1, text="博主", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9), width=6, anchor="w").pack(side="left")
        self.lbl_author = tk.Label(row1, text="—", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 13, "bold"))
        self.lbl_author.pack(side="left", padx=(12, 0))

        # 标题
        row2 = tk.Frame(body, bg=DARK_CARD)
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="标题", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9), width=6, anchor="w").pack(side="left")
        self.lbl_title = tk.Label(row2, text="—", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 11), wraplength=520, justify="left")
        self.lbl_title.pack(side="left", padx=(12, 0), anchor="w")

        # 播放进度
        row3 = tk.Frame(body, bg=DARK_CARD)
        row3.pack(fill="x", pady=(12, 4))
        tk.Label(row3, text="时间", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9), width=6, anchor="w").pack(side="left")
        self.lbl_time = tk.Label(row3, text="0:00 / 0:00", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Segoe UI", 12))
        self.lbl_time.pack(side="left", padx=(12, 0))

        # 进度条
        row4 = tk.Frame(body, bg=DARK_CARD)
        row4.pack(fill="x", pady=(4, 4))
        self.progress = ttk.Progressbar(row4, mode="determinate", maximum=100, style="TProgressbar")
        self.progress.pack(fill="x", side="left", expand=True)
        self.lbl_progress = tk.Label(row4, text="0%", bg=DARK_CARD, fg=ACCENT, font=("Segoe UI", 12, "bold"), width=8, anchor="e")
        self.lbl_progress.pack(side="right", padx=(10, 0))

        # 点赞状态
        row5 = tk.Frame(body, bg=DARK_CARD)
        row5.pack(fill="x", pady=(8, 0))
        tk.Label(row5, text="状态", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9), width=6, anchor="w").pack(side="left")
        self.lbl_like_status = tk.Label(row5, text="未点赞", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 11, "bold"))
        self.lbl_like_status.pack(side="left", padx=(12, 0))

        # 底部控制按钮
        controls = tk.Frame(card_video, bg=DARK_CARD)
        controls.pack(fill="x", padx=20, pady=(8, 20))

        self.btn_start = tk.Button(
            controls,
            text="▶ 开始监控",
            bg=ACCENT,
            fg="white",
            font=("Microsoft YaHei", 11, "bold"),
            padx=24,
            pady=10,
            borderwidth=0,
            cursor="hand2",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            command=self._toggle_monitor,
        )
        self.btn_start.pack(side="left")

        tk.Label(controls, text="· 达到阈值自动点赞 · 不影响正常操作", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9)).pack(side="left", padx=16, pady=12)

        # 本次会话统计卡片
        card_session = tk.Frame(left, bg=DARK_CARD, highlightthickness=1, highlightbackground=DARK_BORDER)
        card_session.pack(fill="both", expand=True, pady=(0, 0))

        header2 = tk.Frame(card_session, bg=DARK_CARD)
        header2.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(header2, text="本次会话", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 14, "bold")).pack(side="left")
        self.lbl_session_start = tk.Label(header2, text="", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9))
        self.lbl_session_start.pack(side="right")

        body2 = tk.Frame(card_session, bg=DARK_CARD)
        body2.pack(fill="both", expand=True, padx=20, pady=16)

        # 四个统计项
        s1 = tk.Frame(body2, bg=DARK_CARD)
        s1.pack(side="left", fill="both", expand=True)
        tk.Label(s1, text="已点赞", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 10)).pack(anchor="w")
        self.lbl_session_likes = tk.Label(s1, text="0", bg=DARK_CARD, fg=ACCENT, font=("Segoe UI", 30, "bold"))
        self.lbl_session_likes.pack(anchor="w", pady=(2, 0))
        tk.Label(s1, text="个视频", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9)).pack(anchor="w")

        s2 = tk.Frame(body2, bg=DARK_CARD)
        s2.pack(side="left", fill="both", expand=True)
        tk.Label(s2, text="已观看", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 10)).pack(anchor="w")
        self.lbl_session_videos = tk.Label(s2, text="0", bg=DARK_CARD, fg=BLUE, font=("Segoe UI", 30, "bold"))
        self.lbl_session_videos.pack(anchor="w", pady=(2, 0))
        tk.Label(s2, text="个视频", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9)).pack(anchor="w")

        s3 = tk.Frame(body2, bg=DARK_CARD)
        s3.pack(side="left", fill="both", expand=True)
        tk.Label(s3, text="运行时长", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 10)).pack(anchor="w")
        self.lbl_session_duration = tk.Label(s3, text="0s", bg=DARK_CARD, fg=GOLD, font=("Segoe UI", 24, "bold"))
        self.lbl_session_duration.pack(anchor="w", pady=(2, 0))

        s4 = tk.Frame(body2, bg=DARK_CARD)
        s4.pack(side="left", fill="both", expand=True)
        tk.Label(s4, text="点赞坐标", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 10)).pack(anchor="w")
        self.lbl_like_pos = tk.Label(s4, text="—,—", bg=DARK_CARD, fg=GREEN, font=("Segoe UI", 18, "bold"))
        self.lbl_like_pos.pack(anchor="w", pady=(2, 0))

        # 右侧：日志
        right = tk.Frame(parent, bg=DARK_BG)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        card_log = tk.Frame(right, bg=DARK_CARD, highlightthickness=1, highlightbackground=DARK_BORDER)
        card_log.pack(fill="both", expand=True)

        header3 = tk.Frame(card_log, bg=DARK_CARD)
        header3.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(header3, text="运行日志", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 14, "bold")).pack(side="left")

        self.log_text = tk.Text(
            card_log,
            bg=DARK_CARD,
            fg=TEXT_PRIMARY,
            font=("Consolas", 10),
            borderwidth=0,
            highlightthickness=0,
            insertbackground=TEXT_PRIMARY,
            wrap="word",
            height=12,
        )
        self.log_text.pack(fill="both", expand=True, padx=20, pady=12)
        self.log_text.configure(state="disabled")

        self._log("系统已就绪，点击「开始监控」开始运行")

    def _build_stats_tab(self, parent):
        # 顶部四个累计卡片
        card_row = tk.Frame(parent, bg=DARK_BG)
        card_row.pack(fill="x", pady=(0, 12))

        cards = [
            ("累计点赞", lambda: str(self.stats.get_total_likes()), ACCENT),
            ("累计观看", lambda: str(self.stats.get_total_videos()), BLUE),
            ("累计时长", lambda: f"{self.stats.get_total_hours():.1f}h", GOLD),
            ("使用次数", lambda: str(self.stats.get_total_sessions()), PURPLE),
        ]
        for title, val_fn, color in cards:
            card = tk.Frame(card_row, bg=DARK_CARD, highlightthickness=1, highlightbackground=DARK_BORDER)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12))
            self._add_stat_card(card, title, val_fn, color)

        # 热门博主
        card_authors = tk.Frame(parent, bg=DARK_CARD, highlightthickness=1, highlightbackground=DARK_BORDER)
        card_authors.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=(0, 0))
        tk.Label(card_authors, text="  热门博主 TOP", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        tk.Label(card_authors, text="  你点赞最多的博主", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9)).pack(anchor="w", padx=16)

        self.tree_authors = ttk.Treeview(
            card_authors,
            columns=("rank", "author", "count"),
            show="headings",
            height=10,
        )
        self.tree_authors.heading("rank", text="#")
        self.tree_authors.heading("author", text="博主")
        self.tree_authors.heading("count", text="点赞数")
        self.tree_authors.column("rank", width=50, anchor="center")
        self.tree_authors.column("author", width=200, anchor="w")
        self.tree_authors.column("count", width=80, anchor="center")
        self.tree_authors.pack(fill="both", expand=True, padx=20, pady=16)

        # 最近点赞记录
        card_recent = tk.Frame(parent, bg=DARK_CARD, highlightthickness=1, highlightbackground=DARK_BORDER)
        card_recent.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=(0, 0))
        tk.Label(card_recent, text="  最近点赞记录", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        tk.Label(card_recent, text="  最新 200 条点赞视频", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9)).pack(anchor="w", padx=16)

        self.tree_recent = ttk.Treeview(
            card_recent,
            columns=("time", "author", "title"),
            show="headings",
            height=10,
        )
        self.tree_recent.heading("time", text="时间")
        self.tree_recent.heading("author", text="博主")
        self.tree_recent.heading("title", text="标题")
        self.tree_recent.column("time", width=140, anchor="center")
        self.tree_recent.column("author", width=120, anchor="w")
        self.tree_recent.column("title", width=280, anchor="w")
        self.tree_recent.pack(fill="both", expand=True, padx=20, pady=16)

        self._refresh_stats()

    def _build_settings_tab(self, parent):
        card = tk.Frame(parent, bg=DARK_CARD, highlightthickness=1, highlightbackground=DARK_BORDER)
        card.pack(fill="x", pady=(0, 12))

        tk.Label(card, text="参数设置", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", padx=20, pady=(20, 4))
        tk.Label(card, text="修改后自动生效", bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 9)).pack(anchor="w", padx=20)

        body = tk.Frame(card, bg=DARK_CARD)
        body.pack(fill="x", padx=20, pady=20)

        # 自动点赞阈值
        row1 = tk.Frame(body, bg=DARK_CARD)
        row1.pack(fill="x", pady=8)
        tk.Label(row1, text="自动点赞阈值", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 10), width=18, anchor="w").pack(side="left")
        self.threshold_var = tk.IntVar(value=int(self.config.get("auto_like_threshold", 0.60) * 100))
        scale = tk.Scale(
            row1,
            from_=20,
            to=90,
            orient="horizontal",
            variable=self.threshold_var,
            bg=DARK_CARD,
            fg=TEXT_PRIMARY,
            highlightthickness=0,
            troughcolor=DARK_BORDER,
            activebackground=ACCENT,
            font=("Microsoft YaHei", 9),
            command=lambda v: self._on_threshold_change(),
        )
        scale.pack(side="left", fill="x", expand=True, padx=(10, 10))
        self.lbl_threshold_val = tk.Label(row1, text=f"{self.threshold_var.get()}%", bg=DARK_CARD, fg=ACCENT, font=("Microsoft YaHei", 11, "bold"))
        self.lbl_threshold_val.pack(side="right")

        # 检查间隔
        row2 = tk.Frame(body, bg=DARK_CARD)
        row2.pack(fill="x", pady=8)
        tk.Label(row2, text="检查间隔(秒)", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 10), width=18, anchor="w").pack(side="left")
        self.interval_var = tk.DoubleVar(value=self.config.get("check_interval", 0.8))
        scale2 = tk.Scale(
            row2,
            from_=0.3,
            to=3.0,
            resolution=0.1,
            orient="horizontal",
            variable=self.interval_var,
            bg=DARK_CARD,
            fg=TEXT_PRIMARY,
            highlightthickness=0,
            troughcolor=DARK_BORDER,
            activebackground=ACCENT,
            font=("Microsoft YaHei", 9),
            command=lambda v: self._on_interval_change(),
        )
        scale2.pack(side="left", fill="x", expand=True, padx=(10, 10))
        self.lbl_interval_val = tk.Label(row2, text=f"{self.interval_var.get():.1f}s", bg=DARK_CARD, fg=ACCENT, font=("Microsoft YaHei", 11, "bold"))
        self.lbl_interval_val.pack(side="right")

        # 窗口关键词
        row3 = tk.Frame(body, bg=DARK_CARD)
        row3.pack(fill="x", pady=8)
        tk.Label(row3, text="窗口关键词", bg=DARK_CARD, fg=TEXT_PRIMARY, font=("Microsoft YaHei", 10), width=18, anchor="w").pack(side="left")
        self.keyword_var = tk.StringVar(value=self.config.get("window_title_keyword", "抖音"))
        entry = tk.Entry(
            row3,
            textvariable=self.keyword_var,
            bg=DARK_BG,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            font=("Microsoft YaHei", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=DARK_BORDER,
            highlightcolor=ACCENT,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(10, 0), ipady=6)

        tk.Button(
            body,
            text="保存设置",
            bg=ACCENT,
            fg="white",
            font=("Microsoft YaHei", 10, "bold"),
            padx=24,
            pady=8,
            borderwidth=0,
            cursor="hand2",
            activebackground=ACCENT_HOVER,
            command=self._save_settings,
        ).pack(anchor="e", pady=(20, 0))

    def _round_style(self, frame):
        pass

    def _add_stat_card(self, card, title, val_fn, color):
        tk.Label(card, text=title, bg=DARK_CARD, fg=TEXT_SECONDARY, font=("Microsoft YaHei", 10)).pack(anchor="w", padx=20, pady=(20, 0))
        lbl = tk.Label(card, text=val_fn(), bg=DARK_CARD, fg=color, font=("Segoe UI", 36, "bold"))
        lbl.pack(anchor="w", padx=20, pady=(4, 0))
        lbl._get_fn = val_fn
        self._stat_labels = getattr(self, "_stat_labels", []) + [lbl]

    # ---------- 事件 ----------
    def _on_log(self, msg):
        self._log_messages.append(msg)
        try:
            self.root.after(0, self._flush_logs)
        except Exception:
            pass

    def _flush_logs(self):
        if not self._log_messages:
            return
        msgs = self._log_messages
        self._log_messages = []
        try:
            self.log_text.configure(state="normal")
            for m in msgs:
                ts = time.strftime("%H:%M:%S")
                prefix = "✓" if "已点赞" in m else ("ℹ" if "新视频" in m else "·")
                self.log_text.insert("end", f"[{ts}] {prefix} {m}\n")
            self.log_text.see("end")
            # 限制行数
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 200:
                self.log_text.delete("1.0", f"{lines-200}.0")
            self.log_text.configure(state="disabled")
        except Exception:
            pass

    def _log(self, msg):
        self._on_log(msg)

    def _on_state_update(self, **kw):
        pass

    def _toggle_monitor(self):
        if self.running:
            self._stop_monitor()
        else:
            self._start_monitor()

    def _start_monitor(self):
        if not self.engine.find_window(
            self.config.get("window_title_keyword", "抖音"),
            self.config.get("window_class", "Chrome_WidgetWin_1"),
        ):
            messagebox.showwarning("未找到窗口", "没有检测到抖音窗口，请先打开抖音桌面版")
            return

        # 先获取一次视频信息
        if self.engine.ctrl is not None:
            author, title, lp = self.engine.get_video_info()
            if author:
                self.engine.current_author = author
                self.engine.current_title = title if title else "无标题"
            if lp and lp[0] is not None:
                self.engine.like_x, self.engine.like_y = lp[0], lp[1]

        self.stats.record_session_start()
        self.running = True
        self.btn_start.configure(text="⏹ 停止监控", bg="#6c7280", activebackground="#7e8494")
        self.status_dot.configure(fg=GREEN)
        self.status_text.configure(text="运行中", fg=GREEN)
        self.lbl_session_start.configure(text=f"开始时间 {self.stats.session_start}")

        self._log("监控已启动，开始检测视频进度")

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        # UI 刷新线程
        threading.Thread(target=self._ui_update_loop, daemon=True).start()

    def _stop_monitor(self):
        self.running = False
        self.stats.record_session_end()
        self.btn_start.configure(text="▶ 开始监控", bg=ACCENT, activebackground=ACCENT_HOVER)
        self.status_dot.configure(fg=TEXT_SECONDARY)
        self.status_text.configure(text="已停止", fg=TEXT_SECONDARY)
        self._log("监控已停止")

    def _monitor_loop(self):
        interval = self.config.get("check_interval", 0.8)
        last_like_count = 0
        last_watch_count = 0
        while self.running:
            try:
                self.engine.tick_once()

                if self.engine.like_count > last_like_count:
                    last_like_count = self.engine.like_count
                    self.stats.record_like(self.engine.current_author, self.engine.current_title)
                    self.root.after(0, self._refresh_stats)

                if self.engine.watch_count > last_watch_count:
                    last_watch_count = self.engine.watch_count
                    self.stats.record_video()
                    self.root.after(0, self._refresh_stats)

            except Exception as e:
                self._log(f"错误: {e}")

            time.sleep(interval)

    def _ui_update_loop(self):
        while True:
            try:
                self.root.after(0, self._update_ui)
            except Exception:
                return
            time.sleep(0.5)

    def _update_ui(self):
        try:
            author = self.engine.current_author or "—"
            title = self.engine.current_title or "—"
            self.lbl_author.configure(text=author)
            self.lbl_title.configure(text=title)

            cur_s = self.engine.cur_sec or 0
            total_s = self.engine.total_sec or 0
            cur_str = f"{cur_s//60}:{cur_s%60:02d}"
            total_str = f"{total_s//60}:{total_s%60:02d}"
            self.lbl_time.configure(text=f"{cur_str} / {total_str}")

            pct = int(self.engine.progress * 100) if total_s > 0 else 0
            self.progress["value"] = pct
            self.lbl_progress.configure(text=f"{pct}%")

            if self.engine.tracker.liked_for_current:
                self.lbl_like_status.configure(text="✓ 已点赞", fg=GREEN)
            else:
                self.lbl_like_status.configure(text="等待中...", fg=TEXT_SECONDARY)

            self.lbl_session_likes.configure(text=str(self.engine.like_count))
            self.lbl_session_videos.configure(text=str(self.engine.watch_count))
            self.lbl_session_duration.configure(text=self.stats.get_session_duration())

            if self.engine.like_x is not None:
                self.lbl_like_pos.configure(text=f"{self.engine.like_x},{self.engine.like_y}")
            else:
                self.lbl_like_pos.configure(text="计算中")
        except Exception as e:
            self._log(f"UI更新错误: {e}")

    def _refresh_stats(self):
        try:
            # 累计卡片：重新设置标签
            for lbl in getattr(self, "_stat_labels", []):
                try:
                    lbl.configure(text=lbl._get_fn())
                except Exception:
                    pass

            # 热门博主
            for item in self.tree_authors.get_children():
                self.tree_authors.delete(item)
            authors = self.stats.get_top_authors(10)
            for idx, (author, count) in enumerate(authors, 1):
                self.tree_authors.insert("", "end", values=(idx, author, count))

            # 最近记录
            for item in self.tree_recent.get_children():
                self.tree_recent.delete(item)
            recent = self.stats.get_recent_videos(20)
            for v in recent:
                self.tree_recent.insert("", "end", values=(v.get("time", ""), v.get("author", "—"), v.get("title", "—")))
        except Exception:
            pass

    def _on_threshold_change(self):
        self.lbl_threshold_val.configure(text=f"{self.threshold_var.get()}%")

    def _on_interval_change(self):
        self.lbl_interval_val.configure(text=f"{self.interval_var.get():.1f}s")

    def _save_settings(self):
        self.config["auto_like_threshold"] = self.threshold_var.get() / 100.0
        self.config["check_interval"] = float(self.interval_var.get())
        self.config["window_title_keyword"] = self.keyword_var.get().strip() or "抖音"
        save_config(self.config)
        self.engine.tracker.threshold = self.config["auto_like_threshold"]
        messagebox.showinfo("保存成功", "设置已保存并生效")

    def _on_close(self):
        if self.running:
            self.running = False
            self.stats.record_session_end()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DouyinApp()
    app.run()
