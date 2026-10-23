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

    chips = "".join(host_button(host) for host in hosts)
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
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f6f7fb; color: #1f2329; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
.top {{ position: sticky; top: 0; z-index: 9; background: rgba(255,255,255,.94); backdrop-filter: blur(8px); border-bottom: 1px solid #e5e7eb; padding: 18px 28px 14px; }}
.top h1 {{ margin: 0; font-size: 30px; letter-spacing: 1px; }}
.top h1 b {{ color: #ff7d29; }}
.top p {{ margin: 8px 0 12px; color: #6b7280; font-size: 14px; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.chip {{ display: inline-flex; gap: 6px; align-items: center; padding: 6px 14px; border: 1px solid #d8dbe3; border-radius: 999px; background: #fff; color: #374151; text-decoration: none; font-size: 13px; cursor: pointer; }}
.chip b {{ color: #9ca3af; font-weight: 500; }}
.chip:hover {{ border-color: #ff7d29; color: #ff7d29; }}
.chip.active {{ background: #1f2329; border-color: #1f2329; color: #fff; }}
.chip.active b {{ color: #bbb; }}
.host-chip::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--dot, #ccc); }}
.stats {{ display: flex; gap: 26px; margin-top: 14px; }}
.stats div {{ font-size: 13px; color: #6b7280; }}
.stats strong {{ display: block; font-size: 22px; color: #1f2329; }}
main {{ padding: 8px 28px 48px; max-width: 1600px; }}
.day h1 {{ margin: 26px 0 6px; font-size: 26px; }}
.site h2 {{ display: flex; gap: 10px; align-items: center; margin: 20px 0 12px; font-size: 19px; }}
.site h2 i {{ width: 10px; height: 10px; border-radius: 50%; }}
.site h2 small {{ color: #9ca3af; font-weight: 400; font-size: 13px; }}
.track {{ display: flex; gap: 18px; overflow-x: auto; padding: 2px 2px 14px; scroll-snap-type: x proximity; }}
.track::-webkit-scrollbar {{ height: 8px; }}
.track::-webkit-scrollbar-thumb {{ background: #d4d7de; border-radius: 4px; }}
.card {{ flex: 0 0 340px; scroll-snap-align: start; background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; overflow: hidden; box-shadow: 0 2px 10px rgba(15,23,42,.05); }}
.card:hover {{ box-shadow: 0 8px 24px rgba(15,23,42,.12); }}
.frame {{ position: relative; display: block; height: 300px; background: #fff; }}
.frame iframe {{ width: 100%; height: 100%; border: 0; background: #fff; pointer-events: none; }}
.overlay {{ position: absolute; inset: 0; }}
.info {{ padding: 12px 14px 14px; border-top: 1px solid #f0f1f4; }}
.row1 {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
.row1 strong {{ font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
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
</div>
<main>{body}</main>
<script>
const chips = document.querySelectorAll(".host-chip");
chips.forEach((chip) => {{
  chip.onclick = () => {{
    const host = chip.dataset.host;
    chips.forEach((item) => item.classList.toggle("active", item === chip));
    document.querySelectorAll(".card").forEach((card) => {{
      card.classList.toggle("hidden", Boolean(host) && card.dataset.host !== host);
    }});
    document.querySelectorAll(".site").forEach((site) => {{
      const visible = site.querySelector(".card:not(.hidden)");
      site.classList.toggle("hidden", !visible);
    }});
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
