import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codex_panel


class CodexPanelCoreTests(unittest.TestCase):
    def test_routes_import_from_existing_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "config.toml"
            config.write_text(
                'model = "gpt-test"\n'
                'model_provider = "edge"\n'
                'model_reasoning_effort = "high"\n'
                '[model_providers.edge]\n'
                'name = "Edge API"\n'
                'base_url = "https://edge.example/v1"\n'
                'wire_api = "responses"\n',
                encoding="utf-8",
            )
            with mock.patch.object(codex_panel, "CODEX_CONFIG_FILE", config):
                routes = codex_panel._routes_from_codex_config()
            self.assertEqual(len(routes), 1)
            self.assertEqual(routes[0]["provider_id"], "edge")
            self.assertEqual(routes[0]["model"], "gpt-test")
            self.assertEqual(routes[0]["reasoning_effort"], "high")

    def test_write_config_preserves_unrelated_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "config.toml"
            config.write_text(
                '# keep this comment\n'
                'model = "old"\n'
                'model_provider = "old_provider"\n'
                '[history]\n'
                'persistence = "save-all"\n'
                '[model_providers.example]\n'
                'supports_websockets = false\n'
                'http_headers = { x-cockpit-instance-id = ".codex" }\n',
                encoding="utf-8",
            )
            route = codex_panel._normalise_route({
                "name": "Example",
                "provider_id": "example",
                "base_url": "https://api.example/v1",
                "api_key": "secret",
                "model": "gpt-example",
                "reasoning_effort": "xhigh",
                "wire_api": "responses",
            })
            with mock.patch.object(codex_panel, "CODEX_HOME", root), mock.patch.object(
                codex_panel, "CODEX_CONFIG_FILE", config
            ):
                backup = codex_panel._write_codex_config(route)
            text = config.read_text(encoding="utf-8")
            parsed = codex_panel.tomllib.loads(text)
            self.assertIn("# keep this comment", text)
            self.assertTrue(backup.exists())
            self.assertEqual(parsed["history"], {"persistence": "save-all"})
            self.assertEqual(parsed["model_provider"], "example")
            self.assertEqual(parsed["model"], "gpt-example")
            self.assertEqual(parsed["model_providers"]["example"]["base_url"], "https://api.example/v1")
            self.assertEqual(parsed["model_providers"]["example"]["experimental_bearer_token"], "secret")
            self.assertEqual(parsed["model_providers"]["example"]["supports_websockets"], False)
            self.assertEqual(
                parsed["model_providers"]["example"]["http_headers"],
                {"x-cockpit-instance-id": ".codex"},
            )

    def test_history_sync_handles_longer_provider_and_updates_db(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sessions = root / "sessions" / "2026" / "01" / "01"
            sessions.mkdir(parents=True)
            rollout = sessions / "rollout-test.jsonl"
            first = json.dumps({
                "type": "session_meta",
                "payload": {"id": "thread-1", "model_provider": "mc"},
            }, separators=(",", ":")).encode() + b"\n"
            rollout.write_bytes(first + b'{"type":"event_msg","payload":{}}\n')
            database = root / "state_5.sqlite"
            db = sqlite3.connect(database)
            with db:
                db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, model_provider TEXT NOT NULL)")
                db.execute("INSERT INTO threads VALUES ('thread-1', 'mc')")
            db.close()
            backup_dir = root / "session-meta-backups"
            db_backup_dir = root / "db-backups"
            with mock.patch.object(codex_panel, "CODEX_HOME", root), mock.patch.object(
                codex_panel, "CODEX_SESSION_BACKUP_DIR", backup_dir
            ), mock.patch.object(
                codex_panel, "CODEX_DB_BACKUP_DIR", db_backup_dir
            ), mock.patch.object(codex_panel, "CODEX_DB_FILE", database):
                changed, manifest = codex_panel.sync_codex_history_provider("codex_local_access")
            with rollout.open("rb") as stream:
                updated = json.loads(stream.readline())
                tail = stream.read()
            db = sqlite3.connect(database)
            provider = db.execute("SELECT model_provider FROM threads").fetchone()[0]
            db.close()
            db_backup = next(db_backup_dir.glob("state_5.sqlite.bak-codex-switcher-*"))
            db = sqlite3.connect(db_backup)
            backup_provider = db.execute("SELECT model_provider FROM threads").fetchone()[0]
            db.close()
            self.assertEqual(changed, 1)
            self.assertTrue(manifest.exists())
            self.assertEqual(len(list(db_backup_dir.glob("state_5.sqlite.bak-codex-switcher-*"))), 1)
            self.assertEqual(backup_provider, "mc")
            self.assertEqual(updated["payload"]["model_provider"], "codex_local_access")
            self.assertIn(b'event_msg', tail)
            self.assertEqual(provider, "codex_local_access")

    def test_visibility_sync_switches_existing_durable_triggers_to_new_route(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "state_5.sqlite"
            db = sqlite3.connect(database)
            with db:
                db.execute("""
                    CREATE TABLE threads (
                        id TEXT PRIMARY KEY,
                        model_provider TEXT NOT NULL,
                        cwd TEXT NOT NULL,
                        archived INTEGER NOT NULL DEFAULT 0,
                        preview TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT 'cli'
                    )
                """)
                db.execute(
                    "INSERT INTO threads (id, model_provider, cwd, preview) VALUES (?, ?, ?, ?)",
                    ("thread-old", "mc", r"D:\\old", "old session"),
                )
            db.close()

            with mock.patch.object(codex_panel, "CODEX_HOME", root), mock.patch.object(
                codex_panel, "CODEX_SESSION_BACKUP_DIR", root / "session-meta-backups"
            ), mock.patch.object(
                codex_panel, "CODEX_DB_BACKUP_DIR", root / "db-backups"
            ), mock.patch.object(codex_panel, "CODEX_DB_FILE", database):
                codex_panel.sync_codex_session_visibility("mc")
                result = codex_panel.sync_codex_session_visibility("cpa")

            db = sqlite3.connect(database)
            with db:
                old_row = db.execute(
                    "SELECT model_provider, cwd FROM threads WHERE id = 'thread-old'"
                ).fetchone()
                setting = db.execute(
                    "SELECT model_provider FROM codex_resume_visibility_settings WHERE id = 1"
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO threads (id, model_provider, cwd, preview) VALUES (?, ?, ?, ?)",
                    ("thread-new", "another-route", r"E:\\new", "new session"),
                )
                new_row = db.execute(
                    "SELECT model_provider, cwd FROM threads WHERE id = 'thread-new'"
                ).fetchone()
            db.close()

            self.assertEqual(result.db_updates, 1)
            self.assertEqual(result.db_matching, 1)
            self.assertEqual(setting, "cpa")
            self.assertEqual(old_row, ("cpa", r"\\?\D:\\old"))
            self.assertEqual(new_row, ("cpa", r"\\?\E:\\new"))

    def test_codex_and_codexx_console_commands_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codexx = Path(temp_dir) / "codexx.exe"
            codexx.touch()
            with mock.patch.object(codex_panel, "CODEXX_EXE", codexx):
                self.assertEqual(
                    codex_panel._codex_console_command("codexx", action="resume"),
                    ["cmd.exe", "/k", str(codexx), "resume"],
                )
            self.assertEqual(
                codex_panel._codex_console_command("codex"),
                ["cmd.exe", "/k", "codex", "--yolo"],
            )
            self.assertEqual(
                codex_panel._codex_console_command(
                    "codex", action="resume_id", session_id="019f-test-session"
                ),
                ["cmd.exe", "/k", "codex", "resume", "019f-test-session"],
            )

    def test_fast_visibility_sync_does_not_scan_rollout_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "state_5.sqlite"
            db = sqlite3.connect(database)
            with db:
                db.execute("""
                    CREATE TABLE threads (
                        id TEXT PRIMARY KEY,
                        model_provider TEXT NOT NULL,
                        archived INTEGER NOT NULL DEFAULT 0,
                        preview TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT 'cli'
                    )
                """)
                db.execute(
                    "INSERT INTO threads (id, model_provider, preview) VALUES (?, ?, ?)",
                    ("thread-fast", "old", "visible session"),
                )
            db.close()
            with mock.patch.object(codex_panel, "CODEX_DB_FILE", database), mock.patch.object(
                codex_panel, "CODEX_DB_BACKUP_DIR", root / "db-backups"
            ), mock.patch.object(
                codex_panel, "_iter_rollouts", side_effect=AssertionError("rollouts scanned")
            ):
                result = codex_panel.sync_codex_session_visibility("fast")
            self.assertEqual(result.rollout_total, 0)
            self.assertEqual(result.db_matching, 1)
            self.assertEqual(result.picker_visible, 1)

    def test_applying_route_never_syncs_session_visibility(self):
        panel = object.__new__(codex_panel.CodexPanel)
        panel.refresh_status = mock.Mock()
        panel.status_var = mock.Mock()
        route = codex_panel._normalise_route({
            "name": "Fast route",
            "provider_id": "fast",
            "wire_api": "responses",
        })
        with mock.patch.object(codex_panel, "_write_codex_config", return_value=None), mock.patch.object(
            codex_panel, "sync_codex_session_visibility"
        ) as sync_visibility:
            panel._apply(route)
        sync_visibility.assert_not_called()
        panel.refresh_status.assert_called_once_with()
        panel.status_var.set.assert_called_once_with("已应用：Fast route")

    def test_resume_database_optimizer_removes_old_sync_and_compacts_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "state_5.sqlite"
            db = sqlite3.connect(database)
            with db:
                db.execute("""
                    CREATE TABLE threads (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        first_user_message TEXT NOT NULL,
                        preview TEXT NOT NULL,
                        model_provider TEXT NOT NULL
                    )
                """)
                db.execute("""
                    CREATE TABLE codex_resume_visibility_settings (
                        id INTEGER PRIMARY KEY,
                        model_provider TEXT NOT NULL
                    )
                """)
                db.execute("""
                    CREATE TRIGGER codex_resume_visibility_after_insert
                    AFTER INSERT ON threads BEGIN SELECT 1; END
                """)
                db.execute("""
                    CREATE TRIGGER codex_resume_visibility_after_update
                    AFTER UPDATE ON threads BEGIN SELECT 1; END
                """)
                db.execute(
                    "INSERT INTO threads VALUES (?, ?, ?, ?, ?)",
                    ("thread-1", "t" * 5000, "m" * 5000, "p" * 5000, "test"),
                )
            db.close()

            with mock.patch.object(codex_panel, "CODEX_DB_FILE", database):
                result = codex_panel.optimize_codex_resume_database()

            db = sqlite3.connect(database)
            lengths = db.execute("""
                SELECT length(title), length(first_user_message), length(preview)
                FROM threads
            """).fetchone()
            old_objects = db.execute("""
                SELECT name FROM sqlite_master
                WHERE name LIKE 'codex_resume_visibility_%'
            """).fetchall()
            integrity = db.execute("PRAGMA quick_check").fetchone()[0]
            db.close()
            self.assertEqual(lengths, (512, 2048, 2048))
            self.assertEqual(old_objects, [])
            self.assertEqual(integrity, "ok")
            self.assertEqual(result.truncated_rows, 1)
            self.assertTrue(result.removed_visibility_sync)
            self.assertTrue(result.vacuumed)

    def test_align_one_session_provider_updates_db_and_rollout_meta(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sessions = root / "sessions" / "2026" / "01" / "01"
            sessions.mkdir(parents=True)
            rollout = sessions / "rollout-2026-01-01T00-00-00-019f-test.jsonl"
            first = json.dumps({
                "type": "session_meta",
                "payload": {
                    "id": "019f-test-session",
                    "cwd": r"D:\\project",
                    "source": "cli",
                    "model_provider": "cpa",
                },
            }, separators=(",", ":")).encode() + b"\n"
            rollout.write_bytes(first + b'{"type":"event_msg","payload":{}}\n')
            database = root / "state_5.sqlite"
            db = sqlite3.connect(database)
            with db:
                db.execute("""
                    CREATE TABLE threads (
                        id TEXT PRIMARY KEY,
                        model_provider TEXT NOT NULL,
                        rollout_path TEXT NOT NULL
                    )
                """)
                db.execute(
                    "INSERT INTO threads VALUES (?, ?, ?)",
                    ("019f-test-session", "mc", str(rollout)),
                )
            db.close()

            with mock.patch.object(codex_panel, "CODEX_DB_FILE", database):
                result = codex_panel.align_codex_session_provider(
                    "019f-test-session", "xin gpt5.6sol"
                )

            db = sqlite3.connect(database)
            provider = db.execute(
                "SELECT model_provider FROM threads WHERE id = ?",
                ("019f-test-session",),
            ).fetchone()[0]
            db.close()
            updated = json.loads(rollout.read_bytes().splitlines()[0])
            self.assertEqual(provider, "xin gpt5.6sol")
            self.assertEqual(updated["payload"]["model_provider"], "xin gpt5.6sol")
            self.assertEqual(result, {"db_updated": True, "rollout_updated": True})

    def test_resume_picker_does_not_apply_selected_route(self):
        panel = object.__new__(codex_panel.CodexPanel)
        panel._launch_binary = mock.Mock()
        panel.resume_codex()
        panel._launch_binary.assert_called_once_with(
            "codex", action="resume", apply_route=False
        )

    def test_openai_endpoint_builder(self):
        self.assertEqual(
            codex_panel._openai_url("https://api.example/v1", "responses"),
            "https://api.example/v1/responses",
        )
        self.assertEqual(
            codex_panel._openai_url("https://api.example", "chat/completions"),
            "https://api.example/v1/chat/completions",
        )
        self.assertEqual(
            codex_panel._openai_url("https://api.example/v1/responses", "responses"),
            "https://api.example/v1/responses",
        )

    def test_write_config_rejects_unsupported_wire_api(self):
        route = codex_panel._normalise_route({
            "name": "Legacy Chat",
            "provider_id": "legacy",
            "wire_api": "chat",
        })
        with self.assertRaisesRegex(ValueError, "仅支持 wire API：responses"):
            codex_panel._write_codex_config(route)


if __name__ == "__main__":
    unittest.main()
