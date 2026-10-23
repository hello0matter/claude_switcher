"""Day folders and scrollable comparison pages for prompt-test HTML files."""

import functools
import hashlib
import html
import http.server
import re
import threading
from datetime import datetime
from pathlib import Path

import prompt_probe


_DAY_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STAMP = re.compile(r"^\d{8}-\d{6}$")
_COLORS = ("#1565C0", "#2E7D32", "#C62828", "#6A1B9A", "#EF6C00", "#00838F", "#5D4037", "#AD1457")


def day_name(when=None):
    return (when or datetime.now()).strftime("%Y-%m-%d")


_ALLOCATE_LOCK = threading.Lock()


def allocate_prompt_output(root, route, when=None):
    """Put one sample in a day folder. Comparison pages are written separately."""
    moment = when or datetime.now()
    day = Path(root) / day_name(moment)
    with _ALLOCATE_LOCK:
        day.mkdir(parents=True, exist_ok=True)
        return prompt_probe.unique_output_path(day, prompt_probe.prompt_filename(route, moment))


def parse_sample_name(filename):
    stem = Path(filename).stem
    parts = stem.split("_")
    if len(parts) >= 5 and _STAMP.fullmatch(parts[0]):
        return {
            "stamp": parts[0],
            "host": parts[1],
            "model": "_".join(parts[2:-2]) or "nomodel",
            "effort": parts[-2],
            "wire": parts[-1],
        }
    return {"stamp": "", "host": stem, "model": "", "effort": "", "wire": ""}


def _host_color(host):
    digest = hashlib.sha256(str(host).encode("utf-8")).digest()[0]
    return _COLORS[digest % len(_COLORS)]


def _sample_rows(directory):
    rows = []
    if not directory.is_dir():
        return rows
    for path in directory.glob("*.html"):
        if path.name.lower() == "index.html":
            continue
        info = parse_sample_name(path.name)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        info.update({"path": path, "name": path.name, "size": size})
        rows.append(info)
    rows.sort(key=lambda item: (item["stamp"], item["name"]), reverse=True)
    return rows


def collect_days(root):
    root = Path(root)
    days = []
    if not root.exists():
        return days
    for child in sorted([item for item in root.iterdir() if item.is_dir() and _DAY_DIR.fullmatch(item.name)], reverse=True):
        days.append({"label": child.name, "folder": child.name, "rows": _sample_rows(child)})
    loose = _sample_rows(root)
    if loose:
        days.append({"label": "未按天归档", "folder": "", "rows": loose})
    return days


def _group_sites(rows):
    sites = []
    index = {}
    for row in rows:
        host = row["host"] or "未知站点"
        if host not in index:
            index[host] = {"host": host, "color": _host_color(host), "rows": []}
            sites.append(index[host])
        index[host]["rows"].append(row)
    sites.sort(key=lambda item: item["host"])
    return sites


def _card_html(row, href, color):
    meta = [
        ("模型", row["model"] or "未知模型"),
        ("强度", row["effort"] or "-"),
        ("形式", row["wire"] or "-"),
        ("时间", row["stamp"]),
        ("大小", f"{row['size'] // 1024} KB"),
    ]
    meta_html = "".join(
        f'<span class="meta-item"><em>{html.escape(label)}</em>{html.escape(value)}</span>'
        for label, value in meta
        if value
    )
    title = html.escape(row["host"] or row["name"])
    return f"""
<article class="card" data-host="{html.escape(row['host'])}" style="--site:{color}">
  <a class="frame" href="{html.escape(href)}" title="{title}">
    <iframe loading="lazy" src="{html.escape(href)}" title="{title}" tabindex="-1"></iframe>
    <div class="overlay"></div>
  </a>
  <div class="info">
    <div class="row1"><strong>{title}</strong><a href="{html.escape(href)}" target="_blank">打开原图</a></div>
    <div class="meta">{meta_html}</div>
  </div>
</article>
"""


def _page(title, days, home_href, current_folder):
    total = sum(len(day["rows"]) for day in days)
    site_count = len({row["host"] for day in days for row in day["rows"] if row["host"]})
    hosts = sorted({row["host"] for day in days for row in day["rows"] if row["host"]})

    def host_button(host=""):
        label = host or "全部"
        style = f" style=\"--dot:{_host_color(host)}\"" if host else ""
        return f'<button type="button" class="chip host-chip" data-host="{html.escape(host)}"{style}>{html.escape(label)}</button>'

    def day_chip(day):
        href = "#loose" if not day["folder"] else (f"{day['folder']}/index.html" if not current_folder else (
            "index.html" if day["folder"] == current_folder else f"../{day['folder']}/index.html"
        ))
        return f'<a class="chip" href="{html.escape(href)}">{html.escape(day["label"])} <b>{len(day["rows"])}</b></a>'

    chips = host_button("") + "".join(host_button(host) for host in hosts)
    day_chips = "".join(day_chip(day) for day in days)
    sections = []
    for day in days:
        blocks = []
        for site in _group_sites(day["rows"]):
            cards = []
            for row in site["rows"]:
                href = row["name"] if current_folder or not day["folder"] else f"{day['folder']}/{row['name']}"
                cards.append(_card_html(row, href, site["color"]))
            blocks.append(
                f'<section class="site"><h2><i style="background:{site["color"]}"></i>{html.escape(site["host"])}'
                f'<small>{len(site["rows"])} 个作品</small></h2>'
                f'<div class="track">{"".join(cards)}</div></section>'
            )
        if blocks:
            anchor = "loose" if not day["folder"] else day["label"]
            sections.append(f'<section class="day" id="{html.escape(anchor)}"><h1>{html.escape(day["label"])}</h1>{"".join(blocks)}</section>')
    body = "".join(sections) or '<p class="empty">还没有样本。跑一次路线提示词测试后，回到这里刷新。</p>'
    home = f'<a class="chip" href="{html.escape(home_href)}">全局对比</a>' if home_href else ""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
* {{ box-sizing: border-box; }}
:root {{ --card-w: 220px; --frame-h: 165px; --scale: .2444; }}
body {{ margin: 0; background: #f6f7fb; color: #1f2329; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
.top {{ position: sticky; top: 0; z-index: 9; max-height: 46vh; overflow-y: auto; background: rgba(255,255,255,.94); backdrop-filter: blur(8px); border-bottom: 1px solid #e5e7eb; padding: 16px 28px 12px; }}
.top h1 {{ margin: 0; font-size: 30px; letter-spacing: 1px; }}
.top h1 b {{ color: #ff7d29; }}
.top p {{ margin: 8px 0 12px; color: #6b7280; font-size: 14px; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.chip {{ display: inline-flex; gap: 6px; align-items: center; padding: 6px 14px; border: 1px solid #d8dbe3; border-radius: 999px; background: #fff; color: #374151; text-decoration: none; font-size: 13px; cursor: pointer; font-family: inherit; }}
.chip b {{ color: #9ca3af; font-weight: 500; }}
.chip:hover {{ border-color: #ff7d29; color: #ff7d29; }}
.chip.active {{ background: #1f2329; border-color: #1f2329; color: #fff; }}
.chip.active b {{ color: #bbb; }}
.host-chip::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--dot, #ccc); }}
.stats {{ display: flex; gap: 26px; margin-top: 14px; }}
.stats div {{ font-size: 13px; color: #6b7280; }}
.stats strong {{ display: block; font-size: 22px; color: #1f2329; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin-top: 12px; padding-top: 10px; border-top: 1px dashed #e5e7eb; }}
.size {{ display: flex; align-items: center; gap: 8px; font-size: 13px; color: #4b5563; }}
.size input[type="range"] {{ width: 180px; accent-color: #ff7d29; }}
.badge {{ font-size: 12px; color: #9ca3af; }}
.note {{ margin: 10px 28px 0; padding: 10px 14px; border: 1px solid #f1c40f; border-radius: 10px; background: #fffbea; color: #7a5b00; font-size: 13px; }}
main {{ padding: 8px 28px 48px; max-width: 1600px; }}
.day h1 {{ margin: 26px 0 6px; font-size: 26px; }}
.site h2 {{ display: flex; gap: 10px; align-items: center; margin: 20px 0 12px; font-size: 19px; }}
.site h2 i {{ width: 10px; height: 10px; border-radius: 50%; }}
.site h2 small {{ color: #9ca3af; font-weight: 400; font-size: 13px; }}
.track {{ display: flex; gap: 18px; overflow-x: auto; padding: 2px 2px 14px; scroll-snap-type: x proximity; }}
.track::-webkit-scrollbar {{ height: 8px; }}
.track::-webkit-scrollbar-thumb {{ background: #d4d7de; border-radius: 4px; }}
.card {{ flex: 0 0 var(--card-w); scroll-snap-align: start; background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; overflow: hidden; box-shadow: 0 2px 10px rgba(15,23,42,.05); }}
.card:hover {{ box-shadow: 0 8px 24px rgba(15,23,42,.12); }}
.frame {{ position: relative; display: block; height: var(--frame-h); overflow: hidden; background: #fff; }}
.frame iframe {{ position: absolute; top: 0; left: 0; width: 900px; height: 675px; border: 0; background: #fff; transform: scale(var(--scale)); transform-origin: top left; pointer-events: none; }}
.overlay {{ position: absolute; inset: 0; }}
.info {{ padding: 10px 12px 12px; border-top: 1px solid #f0f1f4; }}
.row1 {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
.row1 strong {{ font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.row1 a {{ color: #ff7d29; font-size: 12px; text-decoration: none; }}
.meta {{ display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 8px; }}
.meta-item {{ font-size: 12px; color: #4b5563; }}
.meta-item em {{ font-style: normal; color: #9ca3af; margin-right: 3px; }}
.hidden {{ display: none !important; }}
.empty {{ padding: 40px; color: #6b7280; }}
</style>
</head>
<body>
<div class="top">
  <h1>鹈鹕<b>测智</b></h1>
  <p>同一个提示词，投喂给不同的模型站点，看看谁真的会画鹈鹕骑自行车。</p>
  <div class="stats"><div><strong>{total}</strong>作品</div><div><strong>{site_count}</strong>站点</div><div><strong>{len(days)}</strong>日期</div></div>
  <div class="chips">{home}{chips}{day_chips}</div>
  <div class="controls">
    <label class="size">预览大小 <input id="size" type="range" min="160" max="460" step="10" value="220"> <b id="size-label">220px</b></label>
    <label class="size"><input id="auto" type="checkbox" checked> 自动刷新</label>
    <button type="button" class="chip" id="refresh">立即刷新</button>
    <span class="badge">生成于 {stamp}</span>
  </div>
</div>
<div id="file-note" class="note hidden">当前打开的是本地静态文件，目录变化不会自动出现。请从软件里点“打开对比页”使用动态版本。</div>
<main>{body}</main>
<script>
const SIZE_KEY = "pelican-preview-width";
const FILTER_KEY = "pelican-filter-host";
const AUTO_KEY = "pelican-auto-refresh";
const root = document.documentElement;
const slider = document.getElementById("size");
const sizeLabel = document.getElementById("size-label");
const autoBox = document.getElementById("auto");
const chips = Array.from(document.querySelectorAll(".host-chip"));
if (location.protocol === "file:") document.getElementById("file-note").classList.remove("hidden");

function applySize(value) {{
  const width = Math.max(160, Math.min(460, Number(value) || 220));
  root.style.setProperty("--card-w", width + "px");
  root.style.setProperty("--frame-h", Math.round(width * 0.75) + "px");
  root.style.setProperty("--scale", (width / 900).toFixed(4));
  sizeLabel.textContent = width + "px";
  slider.value = String(width);
  localStorage.setItem(SIZE_KEY, String(width));
}}

function applyFilter(host) {{
  chips.forEach((item) => item.classList.toggle("active", item.dataset.host === host));
  document.querySelectorAll(".card").forEach((card) => {{
    card.classList.toggle("hidden", Boolean(host) && card.dataset.host !== host);
  }});
  document.querySelectorAll(".site").forEach((site) => {{
    site.classList.toggle("hidden", !site.querySelector(".card:not(.hidden)"));
  }});
  sessionStorage.setItem(FILTER_KEY, host);
}}

applySize(localStorage.getItem(SIZE_KEY) || 220);
slider.addEventListener("input", () => applySize(slider.value));
chips.forEach((chip) => chip.addEventListener("click", () => applyFilter(chip.dataset.host)));
applyFilter(sessionStorage.getItem(FILTER_KEY) || "");

autoBox.checked = localStorage.getItem(AUTO_KEY) !== "0";
autoBox.addEventListener("change", () => localStorage.setItem(AUTO_KEY, autoBox.checked ? "1" : "0"));
document.getElementById("refresh").addEventListener("click", () => location.reload());

document.querySelectorAll(".track").forEach((track, index) => {{
  const saved = sessionStorage.getItem("pelican-scroll-" + index);
  if (saved) track.scrollLeft = Number(saved);
  track.addEventListener("scroll", () => sessionStorage.setItem("pelican-scroll-" + index, String(track.scrollLeft)));
}});

setInterval(() => {{
  if (document.visibilityState === "visible" && autoBox.checked) location.reload();
}}, 60000);
</script>
</body>
</html>
"""


_REFRESH_LOCK = threading.Lock()


def refresh_galleries(root):
    """Rewrite the global page and each day page. Sample HTML files are not touched."""
    with _REFRESH_LOCK:
        return _write_galleries(Path(root))


def _write_galleries(root):
    root.mkdir(parents=True, exist_ok=True)
    days = collect_days(root)
    global_page = root / "index.html"
    global_page.write_text(
        _page("路线提示词对比 · 全部日期", days, "", ""),
        encoding="utf-8",
    )
    for day in days:
        if not day["folder"]:
            continue
        folder = root / day["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(
            _page(f"路线提示词对比 · {day['label']}", [day], "../index.html", day["folder"]),
            encoding="utf-8",
        )
    return global_page


_GALLERY_SERVERS = {}


class _GalleryRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Rebuild the gallery before serving any index page, so data is never stale."""

    def __init__(self, *args, root, directory, **kwargs):
        self._root = Path(root)
        super().__init__(*args, directory=str(directory), **kwargs)

    def log_message(self, format, *args):
        return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html") or path.endswith("/index.html"):
            try:
                refresh_galleries(self._root)
            except OSError:
                pass
        super().do_GET()


def serve_gallery(root):
    """Serve the gallery on localhost and rebuild pages on every index request.

    Opening the returned URL keeps the comparison page in sync with the day folders
    even when samples are added or deleted outside the switcher.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    refresh_galleries(root)
    key = str(root.resolve())
    existing = _GALLERY_SERVERS.get(key)
    if existing is not None:
        return existing[1]
    handler = functools.partial(_GalleryRequestHandler, root=root, directory=root)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    _GALLERY_SERVERS[key] = (server, url)
    return url


def shutdown_gallery_servers():
    """Stop any local gallery servers (used by tests and shutdown paths)."""
    for server, _url in list(_GALLERY_SERVERS.values()):
        server.shutdown()
        server.server_close()
    _GALLERY_SERVERS.clear()
