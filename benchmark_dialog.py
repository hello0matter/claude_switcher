import copy
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from benchmark import BENCHMARK_TASKS, run_route_benchmark


class BenchmarkDialog(tk.Toplevel):
    """Run the same short capability suite against one or more routes."""

    def __init__(self, parent, entries):
        super().__init__(parent)
        self.title("能力体检 / 智商对比（非临床 IQ 测量）")
        self.geometry("900x560")
        self.minsize(760, 430)
        counts = {}
        self.entries = []
        for original in entries:
            entry = dict(original)
            base_name = entry.get("name", "未命名")
            counts[base_name] = counts.get(base_name, 0) + 1
            entry["name"] = (
                base_name if counts[base_name] == 1 else f"{base_name} #{counts[base_name]}"
            )
            self.entries.append(entry)
        self.results = {}
        self.running = False
        self.closed = False
        self.baseline_var = tk.StringVar(value=self._default_baseline())
        self.status_var = tk.StringVar(value="未开始；不会修改路线或 Session")
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _default_baseline(self):
        for entry in self.entries:
            route = entry["route"]
            text = (entry["name"] + " " + str(route.get("base_url") or "")).lower()
            if "官方" in text or "openai.com" in text or "anthropic.com" in text:
                return entry["name"]
        return "不设置官方基线"

    def _build_ui(self):
        intro = (
            f"固定 {len(BENCHMARK_TASKS)} 题：算术、规律、逻辑、代码、约束和指令遵循。"
            "每条路线发送 6 次短请求，按返回的 FINAL 答案计分；不是科学 IQ 分数。"
        )
        tk.Label(self, text=intro, anchor="w", justify="left", fg="#555").pack(fill="x", padx=12, pady=(10, 4))
        controls = tk.Frame(self)
        controls.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(controls, text="比较基线：").pack(side="left")
        names = ["不设置官方基线"] + [entry["name"] for entry in self.entries]
        baseline_box = ttk.Combobox(controls, textvariable=self.baseline_var, values=names, state="readonly", width=30)
        baseline_box.pack(side="left", padx=4)
        baseline_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        tk.Button(controls, text="开始能力体检（每条路线 6 题）", command=self._start, bg="#1565C0", fg="white", relief="flat", pady=5).pack(side="left", padx=10)
        tk.Label(controls, textvariable=self.status_var, fg="#666").pack(side="right")

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        columns = ("route", "model", "score", "difference", "latency", "tokens", "status")
        self.tree = ttk.Treeview(body, columns=columns, show="headings")
        headings = {
            "route": "路线",
            "model": "模型",
            "score": "得分",
            "difference": "相对基线",
            "latency": "总耗时 ms",
            "tokens": "实际 tokens",
            "status": "状态",
        }
        widths = {"route": 190, "model": 170, "score": 80, "difference": 90, "latency": 100, "tokens": 100, "status": 130}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.tree.bind("<Double-Button-1>", self._show_detail)
        tk.Label(
            self,
            text="官方差距只有在你选了真实官方 API/官方路线作为基线时才有意义；中转站可能改写、截断或限制答案。",
            anchor="w", justify="left", fg="#8a5a00",
        ).pack(fill="x", padx=12, pady=(0, 10))

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        baseline = self.baseline_var.get()
        baseline_score = None
        for entry in self.entries:
            result = self.results.get(entry["name"])
            if result and entry["name"] == baseline:
                baseline_score = result["percent"]
        for entry in self.entries:
            result = self.results.get(entry["name"])
            if not result:
                values = (entry["name"], entry["route"].get("model", ""), "未测试", "", "", "", "")
            else:
                diff = ""
                if baseline_score is not None:
                    diff = f"{result['percent'] - baseline_score:+d} 分"
                values = (
                    entry["name"], entry["route"].get("model", ""),
                    f"{result['score']}/{result['total']} ({result['percent']}%)",
                    diff, result["latency_ms"], result["tokens"] if result["tokens"] is not None else "未返回", "完成",
                )
            self.tree.insert("", "end", iid=entry["name"], values=values)

    def _start(self):
        if self.running:
            return
        self.running = True
        self.results.clear()
        self._refresh()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        for offset, entry in enumerate(self.entries, 1):
            if self.closed:
                break
            self.after(0, self.status_var.set, f"测试中 {offset}/{len(self.entries)}：{entry['name']}")
            result = run_route_benchmark(copy.deepcopy(entry["route"]), entry["kind"])
            self.results[entry["name"]] = result
            self.after(0, self._refresh)
        self.running = False
        if not self.closed:
            self.after(0, self.status_var.set, "测试完成；双击路线可查看每道题")

    def _show_detail(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        name = selection[0]
        result = self.results.get(name)
        if not result:
            return
        lines = [f"路线：{name}", f"得分：{result['score']}/{result['total']} ({result['percent']}%)", ""]
        for task, item in zip(BENCHMARK_TASKS, result["results"]):
            status = "通过" if item["passed"] else "失败"
            answer = item["answer"] or "无"
            detail = f"；{item['error']}" if item["error"] else ""
            lines.append(f"[{status}] {task['category']}：期望 {task['expected']}，返回 {answer}{detail}")
        messagebox.showinfo("能力体检明细", "\n".join(lines), parent=self)

    def _close(self):
        self.closed = True
        self.destroy()
