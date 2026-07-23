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
