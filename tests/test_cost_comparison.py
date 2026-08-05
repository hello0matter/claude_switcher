import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cost_comparison


class CostComparisonTests(unittest.TestCase):
    def test_default_usage_url_uses_route_site_root(self):
        self.assertEqual(
            cost_comparison.default_usage_url("https://ai777.ai/v1"),
            "https://ai777.ai/usage",
        )

    def test_cost_ratio_labels_compare_same_unit_values(self):
        self.assertEqual(
            cost_comparison.cost_ratio_labels(["0.20", "￥0.50", "bad", "0"]),
            ["最低 · 1.00×", "2.50×", "请输入数字", "0（网页未扣费）"],
        )

    def test_cost_data_round_trip(self):
        data = {
            "entries": {
                "codex:route-1:gpt-test": {
                    "usage_url": "https://example.test/usage",
                    "actual_cost": "0.25",
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "costs.json"
            with mock.patch.object(cost_comparison, "COST_DATA_FILE", path):
                cost_comparison.save_cost_data(data)
                loaded = cost_comparison.load_cost_data()

        self.assertEqual(loaded, data)


if __name__ == "__main__":
    unittest.main()
