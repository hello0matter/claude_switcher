"""Small, repeatable model capability benchmark for route comparisons.

This is intentionally not an IQ test. It is a low-cost black-box smoke
benchmark for comparing the same model through different providers.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from app_network import describe_network_error, open_app_request


BENCHMARK_TASKS = (
    {
        "id": "arithmetic",
        "category": "算术",
        "prompt": (
            "Solve this exactly. A box has 7 rows of 8 red balls and 5 blue balls "
            "are removed. How many balls remain? Reply only as FINAL: <integer>."
        ),
        "expected": "51",
    },
    {
        "id": "sequence",
        "category": "规律",
        "prompt": (
            "Find the next number in 2, 6, 12, 20, 30, ?. Reply only as "
            "FINAL: <integer>."
        ),
        "expected": "42",
    },
    {
        "id": "logic",
        "category": "逻辑",
        "prompt": (
            "Exactly one statement is true: A says 4 is odd; B says 9 is even; "
            "C says 2+2=4. Which letter is true? Reply only as FINAL: <A|B|C>."
        ),
        "expected": "C",
    },
    {
        "id": "code",
        "category": "代码",
        "prompt": (
            "What is printed by this Python code: x = [1, 2, 3]; print(sum(i*i "
            "for i in x if i > 1))? Reply only as FINAL: <integer>."
        ),
        "expected": "13",
    },
    {
        "id": "constraint",
        "category": "约束",
        "prompt": (
            "Mia is taller than Noah. Noah is taller than Omar. Pia is shorter "
            "than Mia but taller than Noah. Who is the second tallest? Reply only "
            "as FINAL: <name>."
        ),
        "expected": "Pia",
    },
    {
        "id": "instruction",
        "category": "指令遵循",
        "prompt": (
            "Answer the question but do not explain: Is 17 an even number? Reply "
            "only as FINAL: YES or NO."
        ),
        "expected": "NO",
    },
)


def _endpoint(base_url, suffix):
    base = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    if base.endswith("/" + suffix):
        return base
    if base.endswith("/v1"):
        return base + "/" + suffix
    return base + "/v1/" + suffix


def _objects(body):
    objects = []
    for raw in str(body or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("event:") or line == "data: [DONE]":
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        try:
            item = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(item, dict):
            objects.append(item)
    if not objects:
        try:
            item = json.loads(body)
        except (TypeError, ValueError):
            item = None
        if isinstance(item, dict):
            objects.append(item)
    return objects


def _usage(objects):
    input_tokens = output_tokens = 0
    found = False
    for item in objects:
        candidates = [item]
        if isinstance(item.get("response"), dict):
            candidates.append(item["response"])
        if isinstance(item.get("message"), dict):
            candidates.append(item["message"])
        for candidate in candidates:
            usage = candidate.get("usage")
            if not isinstance(usage, dict):
                continue
            input_value = usage.get("input_tokens", usage.get("input_token_count"))
            output_value = usage.get("output_tokens", usage.get("output_token_count"))
            if isinstance(input_value, int):
                input_tokens += input_value
                found = True
            if isinstance(output_value, int):
                output_tokens += output_value
                found = True
    return (input_tokens + output_tokens) if found else None


def _response_text(objects, kind):
    texts = []
    errors = []
    for item in objects:
        event_type = item.get("type")
        if event_type in {"error", "response.failed"} or item.get("error"):
            errors.append(str(item.get("message") or item.get("error") or event_type))
        if kind == "codex":
            if event_type in {"response.output_text.delta", "response.output_text.done"}:
                if isinstance(item.get("delta"), str):
                    texts.append(item["delta"])
                elif isinstance(item.get("text"), str):
                    texts.append(item["text"])
            response = item.get("response")
            if isinstance(response, dict):
                if isinstance(response.get("output_text"), str):
                    texts.append(response["output_text"])
                for output in response.get("output", []):
                    for content in output.get("content", []) if isinstance(output, dict) else []:
                        if isinstance(content, dict) and isinstance(content.get("text"), str):
                            texts.append(content["text"])
            if isinstance(item.get("output_text"), str):
                texts.append(item["output_text"])
        else:
            if event_type == "content_block_delta":
                delta = item.get("delta")
                if isinstance(delta, dict) and isinstance(delta.get("text"), str):
                    texts.append(delta["text"])
            if event_type == "content_block" and isinstance(item.get("text"), str):
                texts.append(item["text"])
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    texts.append(content["text"])
    return "".join(texts).strip(), errors


def extract_final_answer(text):
    """Extract the compact answer after FINAL:, tolerating Markdown punctuation."""
    match = re.search(r"\bFINAL\s*[:：]\s*([A-Za-z0-9]+)", str(text or ""), re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()
    return ""


def _request_task(route, kind, task, timeout):
    model = str(route.get("model") or "").strip()
    if not model:
        return {"ok": False, "answer": "", "text": "", "latency_ms": "", "tokens": None, "error": "路线没有设置模型"}
    if kind == "codex":
        url = _endpoint(route.get("base_url"), "responses")
        payload = {
            "model": model,
            "instructions": "Do not call tools. Follow the requested FINAL format exactly.",
            "input": task["prompt"],
            "stream": True,
            "store": False,
        }
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "codex-cli/route-switcher"}
        api_key = route.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
    else:
        url = _endpoint(route.get("base_url") or "https://api.anthropic.com", "messages")
        payload = {"model": model, "max_tokens": 48, "system": "Do not call tools. Follow the requested FINAL format exactly.", "messages": [{"role": "user", "content": task["prompt"]}], "stream": True}
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "Anthropic-Version": "2023-06-01", "User-Agent": "claude-code/route-switcher"}
        auth_var = str(route.get("auth_var") or "ANTHROPIC_AUTH_TOKEN").upper()
        api_key = route.get("api_key") or os.environ.get(auth_var, "")
        if not api_key:
            alternate = "ANTHROPIC_API_KEY" if auth_var != "ANTHROPIC_API_KEY" else "ANTHROPIC_AUTH_TOKEN"
            api_key = os.environ.get(alternate, "")
        if api_key:
            if auth_var == "ANTHROPIC_API_KEY":
                headers["x-api-key"] = api_key
            else:
                headers["Authorization"] = "Bearer " + api_key
    started = time.perf_counter()
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with open_app_request(request, timeout=timeout) as response:
            body = response.read(128 * 1024).decode("utf-8", errors="replace")
            status = response.status
        objects = _objects(body)
        text, errors = _response_text(objects, kind)
        answer = extract_final_answer(text)
        error = "; ".join(errors)[:400]
        if status != 200:
            error = error or f"HTTP {status}"
        return {"ok": status == 200 and bool(answer) and not errors, "answer": answer, "text": text, "latency_ms": f"{(time.perf_counter() - started) * 1000:.0f}", "tokens": _usage(objects), "error": error}
    except urllib.error.HTTPError as exc:
        detail = exc.read(800).decode("utf-8", errors="replace")
        return {"ok": False, "answer": "", "text": "", "latency_ms": f"{(time.perf_counter() - started) * 1000:.0f}", "tokens": None, "error": f"HTTP {exc.code}: {detail[:400]}"}
    except Exception as exc:
        return {"ok": False, "answer": "", "text": "", "latency_ms": f"{(time.perf_counter() - started) * 1000:.0f}", "tokens": None, "error": describe_network_error(exc)}


def run_route_benchmark(route, kind, timeout=45):
    results = []
    for task in BENCHMARK_TASKS:
        result = _request_task(route, kind, task, timeout)
        result.update(id=task["id"], category=task["category"], expected=task["expected"], passed=result["answer"] == task["expected"].lower())
        results.append(result)
    passed = sum(1 for result in results if result["passed"])
    token_values = [result["tokens"] for result in results if result["tokens"] is not None]
    latency_values = [float(result["latency_ms"]) for result in results if result["latency_ms"]]
    return {"score": passed, "total": len(results), "percent": round(passed / len(results) * 100), "tokens": sum(token_values) if token_values else None, "latency_ms": round(sum(latency_values)), "results": results}
