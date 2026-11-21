"""Optional JSON model adapter for Gemini, OpenAI, and local Ollama."""

import json
import os
import time
from urllib.request import Request, urlopen


def empty_usage(error=None, elapsed_ms=0):
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "ms": int(elapsed_ms),
    }
    if error:
        usage["error"] = str(error)[:300]
    return usage


def parse_json_response(content):
    if not content:
        return None
    content = str(content).strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _cost(input_tokens, output_tokens):
    try:
        input_rate = float(os.getenv("MODEL_INPUT_USD_PER_1M", "0") or 0)
        output_rate = float(os.getenv("MODEL_OUTPUT_USD_PER_1M", "0") or 0)
    except (TypeError, ValueError):
        return 0.0
    return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8)


def _openai(system, user):
    from openai import OpenAI

    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return None, "OPENAI_API_KEY is not configured."
    client = OpenAI(api_key=key, timeout=20.0, max_retries=1)
    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    finally:
        client.close()
    content = response.choices[0].message.content if response.choices else ""
    usage = response.usage
    prompt = int(usage.prompt_tokens or 0) if usage else 0
    completion = int(usage.completion_tokens or 0) if usage else 0
    return parse_json_response(content), {
        "input_tokens": prompt,
        "output_tokens": completion,
        "cost_usd": _cost(prompt, completion),
    }


def _gemini(system, user):
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None, "GEMINI_API_KEY is not configured."
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=20_000),
    )
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=json.dumps({"question": user}, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
    finally:
        client.close()
    metadata = getattr(response, "usage_metadata", None)
    prompt = int(getattr(metadata, "prompt_token_count", 0) or 0) if metadata else 0
    completion = int(getattr(metadata, "candidates_token_count", 0) or 0) if metadata else 0
    return parse_json_response(response.text or ""), {
        "input_tokens": prompt,
        "output_tokens": completion,
        "cost_usd": _cost(prompt, completion),
    }


def _ollama(system, user):
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    endpoint = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat").rstrip("/")
    body = json.dumps({
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    request = Request(endpoint, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = ((result.get("message") or {}).get("content") or "")
    prompt = int(result.get("prompt_eval_count") or 0)
    completion = int(result.get("eval_count") or 0)
    return parse_json_response(content), {
        "input_tokens": prompt,
        "output_tokens": completion,
        "cost_usd": 0.0,
    }


def complete_json(system, user):
    """Call the configured provider; imports and network access stay optional."""
    started = time.perf_counter()
    provider = os.getenv("MODEL_PROVIDER", "none").strip().lower()
    if provider in ("", "none", "off", "disabled"):
        return None, empty_usage(elapsed_ms=(time.perf_counter() - started) * 1000)

    providers = {
        "openai": _openai,
        "gemini": _gemini,
        "google": _gemini,
        "ollama": _ollama,
    }
    call = providers.get(provider)
    if call is None:
        return None, empty_usage(f"Unsupported MODEL_PROVIDER: {provider}")

    try:
        data, usage = call(system, user)
        elapsed = int((time.perf_counter() - started) * 1000)
        if not isinstance(data, dict):
            return None, empty_usage("Provider returned invalid JSON.", elapsed)
        usage["ms"] = elapsed
        return data, usage
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        # Avoid leaking request headers, prompt content, or credentials.
        return None, empty_usage(type(exc).__name__ + ": model request failed", elapsed)
