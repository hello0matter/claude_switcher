"""Day folders and scrollable comparison pages for prompt-test HTML files."""

import hashlib
import html
import re
from datetime import datetime
from pathlib import Path

import prompt_probe


_DAY_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STAMP = re.compile(r"^\d{8}-\d{6}$")
_COLORS = ("#1565C0", "#2E7D32", "#C62828", "#6A1B9A", "#EF6C00", "#00838F", "#5D4037", "#AD1457")


def day_name(when=None):
    return (when or datetime.now()).strftime("%Y-%m-%d")


def allocate_prompt_output(root, route, when=None):
    """Put one sample in a day folder. Comparison pages are written separately."""
    moment = when or datetime.now()
    day = Path(root) / day_name(moment)
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
    meta = " · ".join(part for part in (row["model"], row["effort"], row["wire"], row["stamp"]) if part)
    size_note = "空文件或未写完" if row["size"] < 200 else f"{row['size'] // 1024} KB"
    title = html.escape(row["host"] or row["name"])
    return f"""
<article class="card" data-host="{html.escape(row['host'])}" style="--site:{color}">
  <header>
    <strong>{title}</strong>
    <span>{html.escape(meta)}</span>
    <em>{html.escape(size_note)}</em>
    <a href="{html.escape(href)}">单独打开</a>
    <button type="button" class="live-btn">允许卡片内交互</button>
  </header>
  <div class="frame-wrap">
    <div class="overlay" title="滚轮滚动外层页面"></div>
    <iframe loading="lazy" src="{html.escape(href)}" title="{title}"></iframe>
  </div>
</article>
"""


def _page(title, days, home_href, current_folder):
    day_links = []
    for day in days:
        if day["folder"]:
            href = f"{day['folder']}/index.html" if not current_folder else (
                "index.html" if day["folder"] == current_folder else f"../{day['folder']}/index.html"
            )
        else:
            href = "#loose" if not current_folder else "../index.html#loose"
        day_links.append(f'<a href="{html.escape(href)}">{html.escape(day["label"])} ({len(day["rows"])})</a>')
    hosts = sorted({row["host"] for day in days for row in day["rows"] if row["host"]})
    host_buttons = ['<button type="button" data-host="">全部站点</button>']
    host_buttons.extend(
        f'<button type="button" data-host="{html.escape(host)}" style="border-color:{_host_color(host)}">{html.escape(host)}</button>'
        for host in hosts
    )
    sections = []
    for day in days:
        sites = _group_sites(day["rows"])
        site_html = []
        for site in sites:
            cards = []
            for row in site["rows"]:
                if current_folder:
                    href = row["name"]
                elif day["folder"]:
                    href = f"{day['folder']}/{row['name']}"
                else:
                    href = row["name"]
                cards.append(_card_html(row, href, site['color']))
            site_html.append(
                f'<section class="site"><h3 style="color:{site["color"]}">{html.escape(site["host"])}'
                f' <small>{len(site["rows"])} 个</small></h3><div class="grid">{"".join(cards)}</div></section>'
            )
        anchor = "loose" if not day["folder"] else day["label"]
        sections.append(
            f'<section class="day" id="{html.escape(anchor)}"><h2>{html.escape(day["label"])}</h2>{"".join(site_html) or "<p>这一天还没有样本。</p>"}</section>'
        )
    body = "".join(sections) or "<p class='empty'>还没有样本。跑一次路线提示词测试后，回到这里刷新。</p>"
    home = f'<a href="{html.escape(home_href)}">全局对比</a>' if home_href else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ margin: 0; background: #121212; color: #f3f3f3; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
.top {{ position: sticky; top: 0; z-index: 8; background: #1c1c1c; border-bottom: 1px solid #333; padding: 10px 16px 12px; }}
.top h1 {{ margin: 0 0 6px; font-size: 20px; }}
.top p {{ margin: 0 0 8px; color: #bbb; font-size: 13px; }}
.links a, .hosts button, .tools button {{ display: inline-block; margin: 3px 6px 3px 0; padding: 4px 8px; color: #fff; background: #2a2a2a; border: 1px solid #555; border-radius: 6px; text-decoration: none; cursor: pointer; }}
.day {{ padding: 8px 16px 28px; }}
.day h2 {{ margin: 18px 0 8px; font-size: 28px; }}
.site h3 {{ margin: 14px 0 8px; font-size: 22px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(640px, 1fr)); gap: 16px; }}
.card {{ background: #1a1a1a; border: 4px solid var(--site, #444); border-radius: 12px; overflow: hidden; }}
.card header {{ display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: baseline; padding: 10px 12px; }}
.card header strong {{ font-size: 22px; }}
.card header span, .card header em {{ color: #c8c8c8; font-style: normal; }}
.card header a, .card header button {{ color: #9ad; background: transparent; border: 0; cursor: pointer; font: inherit; }}
.frame-wrap {{ position: relative; height: 68vh; min-height: 520px; background: #fff; }}
.frame-wrap iframe {{ width: 100%; height: 100%; border: 0; background: #fff; pointer-events: none; }}
.overlay {{ position: absolute; inset: 0; }}
.frame-wrap.live iframe {{ pointer-events: auto; }}
.frame-wrap.live .overlay {{ display: none; }}
body.compact .frame-wrap {{ height: 340px; min-height: 260px; }}
body.compact .grid {{ grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); }}
.hidden {{ display: none !important; }}
.empty {{ padding: 24px; }}
</style>
</head>
<body>
<div class="top">
  <h1>{html.escape(title)}</h1>
  <p>同一站点的动画放在一起。默认滚轮只滚外层，方便连续看哪个站更好。卡片默认大图；样本很多时再切紧凑。</p>
  <div class="tools">
    {home}
    <button type="button" id="size-btn">切换紧凑图</button>
  </div>
  <div class="links">{''.join(day_links)}</div>
  <div class="hosts">{''.join(host_buttons)}</div>
</div>
{body}
<script>
const sizeBtn = document.getElementById("size-btn");
function applySize(compact) {{
  document.body.classList.toggle("compact", compact);
  sizeBtn.textContent = compact ? "切换大图" : "切换紧凑图";
  localStorage.setItem("prompt-gallery-size", compact ? "compact" : "large");
}}
applySize(localStorage.getItem("prompt-gallery-size") === "compact");
sizeBtn.onclick = () => applySize(!document.body.classList.contains("compact"));
document.querySelectorAll(".hosts button").forEach((button) => {{
  button.onclick = () => {{
    const host = button.dataset.host;
    document.querySelectorAll(".card").forEach((card) => {{
      card.classList.toggle("hidden", Boolean(host) && card.dataset.host !== host);
    }});
    document.querySelectorAll(".site").forEach((site) => {{
      const visible = site.querySelector(".card:not(.hidden)");
      site.classList.toggle("hidden", !visible);
    }});
  }};
}});
document.querySelectorAll(".live-btn").forEach((button) => {{
  button.onclick = () => {{
    const wrap = button.closest(".card").querySelector(".frame-wrap");
    wrap.classList.toggle("live");
    button.textContent = wrap.classList.contains("live") ? "恢复外层滚动" : "允许卡片内交互";
  }};
}});
</script>
</body>
</html>
"""


def refresh_galleries(root):
    """Rewrite the global page and each day page. Sample HTML files are not touched."""
    root = Path(root)
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
