import threading
import time
import unittest

import prompt_test_dialog


class PromptTestDialogHelpers(unittest.TestCase):
    def test_worker_limit_clamps_to_selected_rows(self):
        self.assertEqual(prompt_test_dialog._worker_limit("3", 10), 3)
        self.assertEqual(prompt_test_dialog._worker_limit("0", 10), 1)
        self.assertEqual(prompt_test_dialog._worker_limit("99", 4), 4)
        self.assertEqual(prompt_test_dialog._worker_limit("bad", 5), 3)
        self.assertEqual(prompt_test_dialog._worker_limit("2", 0), 1)

    def test_run_uses_bounded_concurrency(self):
        dialog = object.__new__(prompt_test_dialog.PromptTestDialog)
        dialog.rows = [{"item": str(index)} for index in range(6)]
        dialog._post = lambda *_args: None
        lock = threading.Lock()
        active = 0
        peak = 0
        completed = 0

        def fake_run_one(_row, _batch):
            nonlocal active, peak, completed
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
                completed += 1

        dialog._run_one = fake_run_one
        dialog._run({"workers": 2})

        self.assertEqual(peak, 2)
        self.assertEqual(completed, 6)


if __name__ == "__main__":
    unittest.main()
