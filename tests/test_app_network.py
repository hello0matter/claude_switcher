import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app_network


class AppNetworkTests(unittest.TestCase):
    def test_network_config_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "network.json"
            with mock.patch.object(app_network, "NETWORK_CONFIG_FILE", path):
                app_network.save_network_config(
                    {"mode": "socks5h", "host": "127.0.0.1", "port": 7891}
                )
                loaded = app_network.load_network_config()

        self.assertEqual(
            loaded,
            {"mode": "socks5h", "host": "127.0.0.1", "port": 7891},
        )

    def test_socks_mode_uses_remote_dns_handler(self):
        opener = app_network.build_app_opener(
            {"mode": "socks5h", "host": "127.0.0.1", "port": 7891}
        )
        handlers = [
            handler
            for handler in opener.handlers
            if isinstance(handler, app_network._SocksProxyHandler)
        ]
        self.assertEqual(len(handlers), 1)
        self.assertEqual(
            handlers[0].config,
            {"mode": "socks5h", "host": "127.0.0.1", "port": 7891},
        )

    def test_dns_error_recommends_remote_dns_only_in_direct_mode(self):
        with mock.patch.object(
            app_network,
            "load_network_config",
            return_value={"mode": "direct", "host": "127.0.0.1", "port": 7891},
        ):
            message = app_network.describe_network_error(
                OSError(11001, "getaddrinfo failed")
            )

        self.assertIn("SOCKS5（远程 DNS）", message)

    def test_proxy_refusal_explains_10061(self):
        with mock.patch.object(
            app_network,
            "load_network_config",
            return_value={"mode": "http", "host": "127.0.0.1", "port": 7891},
        ):
            message = app_network.describe_network_error(
                OSError(10061, "No connection could be made")
            )

        self.assertIn("127.0.0.1:7891", message)
        self.assertIn("WinError 10061", message)


if __name__ == "__main__":
    unittest.main()
