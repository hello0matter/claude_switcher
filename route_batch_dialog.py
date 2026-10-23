"""Shared result window for multi-selected route probes."""

import threading
import tkinter as tk
from tkinter import ttk


class RouteBatchDialog(tk.Toplevel):
    """Run one probe function across selected routes and list every result."""

    def __init__(self, parent, title, routes, runner, ok_verdicts):
        super().__init__(parent)
        self.title(title)
        self.geometry("860x520")
        self.minsize(720, 420)
        self.routes = list(routes)
        self.runner = runner
        self.ok_verdicts = set(ok_verdicts)
        self._stop = False
        self._running = False
        self.rows = []

        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=(8, 4))
        self.status_var = tk.StringVar(value=f"准备检测 {len(self.routes)} 条路线")
        tk.Label(top, textvariable=self.status_var, anchor="w").pack(side="left", fill="x", expand=True)
        self.stop_button = tk.Button(top, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="right")

        columns = ("name", "verdict", "latency", "summary")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=12)
        self.tree.heading("name", text="路线")
        self.tree.heading("verdict", text="结论")
        self.tree.heading("latency", text="耗时")
        self.tree.heading("summary", text="摘要")
        self.tree.column("name", width=220, anchor="w")
        self.tree.column("verdict", width=90, anchor="w")
        self.tree.column("latency", width=80, anchor="w")
        self.tree.column("summary", width=420, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

        self.detail = tk.Text(self, height=8, wrap="word")
        self.detail.pack(fill="both", expand=False, padx=10, pady=(0, 8))
        self.detail.insert("1.0", "选择一行可查看完整说明。多选路线会按顺序检测，不会同时打满所有中转站。")
        self.detail.config(state="disabled")

        for route in self.routes:
            item = self.tree.insert(
                "",
                "end",
                values=(route.get("name") or "未命名", "等待", "", ""),
            )
            self.rows.append({"item": item, "route": route, "result": None})
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(150, self.start)

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop = False
        self.stop_button.config(state="normal")
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop = True
        self.status_var.set("正在停止，当前这一条结束后不再继续。")

    def _close(self):
        self._stop = True
        self.destroy()

    def _run(self):
        total = len(self.rows)
        for offset, row in enumerate(self.rows, start=1):
            if self._stop:
                self.after(0, self._mark_remaining, offset - 1, "已停止")
                break
            name = row["route"].get("name") or "未命名"
            self.after(0, self.status_var.set, f"检测中 {offset}/{total}：{name}")
            self.after(0, self._set_row, row, "检测中", "", "")
            try:
                result = self.runner(row["route"])
            except Exception as exc:
                result = {
                    "verdict": "error",
                    "summary": "检测过程出错",
                    "details": [str(exc)],
                    "latency_ms": "",
                }
            row["result"] = result
            latency = f"{result.get('latency_ms')} ms" if result.get("latency_ms") else ""
            self.after(
                0,
                self._set_row,
                row,
                result.get("verdict") or "",
                latency,
                result.get("summary") or "",
            )
        self.after(0, self._finish)

    def _mark_remaining(self, start, verdict):
        for row in self.rows[start:]:
            if row["result"] is None:
                self._set_row(row, verdict, "", "")

    def _set_row(self, row, verdict, latency, summary):
        if not self.winfo_exists():
            return
        name = row["route"].get("name") or "未命名"
        self.tree.item(row["item"], values=(name, verdict, latency, summary))

    def _finish(self):
        if not self.winfo_exists():
            return
        self._running = False
        self.stop_button.config(state="disabled")
        if self._stop:
            self.status_var.set("已停止。")
            return
        failed = 0
        for row in self.rows:
            result = row["result"] or {}
            if result.get("verdict") not in self.ok_verdicts:
                failed += 1
        if failed:
            self.status_var.set(f"完成。{failed}/{len(self.rows)} 条不是通过结论，点行查看详情。")
        else:
            self.status_var.set(f"完成。{len(self.rows)} 条均为通过结论。")

    def _show_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        row = next((item for item in self.rows if item["item"] == selected[0]), None)
        if row is None or not row["result"]:
            return
        result = row["result"]
        details = "\n".join(result.get("details") or [])
        text = (
            f"{row['route'].get('name') or '未命名'}\n"
            f"{result.get('summary') or ''}\n\n{details}"
        )
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.config(state="disabled")
