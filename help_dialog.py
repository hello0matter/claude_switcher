"""Compact help for the switcher's manual route tools."""

import tkinter as tk
from tkinter import scrolledtext


HELP_TEXT = """这些功能怎么用

1. 模型测试表格
测试当前路线下各模型能否完成一次轻量 API 请求。它主要判断模型名、Key、接口格式和基本连通性，不代表长对话一定稳定。

2. 多选路线资费对比
在路线列表中按住 Ctrl 逐个多选，按住 Shift 连续多选。使用同一个任务分别测试后，到各站资费网页查看实际扣费并填入，软件会计算最低价格和相对倍数。蓝色锁表示当前真正写入配置的路线。

3. 手动检测中转站是否投毒
发送随机验证码和私有标记，检查响应注入、标记泄露、跨域跳转、工具劫持、内容改写和流截断。这是黑盒风险检测，不能证明中转站绝对安全。

4. 手动检测路线是否异常
检查本次请求是否遇到 DNS、代理连接、HTTP、响应流或内容完整性异常。异常不等于投毒，例如 HTTP 403 可能只是 Cloudflare 拒绝当前出口 IP。
投毒检测和异常检测都支持 Ctrl 多选、Shift 连选。结果列在同一个窗口里，不再每条弹一个对话框。

5. 路线提示词测试
在 Codex 专区选中一条或多条路线后使用。它会让 Codex 或 Codexx 写一个鹈鹕骑自行车的 HTML，文件名包含时间、API 主域名、模型、推理强度和接口形式。默认隐匿运行，输出列在同一个窗口。提示词和输出目录可在“编辑提示词”或全局设置里改。默认提示词禁止 git commit / push。
默认并发 3 路，可改成 1–6 路；站点限流或机器吃紧时用 1–2 路。“停止”会结束所有正在运行的进程，不会只停一条。每行会显示已运行秒数；文件生成并稳定 20 秒后会主动结束等待，避免一直卡在“运行中”。
Codex CLI 只支持 Responses 接口。wire API 选 /completions 或 /chat/completions 的路线会被明确跳过，请改成 /responses 再做提示词测试；直接 HTTP 模型测试仍可使用原来的后缀。部分中转网关会拒绝 web_search 工具，所以提示词测试只在本次进程参数里加 web_search="disabled"，不会改写 ~/.codex/config.toml。
样本按天放在输出目录下，例如 2026-10-23\时间_站点_模型_强度_responses.html。每天有 index.html，输出目录根上的 index.html 是全部日期的对比页。卡片默认较小，页面上有“预览大小”滑块可实时缩放；同一站点排在一起，用来直接看哪个站更好。从软件里点“打开对比页”时会在本机临时端口动态生成页面，增删样本后刷新即可看到最新结果。

6. 启动时执行提示词测试
勾选后，启动 Codex 或 Codexx 会先弹确认窗，再打开可见控制台。只启动当前高亮路线。wire API 是追加在 API 地址末尾的路径。Codex 只能用 /responses；/chat/completions 等后缀仅用于本软件直连模型测试。选（不追加）只影响软件直连 URL，Codex 仍然按 Responses 请求。API 地址按原样保存，不会自动删掉已有后缀。
路线编辑里的“Web 搜索”默认开启，并按路线保存。关闭时会写入 web_search = "disabled"；重新开启时会移除这一行，让 Codex 回到默认开启。切换 Mimo 等不支持 web_search 工具的网关时请关闭；下次再切回这条路线仍会保持关闭。

API 地址、wire 后缀和 Codex 配置文件的关系

路线窗口里的“API 地址”和“wire API”是两个部分。软件直连测试时会把后缀接在地址后面；写 Codex 配置时则分开写：
  API 地址 https://api.xiaomimimo.com/v1
  wire API /responses
  实际请求 https://api.xiaomimimo.com/v1/responses
  config.toml 里 base_url = "https://api.xiaomimimo.com/v1"，wire_api = "responses"

Codex CLI 0.154 只支持 Responses 接口，并且会自己在 base_url 后面拼 /responses。因此 API 地址建议只填到 /v1，wire 选 /responses。不要把 /responses 也塞进 API 地址，否则可能变成 /responses/responses。也不要给 Codex 写 wire_api = "chat" 或 /completions：Codex 已经移除 chat 接口，写了也不会走那个端点。
/completions 和 /chat/completions 只适合“模型测试表格”等本软件直连请求；路线提示词测试会跳过并提示改成 /responses。小米 Mimo 的 mimo-v2.6-pro 和 mimo-v2.6-flash 已验证使用 https://api.xiaomimimo.com/v1 + /responses 可以正常完成 Codex 请求；原来 Flash 路线的 /completions 已改为 /responses。
提示词测试还会在本次进程参数里加 web_search="disabled"，避免部分网关因为不认识 web_search 工具而直接报错。这个开关只影响本次测试；正常启动 Codex 时使用的是路线编辑里保存的“Web 搜索”开关。

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
