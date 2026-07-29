"""Codex provider management panel for Claude Route Switcher."""

import base64
import copy
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

try:
    import tomlkit
except ImportError:  # pragma: no cover - only used on machines missing the optional writer
    tomlkit = None


CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
CODEX_CONFIG_FILE = CODEX_HOME / "config.toml"
CODEX_ROUTES_FILE = Path.home() / ".codex_routes.json"
CODEX_SESSION_BACKUP_DIR = CODEX_HOME / "session-meta-backups"
CODEX_DB_BACKUP_DIR = CODEX_HOME / "db-backups"
CODEX_DB_FILE = CODEX_HOME / "state_5.sqlite"
CODEXX_EXE = Path(
    os.environ.get(
        "CODEXX_EXE",
        CODEX_HOME / ".sandbox-bin" / "codexhistory" / "codexx.exe",
    )
)
SESSION_META_PROVIDER = re.compile(rb'("model_provider"\s*:\s*)("(?:[^"\\]|\\.)*")([ \t]*)')
VISIBILITY_SETTINGS_TABLE = "codex_resume_visibility_settings"
VISIBILITY_INSERT_TRIGGER = "codex_resume_visibility_after_insert"
VISIBILITY_UPDATE_TRIGGER = "codex_resume_visibility_after_update"


@dataclass(frozen=True)
class CodexHistorySyncResult:
    rollout_updates: int
    rollout_matching: int
    rollout_total: int
    manifest: Path | None
    db_updates: int
    db_matching: int
    db_total: int
    picker_visible: int
    db_backup: Path | None


def _now_stamp():
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _mask_secret(value):
    value = str(value or "")
    if not value:
        return "(未设置)"
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def _normalise_route(route):
    result = {
        "name": "",
        "provider_id": "",
        "base_url": "",
        "api_key": "",
        "model": "",
        "reasoning_effort": "",
        "wire_api": "responses",
        "models": [],
        "note": "",
    }
    result.update(route or {})
    result["name"] = str(result.get("name") or result.get("provider_id") or "未命名")
    result["provider_id"] = str(result.get("provider_id") or result["name"]).strip()
    result["base_url"] = str(result.get("base_url") or "").strip().rstrip("/")
    result["api_key"] = str(result.get("api_key") or "").strip()
    result["model"] = str(result.get("model") or "").strip()
    result["reasoning_effort"] = str(result.get("reasoning_effort") or "").strip()
    result["wire_api"] = str(result.get("wire_api") or "responses").strip()
    models = result.get("models", [])
    if isinstance(models, str):
        models = [item.strip() for item in models.split(",") if item.strip()]
    result["models"] = list(dict.fromkeys(str(item).strip() for item in models if str(item).strip()))
    result["note"] = str(result.get("note") or "").strip()
    result.setdefault("route_id", "route-" + uuid.uuid4().hex[:12])
    return result


def _read_codex_config():
    if not CODEX_CONFIG_FILE.exists():
        return {}
    try:
        with CODEX_CONFIG_FILE.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _routes_from_codex_config():
    config = _read_codex_config()
    current_provider = str(config.get("model_provider") or "")
    current_model = str(config.get("model") or "")
    current_reasoning = str(config.get("model_reasoning_effort") or "")
    routes = []
    for provider_id, provider in (config.get("model_providers") or {}).items():
        if not isinstance(provider, dict):
            continue
        routes.append(_normalise_route({
            "name": provider.get("name") or provider_id,
            "provider_id": provider_id,
            "base_url": provider.get("base_url", ""),
            "api_key": provider.get("experimental_bearer_token", ""),
            "model": current_model if provider_id == current_provider else "",
            "reasoning_effort": current_reasoning if provider_id == current_provider else "",
            "wire_api": provider.get("wire_api", "responses"),
            "note": "从 ~/.codex/config.toml 导入",
        }))
    if not routes and current_provider:
        routes.append(_normalise_route({
            "name": current_provider,
            "provider_id": current_provider,
            "model": current_model,
            "reasoning_effort": current_reasoning,
        }))
    return routes


def load_codex_routes():
    if CODEX_ROUTES_FILE.exists():
        try:
            with CODEX_ROUTES_FILE.open("r", encoding="utf-8") as stream:
                routes = json.load(stream)
            if isinstance(routes, list) and routes:
                return [_normalise_route(route) for route in routes]
        except (OSError, ValueError):
            pass
    routes = _routes_from_codex_config()
    if not routes:
        routes = [_normalise_route({"name": "Codex 默认 provider", "provider_id": "mc"})]
    save_codex_routes(routes)
    return routes


def save_codex_routes(routes):
    CODEX_ROUTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = [_normalise_route(route) for route in routes]
    temp = CODEX_ROUTES_FILE.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(clean, stream, ensure_ascii=False, indent=2)
    os.replace(temp, CODEX_ROUTES_FILE)


def _backup_file(path):
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-codex-switcher-{_now_stamp()}")
    shutil.copy2(path, backup)
    return backup


def _write_codex_config(route):
    if tomlkit is None:
        raise RuntimeError("缺少 tomlkit，无法安全写入 config.toml。请运行：python -m pip install tomlkit")
    if route["wire_api"] != "responses":
        raise ValueError("当前 Codex 仅支持 wire API：responses")
    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    original = CODEX_CONFIG_FILE.read_text(encoding="utf-8") if CODEX_CONFIG_FILE.exists() else ""
    document = tomlkit.parse(original) if original.strip() else tomlkit.document()
    document["model_provider"] = route["provider_id"]
    if route["model"]:
        document["model"] = route["model"]
    if route["reasoning_effort"]:
        document["model_reasoning_effort"] = route["reasoning_effort"]

    providers = document.get("model_providers")
    if providers is None:
        providers = tomlkit.table()
        document["model_providers"] = providers
    provider = providers.get(route["provider_id"])
    if provider is None:
        provider = tomlkit.table()
        providers[route["provider_id"]] = provider
    provider["name"] = route["name"]
    if route["base_url"]:
        provider["base_url"] = route["base_url"]
    elif "base_url" in provider:
        del provider["base_url"]
    provider["wire_api"] = route["wire_api"]
    provider["requires_openai_auth"] = False
    if route["api_key"]:
        provider["experimental_bearer_token"] = route["api_key"]
    elif "experimental_bearer_token" in provider:
        del provider["experimental_bearer_token"]

    backup = _backup_file(CODEX_CONFIG_FILE)
    temp = CODEX_CONFIG_FILE.with_suffix(".tmp")
    temp.write_text(tomlkit.dumps(document), encoding="utf-8")
    with temp.open("r", encoding="utf-8") as stream:
        tomllib.loads(stream.read())
    os.replace(temp, CODEX_CONFIG_FILE)
    return backup


def _iter_rollouts():
    for folder in (CODEX_HOME / "sessions", CODEX_HOME / "archived_sessions"):
        if folder.exists():
            yield from folder.rglob("*.jsonl")


def _plan_rollout_provider(path, target_provider):
    with path.open("rb") as stream:
        first_line = stream.readline()
    try:
        metadata = json.loads(first_line)
    except (UnicodeDecodeError, ValueError):
        return None
    if metadata.get("type") != "session_meta":
        return None
    match = SESSION_META_PROVIDER.search(first_line)
    if match is None:
        return None
    current = json.loads(match.group(2))
    if current == target_provider:
        return False
    replacement = json.dumps(target_provider, ensure_ascii=True).encode("ascii")
    available = len(match.group(2)) + len(match.group(3))
    if len(replacement) <= available:
        padded = replacement + b" " * (available - len(replacement))
        new_line = first_line[:match.start(2)] + padded + first_line[match.end(2):]
    else:
        new_line = first_line[:match.start(2)] + replacement + first_line[match.end(2):]
    if json.loads(new_line)["payload"].get("model_provider") != target_provider:
        return None
    return {"path": path, "old_line": first_line, "new_line": new_line}


def _apply_rollout_provider_plan(plan):
    path = plan["path"]
    old_line = plan["old_line"]
    new_line = plan["new_line"]
    if len(old_line) == len(new_line):
        with path.open("r+b") as stream:
            if stream.readline() != old_line:
                return False
            stream.seek(0)
            stream.write(new_line)
            stream.flush()
            os.fsync(stream.fileno())
        return True

    temp_name = None
    try:
        with path.open("rb") as source:
            if source.readline() != old_line:
                return False
            temp_fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
            with os.fdopen(temp_fd, "wb") as target:
                target.write(new_line)
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
        os.replace(temp_name, path)
        return True
    except OSError:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        return False


def _table_exists(db, name):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone() is not None


def _extended_windows_path(path):
    if path.startswith("\\\\?\\") or path.startswith("\\\\"):
        return path
    if re.match(r"^[A-Za-z]:\\", path):
        return "\\\\?\\" + path
    return path


def _visibility_trigger_sql(trigger_name, operation, include_cwd):
    event = "INSERT" if operation == "insert" else "UPDATE OF model_provider"
    if operation == "update" and include_cwd:
        event += ", cwd"
    provider_expression = (
        f"(SELECT model_provider FROM {VISIBILITY_SETTINGS_TABLE} WHERE id = 1)"
    )
    conditions = [f"NEW.model_provider <> {provider_expression}"]
    assignments = [f"model_provider = {provider_expression}"]
    if include_cwd:
        plain_drive_path = "length(NEW.cwd) >= 3 AND substr(NEW.cwd, 2, 2) = ':\\'"
        conditions.append(f"({plain_drive_path})")
        assignments.append(
            "cwd = CASE "
            f"WHEN {plain_drive_path} THEN '\\\\?\\' || NEW.cwd "
            "ELSE NEW.cwd END"
        )
    return f"""
        CREATE TRIGGER {trigger_name}
        AFTER {event} ON threads
        WHEN {' OR '.join(conditions)}
        BEGIN
            UPDATE threads
            SET {', '.join(assignments)}
            WHERE id = NEW.id;
        END
    """


def _normalise_sql(sql):
    return re.sub(r"\s+", " ", sql or "").strip()


def _sync_codex_history_db(provider_id):
    empty = {
        "updates": 0,
        "matching": 0,
        "total": 0,
        "picker_visible": 0,
        "backup": None,
    }
    if not CODEX_DB_FILE.exists():
        return empty

    db = None
    try:
        db = sqlite3.connect(CODEX_DB_FILE, timeout=30)
        if not _table_exists(db, "threads"):
            return empty
        columns = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
        if not {"id", "model_provider"}.issubset(columns):
            return empty

        total = db.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
        mismatched = db.execute(
            "SELECT COUNT(*) FROM threads WHERE model_provider <> ?",
            (provider_id,),
        ).fetchone()[0]
        setting = None
        if _table_exists(db, VISIBILITY_SETTINGS_TABLE):
            row = db.execute(
                f"SELECT model_provider FROM {VISIBILITY_SETTINGS_TABLE} WHERE id = 1"
            ).fetchone()
            setting = row[0] if row else None

        include_cwd = "cwd" in columns
        cwd_updates = []
        if include_cwd:
            cwd_updates = [
                (normalised, thread_id)
                for thread_id, cwd in db.execute("SELECT id, cwd FROM threads")
                if cwd is not None and (normalised := _extended_windows_path(cwd)) != cwd
            ]

        expected_triggers = {
            VISIBILITY_INSERT_TRIGGER: _visibility_trigger_sql(
                VISIBILITY_INSERT_TRIGGER, "insert", include_cwd
            ),
            VISIBILITY_UPDATE_TRIGGER: _visibility_trigger_sql(
                VISIBILITY_UPDATE_TRIGGER, "update", include_cwd
            ),
        }
        trigger_rows = dict(db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND name IN (?, ?)",
            (VISIBILITY_INSERT_TRIGGER, VISIBILITY_UPDATE_TRIGGER),
        ))
        triggers_current = all(
            _normalise_sql(trigger_rows.get(name)) == _normalise_sql(sql)
            for name, sql in expected_triggers.items()
        )
        needs_change = bool(
            mismatched
            or cwd_updates
            or setting != provider_id
            or not triggers_current
        )
        backup_path = None
        updates = 0
        if needs_change:
            CODEX_DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = CODEX_DB_BACKUP_DIR / f"state_5.sqlite.bak-codex-switcher-{_now_stamp()}"
            backup_db = sqlite3.connect(backup_path)
            try:
                db.backup(backup_db)
            finally:
                backup_db.close()

            with db:
                db.execute(f"""
                    CREATE TABLE IF NOT EXISTS {VISIBILITY_SETTINGS_TABLE} (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        model_provider TEXT NOT NULL
                    )
                """)
                # Update the setting before touching thread rows. Existing durable triggers
                # read this value and would otherwise change every row back to the old route.
                db.execute(f"""
                    INSERT INTO {VISIBILITY_SETTINGS_TABLE} (id, model_provider)
                    VALUES (1, ?)
                    ON CONFLICT(id) DO UPDATE SET model_provider = excluded.model_provider
                """, (provider_id,))
                for trigger_name in expected_triggers:
                    db.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
                for trigger_sql in expected_triggers.values():
                    db.execute(trigger_sql)
                updates = db.execute(
                    "UPDATE threads SET model_provider = ? WHERE model_provider <> ?",
                    (provider_id, provider_id),
                ).rowcount
                if cwd_updates:
                    db.executemany("UPDATE threads SET cwd = ? WHERE id = ?", cwd_updates)

        matching = db.execute(
            "SELECT COUNT(*) FROM threads WHERE model_provider = ?",
            (provider_id,),
        ).fetchone()[0]
        picker_visible = 0
        if {"archived", "preview", "source"}.issubset(columns):
            picker_visible = db.execute("""
                SELECT COUNT(*) FROM threads
                WHERE archived = 0
                  AND preview <> ''
                  AND source IN ('cli', 'vscode')
                  AND model_provider = ?
            """, (provider_id,)).fetchone()[0]
        return {
            "updates": updates,
            "matching": matching,
            "total": total,
            "picker_visible": picker_visible,
            "backup": backup_path,
        }
    except sqlite3.Error as exc:
        raise RuntimeError("Codex 历史索引数据库同步失败") from exc
    finally:
        if db is not None:
            db.close()


def sync_codex_session_visibility(provider_id):
    plans = []
    rollout_total = 0
    already_matching = 0
    for path in _iter_rollouts():
        plan = _plan_rollout_provider(path, provider_id)
        if isinstance(plan, dict):
            plans.append(plan)
            rollout_total += 1
        elif plan is False:
            rollout_total += 1
            already_matching += 1
    manifest = None
    if plans:
        CODEX_SESSION_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        manifest = CODEX_SESSION_BACKUP_DIR / f"provider-lines-app-{_now_stamp()}.jsonl"
        with manifest.open("w", encoding="utf-8") as stream:
            for plan in plans:
                stream.write(json.dumps({
                    "path": str(plan["path"]),
                    "line": base64.b64encode(plan["old_line"]).decode("ascii"),
                }, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    applied = sum(1 for plan in plans if _apply_rollout_provider_plan(plan))
    db_result = _sync_codex_history_db(provider_id)
    return CodexHistorySyncResult(
        rollout_updates=applied,
        rollout_matching=already_matching + applied,
        rollout_total=rollout_total,
        manifest=manifest,
        db_updates=db_result["updates"],
        db_matching=db_result["matching"],
        db_total=db_result["total"],
        picker_visible=db_result["picker_visible"],
        db_backup=db_result["backup"],
    )


def sync_codex_history_provider(provider_id):
    """Backward-compatible wrapper for callers expecting the original tuple."""
    result = sync_codex_session_visibility(provider_id)
    return result.rollout_updates, result.manifest


def _codex_console_command(binary, resume_all=False):
    if binary == "codex":
        executable = os.environ.get("CODEX_COMMAND", "codex")
    elif binary == "codexx":
        if not CODEXX_EXE.is_file():
            raise FileNotFoundError(f"找不到 Codexx：{CODEXX_EXE}")
        executable = str(CODEXX_EXE)
    else:
        raise ValueError(f"未知 Codex 二进制：{binary}")
    arguments = ["resume", "--all"] if resume_all else ["--yolo"]
    return ["cmd.exe", "/k", executable, *arguments]


def _openai_url(base_url, endpoint):
    base = (base_url or "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/" + endpoint):
        return base
    if base.endswith("/v1"):
        return base + "/" + endpoint
    return base + "/v1/" + endpoint


def test_codex_model(route, model, timeout=30):
    model = (model or route.get("model") or "").strip()
    if not model:
        return False, "", "没有模型名"
    headers = {"Content-Type": "application/json"}
    if route.get("api_key"):
        headers["Authorization"] = "Bearer " + route["api_key"]
    wire_api = route.get("wire_api", "responses")
    if wire_api == "chat":
        endpoint = "chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 16}
    elif wire_api == "completions":
        endpoint = "completions"
        payload = {"model": model, "prompt": "Reply with OK.", "max_tokens": 16}
    else:
        endpoint = "responses"
        payload = {"model": model, "input": "Reply with OK.", "max_output_tokens": 16}
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(_openai_url(route.get("base_url"), endpoint), data=body, headers=headers, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(4096)
        return True, f"{(time.perf_counter() - started) * 1000:.0f}", ""
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        return False, f"{(time.perf_counter() - started) * 1000:.0f}", f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        return False, f"{(time.perf_counter() - started) * 1000:.0f}", str(exc)


class CodexRouteEditor(tk.Toplevel):
    def __init__(self, parent, route=None, title="添加 Codex 路线"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        route = _normalise_route(route or {})
        fields = [
            ("名称 *", "name"),
            ("provider ID *", "provider_id"),
            ("API 地址", "base_url"),
            ("Bearer 密钥", "api_key"),
            ("默认模型", "model"),
            ("模型列表（逗号）", "models"),
            ("推理强度", "reasoning_effort"),
            ("wire API", "wire_api"),
            ("备注", "note"),
        ]
        self.vars = {}
        self.key_entry = None
        for row, (label, key) in enumerate(fields):
            tk.Label(self, text=label, width=18, anchor="w").grid(row=row, column=0, padx=(12, 4), pady=5, sticky="w")
            value = route.get(key, []) if key == "models" else route.get(key, "")
            if key == "models":
                value = ", ".join(value) if isinstance(value, list) else str(value)
            var = tk.StringVar(value=str(value))
            if key == "reasoning_effort":
                entry = ttk.Combobox(
                    self,
                    textvariable=var,
                    width=40,
                    values=("", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"),
                )
            elif key == "wire_api":
                entry = ttk.Combobox(
                    self,
                    textvariable=var,
                    width=40,
                    values=("responses",),
                    state="readonly",
                )
            else:
                entry = tk.Entry(self, textvariable=var, width=43, show="*" if key == "api_key" else "")
            entry.grid(row=row, column=1, padx=4, pady=5)
            self.vars[key] = var
            if key == "api_key":
                self.key_entry = entry
                tk.Button(self, text="显示", width=5, command=self._toggle_key).grid(row=row, column=2, padx=(0, 8))
        self._key_visible = False
        buttons = tk.Frame(self)
        buttons.grid(row=len(fields), column=0, columnspan=3, pady=(8, 12))
        tk.Button(buttons, text="保存", width=12, command=self._save).pack(side="left", padx=5)
        tk.Button(buttons, text="取消", width=12, command=self.destroy).pack(side="left", padx=5)
        self.grab_set()
        self.wait_window()

    def _toggle_key(self):
        self._key_visible = not self._key_visible
        self.key_entry.config(show="" if self._key_visible else "*")

    def _save(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if not values["name"] or not values["provider_id"]:
            messagebox.showwarning("提示", "名称和 provider ID 不能为空", parent=self)
            return
        values["models"] = [item.strip() for item in values["models"].split(",") if item.strip()]
        self.result = _normalise_route(values)
        self.destroy()


class CodexModelTestDialog(tk.Toplevel):
    def __init__(self, parent, route):
        super().__init__(parent)
        self.parent = parent
        self.route = route
        self.title("Codex 模型测试 - " + route.get("name", ""))
        self.geometry("820x480")
        self.minsize(700, 380)
        self.closed = False
        self.testing = False
        self.rows = [{"model": model, "status": "", "latency": "", "error": ""} for model in route.get("models", [])]
        if route.get("model") and route["model"] not in [row["model"] for row in self.rows]:
            self.rows.insert(0, {"model": route["model"], "status": "", "latency": "", "error": ""})
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh()

    def _build_ui(self):
        top = tk.Frame(self, pady=8)
        top.pack(fill="x", padx=10)
        tk.Button(top, text="添加模型", command=self._add).pack(side="left", padx=3)
        tk.Button(top, text="删除选中", command=self._delete).pack(side="left", padx=3)
        tk.Button(top, text="测试选中", command=self._test_selected).pack(side="left", padx=3)
        tk.Button(top, text="测试全部", command=self._test_all, bg="#238636", fg="white").pack(side="left", padx=3)
        tk.Button(top, text="应用到路线", command=self._apply).pack(side="left", padx=3)
        self.status = tk.StringVar(value="")
        tk.Label(top, textvariable=self.status, fg="#666").pack(side="right")
        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree = ttk.Treeview(body, columns=("model", "status", "latency", "error"), show="headings", selectmode="extended")
        for column, heading, width in (("model", "模型", 280), ("status", "状态", 90), ("latency", "耗时 ms", 90), ("error", "错误", 330)):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(index), values=(row["model"], row["status"], row["latency"], row["error"][:180]))
        self.status.set(f"共 {len(self.rows)} 个模型")

    def _selected(self):
        return [int(item) for item in self.tree.selection()]

    def _add(self):
        model = simpledialog.askstring("添加模型", "模型名：", parent=self)
        if model and model.strip():
            self.rows.append({"model": model.strip(), "status": "", "latency": "", "error": ""})
            self._refresh()

    def _delete(self):
        for index in reversed(self._selected()):
            self.rows.pop(index)
        self._refresh()

    def _test_selected(self):
        indexes = self._selected()
        if indexes:
            self._start(indexes)

    def _test_all(self):
        if self.rows and not self.testing:
            self._start(list(range(len(self.rows))))

    def _start(self, indexes):
        if self.testing:
            return
        self.testing = True
        threading.Thread(target=self._run, args=(indexes,), daemon=True).start()

    def _run(self, indexes):
        for offset, index in enumerate(indexes, 1):
            if self.closed:
                break
            row = self.rows[index]
            self.after(0, self.status.set, f"测试中 {offset}/{len(indexes)}: {row['model']}")
            ok, latency, error = test_codex_model(self.route, row["model"])
            row.update(status="联通" if ok else "失败", latency=latency, error=error)
            self.after(0, self._refresh)
        self.testing = False
        if not self.closed:
            self.after(0, self.status.set, "测试完成")

    def _apply(self):
        self.route["models"] = [row["model"] for row in self.rows]
        selected = self._selected()
        if selected:
            self.route["model"] = self.rows[selected[0]]["model"]
        save_codex_routes(self.parent.routes)
        self.parent.refresh_list(self.parent.selected_index())
        messagebox.showinfo("完成", "Codex 模型列表已保存", parent=self)

    def _close(self):
        self.closed = True
        self.destroy()


class CodexPanel(tk.Frame):
    """Provider, endpoint, model and resume-history controls for Codex."""

    def __init__(self, parent):
        super().__init__(parent)
        self.routes = load_codex_routes()
        self._build_ui()
        self.refresh_list(0)
        self.refresh_status()

    def _build_ui(self):
        top = tk.Frame(self, bg="#eef7f2", pady=5)
        top.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(top, text="Codex 当前 provider：", bg="#eef7f2", font=("", 9)).pack(side="left")
        self.current_label = tk.Label(top, text="", bg="#eef7f2", fg="#13795b", font=("", 9, "bold"))
        self.current_label.pack(side="left")
        self.model_label = tk.Label(top, text="", bg="#eef7f2", fg="#13795b", font=("", 9, "bold"))
        self.model_label.pack(side="left", padx=(18, 0))

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        left = tk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(left, text="Codex 路线", font=("", 10, "bold")).pack(anchor="w")
        list_frame = tk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        scroll = tk.Scrollbar(list_frame, orient="vertical")
        self.listbox = tk.Listbox(list_frame, font=("Consolas", 10), yscrollcommand=scroll.set, activestyle="dotbox")
        scroll.config(command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self.update_detail())
        self.listbox.bind("<Double-Button-1>", lambda _event: self.launch())
        buttons = tk.Frame(left)
        buttons.pack(fill="x", pady=(4, 0))
        for text, command in (("+", self.add), ("编辑", self.edit), ("删除", self.delete), ("上移", self.move_up), ("下移", self.move_down), ("复制", self.duplicate)):
            tk.Button(buttons, text=text, command=command).pack(side="left", padx=2)

        right = tk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="Codex 详情", font=("", 10, "bold")).pack(anchor="w")
        detail = tk.LabelFrame(right, padx=8, pady=6)
        detail.pack(fill="both", expand=True)
        self.detail_vars = {key: tk.StringVar() for key in ("name", "provider_id", "base_url", "api_key", "model", "reasoning_effort", "wire_api", "note")}
        for label, key in (("名称", "name"), ("provider ID", "provider_id"), ("API 地址", "base_url"), ("Bearer 密钥", "api_key"), ("模型", "model"), ("推理强度", "reasoning_effort"), ("wire API", "wire_api"), ("备注", "note")):
            row = tk.Frame(detail)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label + ":", width=13, anchor="w", fg="#666").pack(side="left")
            tk.Label(row, textvariable=self.detail_vars[key], anchor="w", justify="left", wraplength=300).pack(side="left", fill="x", expand=True)
        action = tk.Frame(right)
        action.pack(fill="x", pady=(10, 0))
        tk.Button(action, text="设为 Codex 全局", command=self.apply_global, bg="#13795b", fg="white", font=("", 10, "bold"), relief="flat", pady=5).pack(fill="x", pady=(0, 4))
        launch_row = tk.Frame(action)
        launch_row.pack(fill="x", pady=(0, 4))
        tk.Button(launch_row, text="启动 Codex", command=self.launch, bg="#238636", fg="white", font=("", 10, "bold"), relief="flat", pady=5).pack(side="left", fill="x", expand=True, padx=(0, 2))
        tk.Button(launch_row, text="启动 Codexx", command=self.launch_codexx, bg="#1f6f9f", fg="white", font=("", 10, "bold"), relief="flat", pady=5).pack(side="left", fill="x", expand=True, padx=(2, 0))
        resume_row = tk.Frame(action)
        resume_row.pack(fill="x", pady=(0, 4))
        tk.Button(resume_row, text="Codex resume --all", command=self.resume_codex, relief="flat", pady=4).pack(side="left", fill="x", expand=True, padx=(0, 2))
        tk.Button(resume_row, text="Codexx resume --all", command=self.resume_codexx, relief="flat", pady=4).pack(side="left", fill="x", expand=True, padx=(2, 0))
        tk.Button(action, text="Codex 模型测试表", command=self.open_model_tests, bg="#b35c00", fg="white", font=("", 10, "bold"), relief="flat", pady=5).pack(fill="x", pady=(0, 4))
        tk.Button(action, text="一键同步全部 Session 可见性", command=self.sync_history, bg="#5c3d99", fg="white", relief="flat", pady=4).pack(fill="x", pady=(0, 4))
        tk.Label(
            action,
            text="说明：可见性同步是独立的手动操作；路线切换和启动不会扫描 Session。",
            fg="#666",
            font=("", 8),
            justify="left",
            wraplength=420,
        ).pack(fill="x", pady=(2, 0))
        self.status_var = tk.StringVar(value="选择 Codex 路线后操作")
        tk.Label(right, textvariable=self.status_var, fg="#777", font=("", 8), wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))

    def selected_index(self):
        selected = self.listbox.curselection()
        return selected[0] if selected else None

    def refresh_list(self, select_index=None):
        self.listbox.delete(0, "end")
        for route in self.routes:
            label = route["name"]
            if route.get("model"):
                label += "  [" + route["model"] + "]"
            self.listbox.insert("end", label)
        if select_index is not None and self.routes:
            index = max(0, min(select_index, len(self.routes) - 1))
            self.listbox.selection_set(index)
            self.listbox.see(index)
            self.update_detail()

    def update_detail(self):
        index = self.selected_index()
        if index is None:
            return
        route = self.routes[index]
        for key in ("name", "provider_id", "base_url", "model", "reasoning_effort", "wire_api", "note"):
            self.detail_vars[key].set(route.get(key) or "(未设置)")
        self.detail_vars["api_key"].set(_mask_secret(route.get("api_key")))

    def refresh_status(self):
        config = _read_codex_config()
        self.current_label.config(text=config.get("model_provider") or "(未设置)")
        self.model_label.config(text="model: " + str(config.get("model") or "(未设置)"))

    def add(self):
        editor = CodexRouteEditor(self)
        if editor.result:
            self.routes.append(editor.result)
            save_codex_routes(self.routes)
            self.refresh_list(len(self.routes) - 1)

    def edit(self):
        index = self.selected_index()
        if index is None:
            return
        editor = CodexRouteEditor(self, self.routes[index], "编辑 Codex 路线")
        if editor.result:
            editor.result["route_id"] = self.routes[index].get("route_id", "route-" + uuid.uuid4().hex[:12])
            self.routes[index] = editor.result
            save_codex_routes(self.routes)
            self.refresh_list(index)

    def delete(self):
        index = self.selected_index()
        if index is None:
            return
        if messagebox.askyesno("确认删除", f"删除路线「{self.routes[index]['name']}」？", parent=self):
            self.routes.pop(index)
            save_codex_routes(self.routes)
            self.refresh_list(min(index, len(self.routes) - 1) if self.routes else None)

    def move_up(self):
        index = self.selected_index()
        if index is None or index == 0:
            return
        self.routes[index - 1], self.routes[index] = self.routes[index], self.routes[index - 1]
        save_codex_routes(self.routes)
        self.refresh_list(index - 1)

    def move_down(self):
        index = self.selected_index()
        if index is None or index >= len(self.routes) - 1:
            return
        self.routes[index + 1], self.routes[index] = self.routes[index], self.routes[index + 1]
        save_codex_routes(self.routes)
        self.refresh_list(index + 1)

    def duplicate(self):
        index = self.selected_index()
        if index is None:
            return
        route = copy.deepcopy(self.routes[index])
        route["name"] += " (副本)"
        route["route_id"] = "route-" + uuid.uuid4().hex[:12]
        self.routes.insert(index + 1, route)
        save_codex_routes(self.routes)
        self.refresh_list(index + 1)

    def _selected_route(self):
        index = self.selected_index()
        return self.routes[index] if index is not None else None

    def _apply(self, route):
        backup = _write_codex_config(route)
        self.refresh_status()
        backup_note = "，已备份 config.toml" if backup else ""
        self.status_var.set(f"已应用：{route['name']}{backup_note}")

    def apply_global(self):
        route = self._selected_route()
        if route is None:
            messagebox.showwarning("提示", "请先选择一条 Codex 路线", parent=self)
            return
        try:
            self._apply(route)
        except Exception as exc:
            messagebox.showerror("Codex 配置失败", str(exc), parent=self)

    def sync_history(self):
        route = self._selected_route()
        if route is None:
            return
        try:
            result = sync_codex_session_visibility(route["provider_id"])
            note = (
                f"可见性同步完成：Session {result.rollout_matching}/{result.rollout_total}"
                f"（改 {result.rollout_updates}）；索引 {result.db_matching}/{result.db_total}"
                f"（改 {result.db_updates}）；resume 普通会话 {result.picker_visible}"
            )
            if result.manifest:
                note += f"；Session 备份：{result.manifest.name}"
            self.status_var.set(note)
        except Exception as exc:
            messagebox.showerror("历史同步失败", str(exc), parent=self)

    def launch(self):
        self._launch_binary("codex")

    def launch_codexx(self):
        self._launch_binary("codexx")

    def resume_codex(self):
        self._launch_binary("codex", resume_all=True)

    def resume_codexx(self):
        self._launch_binary("codexx", resume_all=True)

    def _launch_binary(self, binary, resume_all=False):
        route = self._selected_route()
        if route is None:
            messagebox.showwarning("提示", "请先选择一条 Codex 路线", parent=self)
            return
        display_name = "Codexx" if binary == "codexx" else "Codex"
        try:
            self._apply(route)
            command = _codex_console_command(binary, resume_all)
            subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
            action = "resume --all" if resume_all else "启动"
            self.status_var.set(f"已{action} {display_name}：{route['name']}")
        except FileNotFoundError as exc:
            detail = str(exc) if str(exc) else f"找不到 {display_name} 二进制文件"
            messagebox.showerror("错误", detail, parent=self)
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc), parent=self)

    def open_model_tests(self):
        route = self._selected_route()
        if route is None:
            messagebox.showwarning("提示", "请先选择一条 Codex 路线", parent=self)
            return
        CodexModelTestDialog(self, route)
