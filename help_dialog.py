"""Compact help for the switcher's manual route tools."""

import tkinter as tk
from tkinter import scrolledtext


HELP_TEXT = """四个功能怎么用

1. 模型测试表格
测试当前路线下各模型能否完成一次轻量 API 请求。它主要判断模型名、Key、接口格式和基本连通性，不代表长对话一定稳定。

2. 多选路线资费对比
在路线列表中按住 Ctrl 逐个多选，按住 Shift 连续多选。使用同一个任务分别测试后，到各站资费网页查看实际扣费并填入，软件会计算最低价格和相对倍数。蓝色锁表示当前真正写入配置的路线。

3. 手动检测中转站是否投毒
发送随机验证码和私有标记，检查响应注入、标记泄露、跨域跳转、工具劫持、内容改写和流截断。这是黑盒风险检测，不能证明中转站绝对安全。

4. 手动检测路线是否异常
检查本次请求是否遇到 DNS、代理连接、HTTP、响应流或内容完整性异常。异常不等于投毒，例如 HTTP 403 可能只是 Cloudflare 拒绝当前出口 IP。

本软件网络设置

右上角“全局设置”只控制本软件发出的模型测试和路线检测请求。它不会修改 Codex、Claude、Proxifier、Windows环境变量或任何 CLI 配置。

SOCKS5（远程 DNS）会让代理服务器解析目标域名，可绕过公司 DNS 无法解析造成的 getaddrinfo failed / WinError 11001 / 11002。

启用本软件代理后，建议关闭 Proxifier 中针对 python.exe/pythonw.exe 的代理规则，或确保 127.0.0.1 直连，避免同一个请求被重复代理。直连模式仅表示本软件不主动配置代理，Proxifier 仍然可以在 Socket 层接管。

WinError 10061 表示本软件设置的代理地址或端口没有程序监听，通常是 Clash 未启动、端口不对，或选错了 HTTP/SOCKS 类型。
"""


class HelpDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("功能帮助")
        self.geometry("720x570")
        self.minsize(620, 480)
        text = scrolledtext.ScrolledText(
            self,
            wrap="word",
            font=("Microsoft YaHei UI", 10),
            padx=12,
            pady=10,
        )
        text.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        text.insert("1.0", HELP_TEXT)
        text.config(state="disabled")
        tk.Button(self, text="关闭", command=self.destroy, width=12).pack(pady=(4, 10))
        self.grab_set()
