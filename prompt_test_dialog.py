"""Batch prompt-test window. One window lists every selected route."""

import os
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import prompt_gallery
import prompt_probe


class PromptSettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("编辑路线提示词测试")
        self.geometry("760x520")
        self.minsize(640, 420)
        self.saved = None
        settings = prompt_probe.load_prompt_settings()
        self.dir_var = tk.StringVar(value=settings["output_dir"])
        self.hidden_var = tk.BooleanVar(value=settings["hidden"])

        tk.Label(self, text="输出目录", anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        tk.Entry(self, textvariable=self.dir_var).pack(fill="x", padx=12)
        tk.Label(
            self,
            text=prompt_probe.PLACEHOLDER_HELP,
            fg="#666",
            wraplength=720,
            justify="left",
        ).pack(fill="x", padx=12, pady=(8, 2))
        self.text = scrolledtext.ScrolledText(self, wrap="word", height=16)
        self.text.pack(fill="both", expand=True, padx=12, pady=4)
        self.text.insert("1.0", settings["prompt"])
        tk.Checkbutton(
            self,
            text="批量测试默认隐匿运行（不弹每个路线的控制台；模型自己开的命令窗口仍可能闪一下）",
            variable=self.hidden_var,
            anchor="w",
            justify="left",
            wraplength=720,
        ).pack(fill="x", padx=12, pady=4)
        buttons = tk.Frame(self)
        buttons.pack(pady=(4, 10))
        tk.Button(buttons, text="保存", command=self._save, bg="#1565C0", fg="white", relief="flat", padx=14).pack(side="left", padx=4)
        tk.Button(buttons, text="恢复默认", command=self._reset).pack(side="left", padx=4)
        tk.Button(buttons, text="取消", command=self.destroy).pack(side="left", padx=4)
        self.transient(parent)
        self.grab_set()

    def _reset(self):
        self.dir_var.set(prompt_probe.DEFAULT_OUTPUT_DIR)
        self.hidden_var.set(True)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", prompt_probe.DEFAULT_PROMPT)

    def _save(self):
        try:
            self.saved = prompt_probe.save_prompt_settings(
                {
                    "output_dir": self.dir_var.get(),
                    "prompt": self.text.get("1.0", "end").strip(),
                    "hidden": self.hidden_var.get(),
                }
            )
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.destroy()


class PromptTestDialog(tk.Toplevel):
    def __init__(self, parent, routes, command_builder):
        super().__init__(parent)
        self.title("路线提示词测试")
        self.geometry("980x620")
        self.minsize(820, 480)
        self.routes = list(routes)
        self.command_builder = command_builder
        self._stop = False
        self._running = False
        self._process = None
        self.rows = []
        settings = prompt_probe.load_prompt_settings()
        self.hidden_var = tk.BooleanVar(value=settings["hidden"])
        self.binary_var = tk.StringVar(value="codex")

        bar = tk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(bar, text="程序").pack(side="left")
        ttk.Combobox(
            bar,
            textvariable=self.binary_var,
            values=("codex", "codexx"),
            state="readonly",
            width=10,
        ).pack(side="left", padx=(4, 10))
        tk.Checkbutton(bar, text="隐匿运行", variable=self.hidden_var).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="开始测试", command=self.start, bg="#1f6f9f", fg="white", relief="flat").pack(side="left", padx=2)
        tk.Button(bar, text="停止", command=self.stop).pack(side="left", padx=2)
        tk.Button(bar, text="编辑提示词", command=self.edit_prompt).pack(side="left", padx=2)
        tk.Button(bar, text="打开输出目录", command=self.open_dir).pack(side="left", padx=2)
        tk.Button(bar, text="打开对比页", command=self.open_gallery).pack(side="left", padx=2)
        self.status_var = tk.StringVar(value=f"已选 {len(self.routes)} 条。开始后按顺序跑，结果都列在这个窗口里。")
        tk.Label(self, textvariable=self.status_var, anchor="w", justify="left", wraplength=940).pack(fill="x", padx=10)

        columns = ("name", "model", "effort", "wire", "status", "file")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=12)
        headings = {
            "name": "路线",
            "model": "模型",
            "effort": "强度",
            "wire": "形式",
            "status": "状态",
            "file": "文件",
        }
        widths = {"name": 180, "model": 140, "effort": 70, "wire": 90, "status": 140, "file": 320}
        for key, label in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=widths[key], anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())
        self.detail = scrolledtext.ScrolledText(self, height=9, wrap="word")
        self.detail.pack(fill="both", expand=False, padx=10, pady=(0, 8))
        self.detail.insert(
            "1.0",
            "隐匿运行适合批量：不给每条路线弹一个 Codex 窗口，输出写在下面。\n"
            "不隐匿时会打开控制台，方便看模型有没有自己写文件。\n"
            "默认提示词禁止 git commit / push。输出目录不是 git 仓库时，模型也不该去碰别的仓库。\n"
            "批量测试只用本次进程参数，不改写 ~/.codex/config.toml。密钥不会显示在这个窗口里。",
        )
        for route in self.routes:
            item = self.tree.insert(
                "",
                "end",
                values=(
                    route.get("name") or "未命名",
                    route.get("model") or "(无模型)",
                    route.get("reasoning_effort") or "默认",
                    prompt_probe.wire_suffix_label(route.get('wire_api')),
                    "等待",
                    "",
                ),
            )
            self.rows.append({"item": item, "route": route, "detail": "", "path": ""})
        self.protocol("WM_DELETE_WINDOW", self._close)

    def edit_prompt(self):
        if self._running:
            messagebox.showwarning("提示", "测试进行中，先停止再改提示词。", parent=self)
            return
        PromptSettingsDialog(self)

    def _output_root(self):
        return Path(prompt_probe.load_prompt_settings()["output_dir"])

    def open_dir(self):
        self._open_path(self._output_root(), "打不开目录")

    def open_gallery(self):
        root = self._output_root()
        try:
            url = prompt_gallery.serve_gallery(root)
        except OSError as exc:
            messagebox.showerror("打不开对比页", str(exc), parent=self)
            return
        if not webbrowser.open(url):
            self._open_path(root / "index.html", "打不开对比页")

    def _open_path(self, path, title):
        try:
            path = Path(path)
            if path.suffix.lower() != ".html":
                path.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)  # noqa: S606 - user asked to open the comparison page
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror(title, str(exc), parent=self)

    def start(self):
        if self._running:
            return
        settings = prompt_probe.load_prompt_settings()
        if prompt_probe.prompt_mentions_git_publish(settings["prompt"]) and not messagebox.askyesno(
            "提示词包含提交或推送",
            "当前提示词里有提交/推送字样。模型可能会改 git 仓库。\n仍要开始吗？",
            parent=self,
        ):
            return
        self._running = True
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop = True
        self.status_var.set("正在停止当前进程。")
        self._kill_process()

    def _close(self):
        self._stop = True
        self._kill_process()
        self.destroy()

    def _kill_process(self):
        process = self._process
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()

    def _run(self):
        total = len(self.rows)
        for offset, row in enumerate(self.rows, start=1):
            if self._stop:
                self.after(0, self._mark_remaining, offset - 1, "已停止")
                break
            self.after(0, self.status_var.set, f"测试中 {offset}/{total}：{row['route'].get('name') or '未命名'}")
            self._run_one(row)
        self.after(0, self._finish)

    def _run_one(self, row):
        route = dict(row["route"])
        route["wire_api"] = prompt_probe.normalize_wire_suffix(route.get("wire_api"), default="/responses")
        route["base_url"] = str(route.get("base_url") or "").strip().rstrip("/")
        problem = prompt_probe.provider_id_problem(route)
        if problem:
            self._finish_row(row, "已跳过", "", problem)
            return
        if not str(route.get("model") or "").strip():
            self._finish_row(row, "已跳过", "", "这条路线没有模型名，无法做提示词测试。")
            return
        settings = prompt_probe.load_prompt_settings()
        directory = Path(settings["output_dir"])
        try:
            output_path = prompt_gallery.allocate_prompt_output(directory, route)
        except OSError as exc:
            self._finish_row(row, "失败", "", f"无法创建输出目录：{exc}")
            return
        prompt = prompt_probe.render_prompt(settings["prompt"], route, output_path)
        hidden = bool(self.hidden_var.get())
        try:
            command = self.command_builder(self.binary_var.get(), route, prompt, output_path.parent, hidden)
        except Exception as exc:
            self._finish_row(row, "失败", str(output_path), str(exc))
            return
        self._set_status(row, "运行中", str(output_path))
        try:
            process = subprocess.Popen(command, cwd=str(directory), **self._popen_kwargs(hidden))
        except OSError as exc:
            self._finish_row(row, "失败", str(output_path), str(exc))
            return
        self._process = process
        output = self._read_process(process, hidden, output_path, row)
        code = process.poll()
        self._process = None
        output = self._scrub(route, output)
        if self._stop:
            status = "已停止"
        elif output_path.is_file() and output_path.stat().st_size > 0:
            status = "已生成文件"
        elif code == 0:
            status = "进程结束但没有文件"
        else:
            status = f"失败（退出码 {code}）"
        detail = self._public_detail(prompt, output_path, output, code)
        try:
            prompt_gallery.refresh_galleries(directory)
        except OSError:
            pass
        self._finish_row(row, status, str(output_path), detail)

    def _popen_kwargs(self, hidden):
        if os.name != "nt":
            if hidden:
                return {
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.STDOUT,
                    "text": True,
                    "encoding": "utf-8",
                    "errors": "replace",
                }
            return {}
        if hidden:
            return {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "creationflags": subprocess.CREATE_NO_WINDOW,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            }
        return {"creationflags": subprocess.CREATE_NEW_CONSOLE}

    def _read_process(self, process, hidden, output_path=None, row=None):
        """Wait for the child while surfacing progress and stopping once its file settles.

        Codex sometimes keeps its wrapper process alive after the sample HTML is
        complete. Waiting ten minutes left rows stuck on 运行中, so watch the output
        file, report elapsed time, and end the wait after it stops changing.
        """
        timeout_seconds = 600
        settle_seconds = 20
        started = time.monotonic()
        deadline = started + timeout_seconds
        last_size = None
        stable_since = None
        output = ""
        while True:
            try:
                output, _stderr = process.communicate(timeout=2)
                break
            except subprocess.TimeoutExpired:
                elapsed = int(time.monotonic() - started)
                if row is not None:
                    self._set_status(row, f"运行中 {elapsed}s", str(output_path or ""))
                if output_path is not None and Path(output_path).is_file():
                    try:
                        size = Path(output_path).stat().st_size
                    except OSError:
                        size = 0
                    if size > 0 and size == last_size:
                        stable_since = stable_since or time.monotonic()
                        if time.monotonic() - stable_since >= settle_seconds:
                            self._kill_process()
                            try:
                                output, _stderr = process.communicate(timeout=10)
                            except subprocess.TimeoutExpired:
                                pass
                            return (output or "") + "\n文件已生成，进程仍在运行，已结束等待。"
                    else:
                        last_size = size
                        stable_since = None
                if time.monotonic() >= deadline:
                    self._kill_process()
                    try:
                        output, _stderr = process.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        pass
                    if not hidden:
                        return "超时，已终止。"
                    return ((output or "") + "\n超时，已终止。")[-4000:]
        return (output or "")[-4000:]

    def _scrub(self, route, output):
        text = str(output or "")
        key = str(route.get("api_key") or "")
        if key:
            text = text.replace(key, "****")
        return text

    def _public_detail(self, prompt, output_path, output, code):
        shown = output.replace("\r", "")
        return (
            f"目标文件：{output_path}\n退出码：{code}\n\n"
            f"提示词：\n{prompt}\n\n输出摘要：\n{shown or '(隐匿关闭时不抓控制台输出，请看文件是否生成)'}"
        )

    def _finish_row(self, row, status, path, detail):
        row["detail"] = detail
        row["path"] = path
        self._set_status(row, status, path)

    def _set_status(self, row, status, path):
        def apply():
            if not self.winfo_exists():
                return
            route = row["route"]
            self.tree.item(
                row["item"],
                values=(
                    route.get("name") or "未命名",
                    route.get("model") or "",
                    route.get("reasoning_effort") or "默认",
                    prompt_probe.wire_suffix_label(route.get('wire_api')),
                    status,
                    path,
                ),
            )

        self.after(0, apply)

    def _mark_remaining(self, start, status):
        for row in self.rows[start:]:
            current = self.tree.item(row["item"], "values")
            if current and current[4] == "等待":
                self._set_status(row, status, "")

    def _finish(self):
        self._running = False
        if self.winfo_exists() and not self._stop:
            self.status_var.set("本轮结束。对比页已按天更新，点“打开对比页”用滚轮看哪个站点更好。")

    def _show_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        row = next((item for item in self.rows if item["item"] == selected[0]), None)
        if row is None or not row["detail"]:
            return
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", row["detail"])
