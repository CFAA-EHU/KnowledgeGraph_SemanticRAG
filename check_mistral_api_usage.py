from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from statistics import mean


MODELS_URL = "https://api.mistral.ai/v1/models"
CHAT_URL = "https://api.mistral.ai/v1/chat/completions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida una API key de Mistral y estima consumo por peticion con una llamada minima."
    )
    parser.add_argument("--api-key", default="", help="API key de Mistral. Si no se indica, usa MISTRAL_API_KEY.")
    parser.add_argument("--model", default="mistral-small-latest", help="Modelo para la llamada de prueba.")
    parser.add_argument("--prompt", default="Reply with the single word: ok", help="Prompt minimo para medir uso.")
    parser.add_argument("--repeats", type=int, default=1, help="Numero de llamadas de prueba a ejecutar.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Pausa entre llamadas de prueba.")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8,
        help="Maximo de tokens de salida para la llamada de prueba.",
    )
    return parser.parse_args()


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def http_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, headers: dict[str, str], payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, headers=headers, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def validate_api_key(headers: dict[str, str]) -> dict:
    status, payload = http_get_json(MODELS_URL, headers)
    models = payload.get("data", []) if isinstance(payload, dict) else []
    return {
        "auth_ok": True,
        "http_status": status,
        "model_count": len(models),
        "sample_models": [model.get("id") for model in models[:8] if isinstance(model, dict)],
    }


def run_probe(headers: dict[str, str], *, model: str, prompt: str, max_tokens: int) -> dict:
    started = time.perf_counter()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    status, response_payload = http_post_json(CHAT_URL, headers, payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    usage = response_payload.get("usage", {}) if isinstance(response_payload, dict) else {}
    choices = response_payload.get("choices", []) if isinstance(response_payload, dict) else []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
    return {
        "status": "ok",
        "http_status": status,
        "latency_ms": elapsed_ms,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "response_preview": content[:120],
    }


def classify_http_error(exc: urllib.error.HTTPError) -> dict:
    body = exc.read().decode("utf-8", errors="ignore")
    status = "http_error"
    if exc.code == 429:
        status = "rate_limited"
    return {
        "status": status,
        "http_status": exc.code,
        "body_preview": body[:300],
    }


def main() -> int:
    args = parse_args()
    api_key = args.api_key.strip() or os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta la API key. Usa --api-key o define MISTRAL_API_KEY.")

    headers = build_headers(api_key)

    try:
        validation = validate_api_key(headers)
    except urllib.error.HTTPError as exc:
        print(json.dumps({"auth_ok": False, **classify_http_error(exc)}, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:
        print(json.dumps({"auth_ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    runs: list[dict] = []
    for index in range(args.repeats):
        try:
            run_result = run_probe(headers, model=args.model, prompt=args.prompt, max_tokens=args.max_tokens)
        except urllib.error.HTTPError as exc:
            run_result = classify_http_error(exc)
        except Exception as exc:
            run_result = {"status": "error", "error": str(exc)}
        run_result["run_index"] = index + 1
        runs.append(run_result)
        if index < args.repeats - 1 and args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    ok_runs = [run for run in runs if run.get("status") == "ok"]
    rate_limited_runs = [run for run in runs if run.get("status") == "rate_limited"]

    summary = {
        "auth_ok": True,
        "model": args.model,
        "repeats": args.repeats,
        "successful_runs": len(ok_runs),
        "rate_limited_runs": len(rate_limited_runs),
        "other_failed_runs": len(runs) - len(ok_runs) - len(rate_limited_runs),
        "avg_latency_ms": round(mean(run["latency_ms"] for run in ok_runs), 1) if ok_runs else None,
        "avg_prompt_tokens": round(mean(run["usage"]["prompt_tokens"] for run in ok_runs if run["usage"]["prompt_tokens"] is not None), 2)
        if ok_runs
        else None,
        "avg_completion_tokens": round(mean(run["usage"]["completion_tokens"] for run in ok_runs if run["usage"]["completion_tokens"] is not None), 2)
        if ok_runs
        else None,
        "avg_total_tokens": round(mean(run["usage"]["total_tokens"] for run in ok_runs if run["usage"]["total_tokens"] is not None), 2)
        if ok_runs
        else None,
        "can_estimate_per_request_usage": bool(ok_runs),
        "can_read_remaining_quota_directly": False,
        "quota_note": "Mistral no expone aqui un endpoint publico simple para leer tokens restantes; este script solo mide consumo por peticion y detecta 429.",
    }

    output = {
        "validation": validation,
        "summary": summary,
        "runs": runs,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if ok_runs else 1


if __name__ == "__main__":
    raise SystemExit(main())
