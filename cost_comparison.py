"""Manual, persistent route cost comparison UI."""

import json
import os
import re
import tempfile
import tkinter as tk
import urllib.parse
import webbrowser
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import messagebox


COST_DATA_FILE = Path.home() / ".claude_switcher_costs.json"


def comparison_key(item):
    return ":".join(
        (
            str(item.get("kind") or "route"),
            str(item.get("route_id") or item.get("name") or "unknown"),
            str(item.get("model") or "default"),
        )
    )


def default_usage_url(base_url):
    parsed = urllib.parse.urlparse(str(base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/usage", "", "", ""))


def load_cost_data():
    if COST_DATA_FILE.exists():
        try:
            data = json.loads(COST_DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("entries"), dict):
                return data
        except (OSError, ValueError, TypeError):
            pass
    return {"entries": {}}


def save_cost_data(data):
    COST_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=COST_DATA_FILE.name + ".", dir=COST_DATA_FILE.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        Path(temp_name).replace(COST_DATA_FILE)
    finally:
        temp = Path(temp_name)
        if temp.exists():
            temp.unlink()


def parse_cost(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    match = re.fullmatch(r"[￥¥$]?\s*(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def cost_ratio_labels(values):
    texts = [str(value or "").strip() for value in values]
    parsed = [parse_cost(value) for value in values]
    positive = [value for value in parsed if value is not None and value > 0]
    minimum = min(positive) if positive else None
    labels = []
    for text, value in zip(texts, parsed):
        if not text:
            labels.append("待填写")
        elif value is None:
            labels.append("请输入数字")
        elif value == 0:
            labels.append("0（网页未扣费）")
        elif minimum is None:
            labels.append("")
        elif value == minimum:
            labels.append("最低 · 1.00×")
        else:
            labels.append(f"{value / minimum:.2f}×")
    return labels


class CostComparisonDialog(tk.Toplevel):
    def __init__(self, parent, items):
        super().__init__(parent)
        self.title("路线实际扣费对比")
        self.geometry(f"1120x{min(740, 230 + len(items) * 42)}")
        self.minsize(940, 340)
        self.items = items
        self.data = load_cost_data()
        self.rows = []
        self._build_ui()
        self._update_ratios()
        self.grab_set()

    def _build_ui(self):
        tk.Label(
            self,
            text=(
                "用同一个任务分别测试这些路线，再到各站资费网页查看实际扣费并填入。"
                "Ctrl 可逐个多选，Shift 可连续多选；扣费数字必须使用同一单位。"
            ),
            fg="#555",
            justify="left",
            wraplength=900,
        ).pack(fill="x", padx=12, pady=(10, 6))

        table = tk.Frame(self)
        table.pack(fill="both", expand=True, padx=12)
        headers = ("锁定路线", "模型", "资费/用量网页", "实际扣费", "相对价格")
        for column, text in enumerate(headers):
            tk.Label(table, text=text, font=("", 9, "bold"), anchor="w").grid(
                row=0, column=column, padx=4, pady=(0, 4), sticky="ew"
            )
        table.columnconfigure(0, weight=1, minsize=180)
        table.columnconfigure(1, weight=1, minsize=160)
        table.columnconfigure(2, weight=3, minsize=430)
        table.columnconfigure(3, weight=0, minsize=110)
        table.columnconfigure(4, weight=0, minsize=120)

        entries = self.data.setdefault("entries", {})
        for row_index, item in enumerate(self.items, 1):
            saved = entries.get(comparison_key(item), {})
            url_var = tk.StringVar(
                value=saved.get("usage_url") or default_usage_url(item.get("base_url"))
            )
            cost_var = tk.StringVar(value=saved.get("actual_cost", ""))
            ratio_var = tk.StringVar()
            locked = bool(item.get("locked"))
            name = ("🔒 " if locked else "") + str(item.get("name") or "未命名")
            name_label = tk.Label(
                table,
                text=name,
                font=("", 9, "bold" if locked else "normal"),
                anchor="w",
            )
            if locked:
                name_label.config(fg="#1565C0")
            name_label.grid(row=row_index, column=0, padx=4, pady=4, sticky="ew")
            tk.Label(table, text=item.get("model") or "（默认）", anchor="w").grid(
                row=row_index, column=1, padx=4, pady=4, sticky="ew"
            )
            url_frame = tk.Frame(table)
            url_frame.grid(row=row_index, column=2, padx=4, pady=4, sticky="ew")
            url_frame.columnconfigure(0, weight=1)
            tk.Entry(url_frame, textvariable=url_var).grid(row=0, column=0, sticky="ew")
            tk.Button(
                url_frame,
                text="打开",
                command=lambda variable=url_var: self._open_url(variable),
                width=5,
            ).grid(row=0, column=1, padx=(4, 0))
            cost_entry = tk.Entry(table, textvariable=cost_var, width=12)
            cost_entry.grid(row=row_index, column=3, padx=4, pady=4, sticky="ew")
            cost_entry.bind("<KeyRelease>", lambda _event: self._update_ratios())
            tk.Label(table, textvariable=ratio_var, anchor="w").grid(
                row=row_index, column=4, padx=4, pady=4, sticky="ew"
            )
            self.rows.append((item, url_var, cost_var, ratio_var))

        buttons = tk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=10)
        tk.Button(
            buttons,
            text="全部打开资费网页",
            command=self._open_all,
            bg="#1565C0",
            fg="white",
            relief="flat",
            padx=10,
            pady=5,
        ).pack(side="left")
        tk.Button(
            buttons,
            text="保存并计算对比",
            command=self._save,
            bg="#2e7d32",
            fg="white",
            relief="flat",
            padx=10,
            pady=5,
        ).pack(side="right", padx=(4, 0))
        tk.Button(buttons, text="关闭", command=self.destroy, padx=10, pady=4).pack(
            side="right"
        )

    def _open_url(self, variable):
        url = variable.get().strip()
        if not url:
            messagebox.showwarning("没有网页地址", "请先填写该路线的资费或用量网页。", parent=self)
            return
        if urllib.parse.urlparse(url).scheme not in {"http", "https"}:
            messagebox.showwarning("网页地址错误", "网页地址必须以 http:// 或 https:// 开头。", parent=self)
            return
        webbrowser.open(url)

    def _open_all(self):
        opened = 0
        for _item, url_var, _cost_var, _ratio_var in self.rows:
            url = url_var.get().strip()
            if url and urllib.parse.urlparse(url).scheme in {"http", "https"}:
                webbrowser.open(url)
                opened += 1
        if not opened:
            messagebox.showwarning("没有网页地址", "请先填写至少一个资费或用量网页。", parent=self)

    def _update_ratios(self):
        labels = cost_ratio_labels([row[2].get() for row in self.rows])
        for row, label in zip(self.rows, labels):
            row[3].set(label)

    def _save(self):
        entries = self.data.setdefault("entries", {})
        for item, url_var, cost_var, _ratio_var in self.rows:
            entries[comparison_key(item)] = {
                "usage_url": url_var.get().strip(),
                "actual_cost": cost_var.get().strip(),
            }
        try:
            save_cost_data(self.data)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self._update_ratios()
        messagebox.showinfo("已保存", "资费网页和实际扣费已保存。", parent=self)
