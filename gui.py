"""
Keep → Garmin 图形界面
基于 tkinter，无需额外安装依赖
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 将当前目录加入 path，确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from keep_sync import sync_keep
import keep_sync as _keep_sync
from garmin_upload import upload_gpx_files


class RedirectText:
    """将 print 输出重定向到 tkinter Text 控件"""

    def __init__(self, text_widget: tk.Text):
        self.text_widget = text_widget
        self._stdout = sys.stdout

    def write(self, s: str):
        self._stdout.write(s)
        self.text_widget.insert(tk.END, s)
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks()

    def flush(self):
        self._stdout.flush()


class Keep2GarminApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Keep → Garmin 数据迁移工具")
        self.root.geometry("600x680")
        self.root.minsize(520, 600)

        # 设置样式
        self._setup_style()
        self._build_ui()

        # 重定向 stdout 到日志区
        self.redirect = RedirectText(self.log_text)
        sys.stdout = self.redirect

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        # 配色
        self.BG = "#f5f5f5"
        self.CARD_BG = "#ffffff"
        self.ACCENT = "#FF6B35"  # Keep 品牌橙
        self.ACCENT2 = "#0072CE"  # Garmin 品牌蓝
        self.TEXT = "#333333"
        self.BORDER = "#e0e0e0"

        self.root.configure(bg=self.BG)

        style.configure("Card.TFrame", background=self.CARD_BG, relief="solid", borderwidth=1)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"),
                        background=self.BG, foreground=self.TEXT)
        style.configure("Section.TLabel", font=("Microsoft YaHei UI", 12, "bold"),
                        background=self.CARD_BG, foreground=self.TEXT)
        style.configure("Hint.TLabel", font=("Microsoft YaHei UI", 8),
                        background=self.CARD_BG, foreground="#999")
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Normal.TButton", font=("Microsoft YaHei UI", 10))
        style.configure("Log.TFrame", background="#1e1e1e")

    def _build_ui(self):
        # ── 标题栏 ──
        title_frame = tk.Frame(self.root, bg=self.BG)
        title_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
        ttk.Label(title_frame, text="Keep → Garmin 数据迁移", style="Title.TLabel").pack(
            side=tk.LEFT)
        ttk.Label(title_frame, text="基于 running_page 的 Keep API",
                  font=("Microsoft YaHei UI", 8), background=self.BG,
                  foreground="#999").pack(side=tk.LEFT, padx=(10, 0))

        # ── 主内容区（可滚动） ──
        canvas = tk.Canvas(self.root, bg=self.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=canvas.yview)
        self.content_frame = tk.Frame(canvas, bg=self.BG)

        self.content_frame.bind("<Configure>",
                                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(15, 0), pady=(0, 5))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=(0, 5))

        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Section 1: Keep 账号 ──
        self._make_keep_section()

        # ── Section 2: Garmin 账号 ──
        self._make_garmin_section()

        # ── Section 3: 导出选项 ──
        self._make_options_section()

        # ── Section 4: 操作按钮 ──
        self._make_actions_section()

        # ── Section 5: 日志输出 ──
        self._make_log_section()

    def _make_keep_section(self):
        card = ttk.Frame(self.content_frame, style="Card.TFrame")
        card.pack(fill=tk.X, padx=5, pady=(0, 8))

        header = tk.Frame(card, bg=self.CARD_BG)
        header.pack(fill=tk.X, padx=15, pady=(12, 8))
        ttk.Label(header, text="●  Keep 账号", style="Section.TLabel",
                  foreground=self.ACCENT).pack(side=tk.LEFT)

        form = tk.Frame(card, bg=self.CARD_BG)
        form.pack(fill=tk.X, padx=20, pady=(0, 12))

        ttk.Label(form, text="手机号", background=self.CARD_BG).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 2))
        self.keep_mobile = ttk.Entry(form, width=35, font=("Consolas", 11))
        self.keep_mobile.grid(row=1, column=0, sticky=tk.EW, pady=(0, 8))

        ttk.Label(form, text="密码", background=self.CARD_BG).grid(
            row=2, column=0, sticky=tk.W, pady=(0, 2))
        self.keep_password = ttk.Entry(form, width=35, show="•", font=("Consolas", 11))
        self.keep_password.grid(row=3, column=0, sticky=tk.EW)

        form.columnconfigure(0, weight=1)

    def _make_garmin_section(self):
        card = ttk.Frame(self.content_frame, style="Card.TFrame")
        card.pack(fill=tk.X, padx=5, pady=(0, 8))

        header = tk.Frame(card, bg=self.CARD_BG)
        header.pack(fill=tk.X, padx=15, pady=(12, 8))
        ttk.Label(header, text="●  Garmin Connect 账号", style="Section.TLabel",
                  foreground=self.ACCENT2).pack(side=tk.LEFT)

        form = tk.Frame(card, bg=self.CARD_BG)
        form.pack(fill=tk.X, padx=20, pady=(0, 12))

        ttk.Label(form, text="邮箱", background=self.CARD_BG).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 2))
        self.garmin_email = ttk.Entry(form, width=35, font=("Consolas", 11))
        self.garmin_email.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))

        ttk.Label(form, text="密码", background=self.CARD_BG).grid(
            row=2, column=0, sticky=tk.W, pady=(0, 2))
        self.garmin_password = ttk.Entry(form, width=35, show="•", font=("Consolas", 11))
        self.garmin_password.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))

        self.garmin_cn = tk.BooleanVar(value=True)
        cn_radio = ttk.Radiobutton(form, text="中国区 (connect.garmin.cn)", variable=self.garmin_cn,
                                   value=True)
        cn_radio.grid(row=4, column=0, sticky=tk.W)
        gl_radio = ttk.Radiobutton(form, text="国际区 (connect.garmin.com)", variable=self.garmin_cn,
                                   value=False)
        gl_radio.grid(row=4, column=1, sticky=tk.W)

        form.columnconfigure(0, weight=1)

    def _make_options_section(self):
        card = ttk.Frame(self.content_frame, style="Card.TFrame")
        card.pack(fill=tk.X, padx=5, pady=(0, 8))

        header = tk.Frame(card, bg=self.CARD_BG)
        header.pack(fill=tk.X, padx=15, pady=(12, 8))
        ttk.Label(header, text="●  导出选项", style="Section.TLabel").pack(side=tk.LEFT)

        form = tk.Frame(card, bg=self.CARD_BG)
        form.pack(fill=tk.X, padx=20, pady=(0, 12))

        # 运动类型
        ttk.Label(form, text="运动类型", background=self.CARD_BG).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 4))

        types_frame = tk.Frame(form, bg=self.CARD_BG)
        types_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        self.sport_running = tk.BooleanVar(value=True)
        self.sport_cycling = tk.BooleanVar(value=True)
        self.sport_hiking = tk.BooleanVar(value=True)
        ttk.Checkbutton(types_frame, text="跑步", variable=self.sport_running).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Checkbutton(types_frame, text="骑行", variable=self.sport_cycling).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Checkbutton(types_frame, text="徒步", variable=self.sport_hiking).pack(side=tk.LEFT)

        # 最大数量
        ttk.Label(form, text="最多导出条数（0 = 全部）", background=self.CARD_BG).grid(
            row=2, column=0, sticky=tk.W, pady=(0, 2))
        self.max_count = ttk.Entry(form, width=10, font=("Consolas", 11))
        self.max_count.insert(0, "0")
        self.max_count.grid(row=3, column=0, sticky=tk.W, pady=(0, 8))

        # 输出目录
        ttk.Label(form, text="GPX 输出目录", background=self.CARD_BG).grid(
            row=4, column=0, sticky=tk.W, pady=(0, 2))
        dir_frame = tk.Frame(form, bg=self.CARD_BG)
        dir_frame.grid(row=5, column=0, columnspan=2, sticky=tk.EW)
        self.output_dir = ttk.Entry(dir_frame, font=("Consolas", 11))
        self.output_dir.insert(0, _keep_sync.get_output_dir())
        self.output_dir.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dir_frame, text="浏览...", command=self._browse_dir,
                   style="Normal.TButton", width=8).pack(side=tk.LEFT, padx=(5, 0))

        # Debug 开关
        self.debug_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="调试模式（打印 Keep API 原始响应）",
                        variable=self.debug_mode).grid(
            row=6, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        # 导出格式
        ttk.Label(form, text="导出格式", background=self.CARD_BG).grid(
            row=7, column=0, sticky=tk.W, pady=(10, 2))
        fmt_frame = tk.Frame(form, bg=self.CARD_BG)
        fmt_frame.grid(row=8, column=0, columnspan=2, sticky=tk.W)
        self.export_format = tk.StringVar(value="tcx")
        ttk.Radiobutton(fmt_frame, text="TCX（推荐 Garmin 用户，自动识别跑步/骑行）",
                        variable=self.export_format, value="tcx").pack(anchor=tk.W)
        ttk.Radiobutton(fmt_frame, text="GPX（通用格式，但 Garmin 不自动识别类型）",
                        variable=self.export_format, value="gpx").pack(anchor=tk.W)

        # 日期范围
        ttk.Label(form, text="时间范围（留空=全部）", background=self.CARD_BG).grid(
            row=9, column=0, sticky=tk.W, pady=(10, 2))
        date_frame = tk.Frame(form, bg=self.CARD_BG)
        date_frame.grid(row=10, column=0, columnspan=2, sticky=tk.W)
        ttk.Label(date_frame, text="从", background=self.CARD_BG).pack(side=tk.LEFT)
        self.date_from = ttk.Entry(date_frame, width=12, font=("Consolas", 10))
        self.date_from.pack(side=tk.LEFT, padx=(4, 12))
        self.date_from.insert(0, "2024-01-01")
        ttk.Label(date_frame, text="到", background=self.CARD_BG).pack(side=tk.LEFT)
        self.date_to = ttk.Entry(date_frame, width=12, font=("Consolas", 10))
        self.date_to.pack(side=tk.LEFT, padx=(4, 0))
        # 全部按钮清空日期
        ttk.Button(date_frame, text="全部", width=5,
                   command=lambda: (self.date_from.delete(0, tk.END),
                                    self.date_to.delete(0, tk.END))
                   ).pack(side=tk.LEFT, padx=(10, 0))

        form.columnconfigure(0, weight=1)

    def _make_actions_section(self):
        card = ttk.Frame(self.content_frame, style="Card.TFrame")
        card.pack(fill=tk.X, padx=5, pady=(0, 8))

        btn_frame = tk.Frame(card, bg=self.CARD_BG)
        btn_frame.pack(fill=tk.X, padx=15, pady=15)

        # 三个主要操作按钮
        self.btn_export = tk.Button(
            btn_frame, text="1. 仅导出文件\n(Keep → GPX/TCX)",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=self.ACCENT, fg="white", activebackground="#e55a2b",
            relief=tk.FLAT, cursor="hand2", padx=18, pady=10,
            command=self._run_export_only)
        self.btn_export.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_upload = tk.Button(
            btn_frame, text="2. 仅上传 Garmin\n(GPX/TCX → Connect)",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=self.ACCENT2, fg="white", activebackground="#005fa3",
            relief=tk.FLAT, cursor="hand2", padx=18, pady=10,
            command=self._run_upload_only)
        self.btn_upload.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_all = tk.Button(
            btn_frame, text="3. 一键全流程\n(Keep → Garmin)",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="#2e7d32", fg="white", activebackground="#1b5e20",
            relief=tk.FLAT, cursor="hand2", padx=18, pady=10,
            command=self._run_all)
        self.btn_all.pack(side=tk.LEFT)

        # 进度条
        self.progress = ttk.Progressbar(card, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=15, pady=(0, 15))

    def _make_log_section(self):
        card = ttk.Frame(self.content_frame, style="Card.TFrame")
        card.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 10))

        header = tk.Frame(card, bg=self.CARD_BG)
        header.pack(fill=tk.X, padx=15, pady=(12, 6))
        ttk.Label(header, text="运行日志", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="清空", command=self._clear_log,
                   style="Normal.TButton", width=6).pack(side=tk.RIGHT)

        log_frame = tk.Frame(card, bg="#1e1e1e")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.log_text = tk.Text(
            log_frame, wrap=tk.WORD, height=12,
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
            font=("Consolas", 9), relief=tk.FLAT,
            padx=10, pady=8,
            state=tk.NORMAL)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scroll.set)

        # 日志颜色 tag
        self.log_text.tag_config("error", foreground="#f44747")
        self.log_text.tag_config("ok", foreground="#6a9955")
        self.log_text.tag_config("warn", foreground="#dcdcaa")
        self.log_text.tag_config("info", foreground="#569cd6")

    # ── 辅助方法 ──

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.output_dir.get())
        if d:
            self.output_dir.delete(0, tk.END)
            self.output_dir.insert(0, d)

    def _get_sport_types(self) -> list[str]:
        types = []
        if self.sport_running.get():
            types.append("running")
        if self.sport_cycling.get():
            types.append("cycling")
        if self.sport_hiking.get():
            types.append("hiking")
        return types or ["running"]

    def _set_buttons_state(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_export.configure(state=state)
        self.btn_upload.configure(state=state)
        self.btn_all.configure(state=state)
        if not enabled:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def _log_divider(self, title: str):
        print(f"\n{'=' * 50}")
        print(f"  {title}")
        print(f"{'=' * 50}\n")

    # ── 操作（在后台线程执行）──

    def _run_export_only(self):
        self._set_buttons_state(False)
        self._clear_log()
        t = threading.Thread(target=self._do_export, daemon=True)
        t.start()

    def _run_upload_only(self):
        self._set_buttons_state(False)
        self._clear_log()
        t = threading.Thread(target=self._do_upload, daemon=True)
        t.start()

    def _run_all(self):
        self._set_buttons_state(False)
        self._clear_log()
        t = threading.Thread(target=self._do_all, daemon=True)
        t.start()

    def _do_export(self):
        try:
            _keep_sync.DEBUG = self.debug_mode.get()
            mobile = self.keep_mobile.get().strip()
            password = self.keep_password.get().strip()

            if not mobile or not password:
                messagebox.showwarning("缺少信息", "请填写 Keep 手机号和密码")
                return

            self._log_divider("Step: Keep → GPX 导出")
            sync_keep(
                mobile=mobile,
                password=password,
                output_dir=self.output_dir.get(),
                sport_types=self._get_sport_types(),
                max_count=int(self.max_count.get() or "0"),
                export_format=self.export_format.get(),
                start_date=self.date_from.get().strip(),
                end_date=self.date_to.get().strip(),
            )
        except Exception as e:
            print(f"\n[ERROR] {e}")
            messagebox.showerror("错误", str(e))
        finally:
            self.root.after(0, lambda: self._set_buttons_state(True))

    def _do_upload(self):
        try:
            email = self.garmin_email.get().strip()
            password = self.garmin_password.get().strip()

            if not email or not password:
                messagebox.showwarning("缺少信息", "请填写 Garmin 邮箱和密码")
                return

            self._log_divider("Step: GPX → Garmin Connect 上传")
            upload_gpx_files(
                email=email,
                password=password,
                gpx_dir=self.output_dir.get(),
                is_cn=self.garmin_cn.get(),
            )
        except Exception as e:
            print(f"\n[ERROR] {e}")
            messagebox.showerror("错误", str(e))
        finally:
            self.root.after(0, lambda: self._set_buttons_state(True))

    def _do_all(self):
        try:
            _keep_sync.DEBUG = self.debug_mode.get()
            mobile = self.keep_mobile.get().strip()
            keep_pw = self.keep_password.get().strip()
            email = self.garmin_email.get().strip()
            garmin_pw = self.garmin_password.get().strip()

            if not mobile or not keep_pw:
                messagebox.showwarning("缺少信息", "请填写 Keep 手机号和密码")
                return
            if not email or not garmin_pw:
                messagebox.showwarning("缺少信息", "请填写 Garmin 邮箱和密码")
                return

            # Step 1: Keep → GPX
            self._log_divider("Step 1/2: Keep → GPX 导出")
            files = sync_keep(
                mobile=mobile,
                password=keep_pw,
                output_dir=self.output_dir.get(),
                sport_types=self._get_sport_types(),
                max_count=int(self.max_count.get() or "0"),
                export_format=self.export_format.get(),
                start_date=self.date_from.get().strip(),
                end_date=self.date_to.get().strip(),
            )

            if not files:
                print("\n[WARN] 没有导出任何 GPX 文件，流程终止。")
                return

            # Step 2: GPX → Garmin
            self._log_divider("Step 2/2: GPX → Garmin Connect 上传")
            upload_gpx_files(
                email=email,
                password=garmin_pw,
                gpx_dir=self.output_dir.get(),
                is_cn=self.garmin_cn.get(),
            )

            print("\n[DONE] 全流程完成！请同步手表查看数据。")
        except Exception as e:
            print(f"\n[ERROR] {e}")
            messagebox.showerror("错误", str(e))
        finally:
            self.root.after(0, lambda: self._set_buttons_state(True))


def main():
    root = tk.Tk()
    app = Keep2GarminApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
