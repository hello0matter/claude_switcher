import unittest

from benchmark import _objects, _response_text, extract_final_answer, generate_benchmark_tasks


class BenchmarkTests(unittest.TestCase):
    def test_extract_final_answer_tolerates_markdown_and_case(self):
        self.assertEqual(extract_final_answer("I checked it. **FINAL: 51**"), "51")
        self.assertEqual(extract_final_answer("FINAL：no"), "no")
        self.assertEqual(extract_final_answer("no marker"), "")

    def test_parse_codex_sse_output_and_usage(self):
        body = (
            'data: {"type":"response.output_text.delta","delta":"FINAL: "}\n'
            'data: {"type":"response.output_text.delta","delta":"51"}\n'
            'data: {"type":"response.completed","response":{"usage":{"input_tokens":12,"output_tokens":4}}}\n'
        )
        objects = _objects(body)
        text, errors = _response_text(objects, "codex")
        self.assertEqual(text, "FINAL: 51")
        self.assertEqual(errors, [])

    def test_parse_claude_sse_output(self):
        body = (
            'event: content_block_delta\n'
            'data: {"type":"content_block_delta","delta":{"text":"FINAL: NO"}}\n'
            'data: {"type":"message_stop"}\n'
        )
        text, errors = _response_text(_objects(body), "claude")
        self.assertEqual(text, "FINAL: NO")
        self.assertEqual(errors, [])

    def test_generated_tasks_are_reproducible_and_cover_all_categories(self):
        first = generate_benchmark_tasks(30, seed=123)
        second = generate_benchmark_tasks(30, seed=123)
        self.assertEqual(first, second)
        self.assertEqual({task["category"] for task in first}, {"算术", "规律", "逻辑", "代码", "约束", "指令遵循"})


if __name__ == "__main__":
    unittest.main()
