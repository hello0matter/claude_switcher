"""Prompt-test filenames, templates, and Codex config overrides.

The prompt test asks Codex or Codexx to write one HTML file. It must not rewrite
the user's global config.toml, and the default prompt must not ask the model to
commit or push.
"""

import json
import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path


PROMPT_SETTINGS_FILE = Path.home() / ".claude_switcher_prompt.json"
LOCKED_WIRE_API = "responses"
WIRE_SUFFIX = "/responses"
_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_TRADITIONAL_SUFFIXES = ("/chat/completions", "/completions")
_FILENAME_TOKEN = re.compile(r"[^A-Za-z0-9._-]+")

DEFAULT_OUTPUT_DIR = (
    r"D:\tmp\tmp\大模型智力评测"
    if os.name == "nt"
    else str(Path.home() / "大模型智力评测")
)
DEFAULT_PROMPT = """重新创建一个 HTML，内容是 SVG 绘制一个鹈鹕骑自行车的 2D 动画。你不需要任何测试。
把完整、可直接用浏览器打开的单个 HTML 文件写到这个路径，并覆盖同名文件：
{output_path}
只写这一个文件。不要创建其他文件，不要运行测试，不要执行 git commit、git push 或其他仓库操作。
"""
PLACEHOLDER_HELP = (
    "可用占位符：{output_path} {output_dir} {filename} {model} {effort} "
    "{wire} {api_host} {route_name} {base_url}。"
    "如果删掉 {output_path}，软件仍会在末尾补上实际保存路径。"
)


def load_prompt_settings():
    settings = {
        "output_dir": DEFAULT_OUTPUT_DIR,
        "prompt": DEFAULT_PROMPT,
        "hidden": True,
    }
    if PROMPT_SETTINGS_FILE.exists():
        try:
            stored = json.loads(PROMPT_SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            stored = None
        if isinstance(stored, dict):
            output_dir = str(stored.get("output_dir") or "").strip()
            prompt = str(stored.get("prompt") or "").strip()
            if output_dir:
                settings["output_dir"] = output_dir
            if prompt:
                settings["prompt"] = prompt
            if "hidden" in stored:
                settings["hidden"] = bool(stored.get("hidden"))
    return settings


def save_prompt_settings(settings):
    payload = {
        "output_dir": str(settings.get("output_dir") or DEFAULT_OUTPUT_DIR).strip()
        or DEFAULT_OUTPUT_DIR,
        "prompt": str(settings.get("prompt") or "").strip() or DEFAULT_PROMPT,
        "hidden": bool(settings.get("hidden", True)),
    }
    PROMPT_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = PROMPT_SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, PROMPT_SETTINGS_FILE)
    return payload


def strip_manual_wire_suffix(base_url):
    """Return (url, kind). kind is traditional, responses, or empty."""
    text = str(base_url or "").strip().rstrip("/")
    lowered = text.lower()
    for suffix in _TRADITIONAL_SUFFIXES:
        if lowered.endswith(suffix):
            return text[: -len(suffix)].rstrip("/"), "traditional"
    if lowered.endswith(WIRE_SUFFIX):
        return text[: -len(WIRE_SUFFIX)].rstrip("/"), "responses"
    return text, ""


def prepare_route_form(values):
    """Editor save path: suffix is appended by Codex, never chosen by hand."""
    prepared = dict(values)
    base_url, kind = strip_manual_wire_suffix(prepared.get("base_url", ""))
    prepared["base_url"] = base_url
    prepared["wire_api"] = LOCKED_WIRE_API
    prepared["wire_suffix_kind"] = kind
    return prepared


def non_subdomain_host(base_url):
    """Drop only the leftmost subdomain label from an API host."""
    raw = str(base_url or "").strip()
    if not raw:
        return "nohost"
    if "://" not in raw:
        raw = "https://" + raw
    host = (urllib.parse.urlparse(raw).hostname or "").strip(".").lower()
    if not host:
        return "nohost"
    if ":" in host:
        return host.replace(":", "-")
    labels = [part for part in host.split(".") if part]
    if len(labels) >= 3:
        labels = labels[1:]
    return ".".join(labels) or "nohost"


def _file_token(value, fallback, limit):
    text = _FILENAME_TOKEN.sub("-", str(value or "")).strip(".-_")
    text = re.sub(r"-{2,}", "-", text)
    return (text or fallback)[:limit]


def prompt_filename(route, when=None):
    moment = when or datetime.now()
    stamp = moment.strftime("%Y%m%d-%H%M%S")
    host = _file_token(non_subdomain_host(route.get("base_url")), "nohost", 48)
    model = _file_token(route.get("model"), "nomodel", 48)
    effort = _file_token(route.get("reasoning_effort"), "default", 16)
    wire = _file_token(route.get("wire_api") or LOCKED_WIRE_API, LOCKED_WIRE_API, 16)
    return f"{stamp}_{host}_{model}_{effort}_{wire}.html"


def unique_output_path(directory, filename):
    directory = Path(directory)
    path = directory / filename
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = directory / f"{path.stem}-{index}{path.suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def render_prompt(template, route, output_path):
    output_path = Path(output_path)
    values = {
        "output_path": str(output_path),
        "output_dir": str(output_path.parent),
        "filename": output_path.name,
        "model": str(route.get("model") or ""),
        "effort": str(route.get("reasoning_effort") or "默认"),
        "wire": LOCKED_WIRE_API,
        "api_host": non_subdomain_host(route.get("base_url")),
        "route_name": str(route.get("name") or ""),
        "base_url": str(route.get("base_url") or ""),
    }
    text = str(template or DEFAULT_PROMPT)
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    if str(output_path) not in text:
        text = text.rstrip() + f"\n\n把 HTML 文件写到：{output_path}\n"
    return text


def provider_id_problem(route):
    provider_id = str(route.get("provider_id") or "").strip()
    if not provider_id:
        return "没有 provider ID"
    if _PROVIDER_ID.fullmatch(provider_id) is None:
        return "provider ID 含空格或特殊字符，批量测试不会改写全局 config.toml，已跳过"
    return ""


def config_override_args(route):
    """Per-process overrides. These are not written to config.toml."""
    provider_id = str(route.get("provider_id") or "").strip()
    args = ["-c", f"model_provider={json.dumps(provider_id, ensure_ascii=False)}"]
    prefix = f"model_providers.{provider_id}"
    base_url, _kind = strip_manual_wire_suffix(route.get("base_url"))
    if base_url:
        args.extend(["-c", f"{prefix}.base_url={json.dumps(base_url, ensure_ascii=False)}"])
    args.extend(
        [
            "-c",
            f"{prefix}.wire_api={json.dumps(LOCKED_WIRE_API)}",
            "-c",
            f"{prefix}.requires_openai_auth=false",
        ]
    )
    if route.get("name"):
        args.extend(["-c", f"{prefix}.name={json.dumps(str(route['name']), ensure_ascii=False)}"])
    api_key = str(route.get("api_key") or "")
    if api_key:
        args.extend(
            ["-c", f"{prefix}.experimental_bearer_token={json.dumps(api_key, ensure_ascii=False)}"]
        )
    if route.get("reasoning_effort"):
        args.extend(
            [
                "-c",
                "model_reasoning_effort="
                + json.dumps(str(route["reasoning_effort"]), ensure_ascii=False),
            ]
        )
    storage = route.get("disable_response_storage")
    if storage in (True, False):
        args.extend(["-c", f"disable_response_storage={str(storage).lower()}"])
    return args


def prompt_mentions_git_publish(prompt):
    """Warn only when a line asks for commit/push, not when it forbids them."""
    for line in str(prompt or "").splitlines():
        lowered = line.lower()
        if any(word in lowered for word in ("不要", "禁止", "do not", "don't", "never")):
            continue
        if any(word in lowered for word in ("git commit", "git push", "提交", "推送")):
            return True
    return False
