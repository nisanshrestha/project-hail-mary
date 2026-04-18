#!/usr/bin/env python3
"""Exercise the FastAPI AI path: mode check → AI on → triage text that hits Modal Llama.

Usage (from repo root, API running on :8000):
  python scripts/test_ai_integration.py
  python scripts/test_ai_integration.py --base-url http://127.0.0.1:8000
  python scripts/test_ai_integration.py --briefing-only   # name lookup only (briefing path)

Requires .env with LLM_BACKEND=modal, MODAL_APP_NAME=..., and valid Modal auth for the server process.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")


def _req(
    method: str,
    base: str,
    path: str,
    body: dict | None = None,
    timeout: float = 180.0,
) -> tuple[int, dict | list | str]:
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        code = e.code
    try:
        parsed: dict | list = json.loads(raw)
    except json.JSONDecodeError:
        return code, raw
    return code, parsed


def main() -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(description="Test Hail Mary AI (Modal) integration via HTTP API.")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    p.add_argument(
        "--briefing-only",
        action="store_true",
        help="Only test patient briefing (name-only), not triage+Llama.",
    )
    args = p.parse_args()
    base = args.base_url

    print("=== GET /api/mode ===")
    code, data = _req("GET", base, "/api/mode", timeout=30.0)
    if code != 200:
        print(f"FAIL HTTP {code}: {data}")
        return 1
    print(json.dumps(data, indent=2))
    if not isinstance(data, dict):
        return 1
    if not data.get("ai_available"):
        print(
            "\nWARNING: ai_available is false — fix LLM_BACKEND, MODAL_APP_NAME, "
            "Modal token, and restart the API before expecting Llama output.\n"
        )
    if data.get("llm_backend") != "modal":
        print(
            f"\nNOTE: llm_backend is {data.get('llm_backend')!r} (expected 'modal' for this script's intent).\n"
        )

    print("\n=== POST /api/mode { mode: ai } ===")
    code, data = _req("POST", base, "/api/mode", {"mode": "ai"}, timeout=30.0)
    if code != 200:
        print(f"FAIL HTTP {code}: {data}")
        return 1
    print(json.dumps(data, indent=2))
    if isinstance(data, dict) and data.get("mode") != "ai":
        print("WARNING: Server did not switch to AI mode (check ai_available).")

    if args.briefing_only:
        text = "Santos"
        print(f'\n=== POST /api/voice/text (briefing) "{text}" ===')
    else:
        # Triage path: seed soldier "Morrison" + injury phrase that matches engine / fuzzy match
        text = (
            "Morrison has a gunshot wound to the chest, tension is building, need chest seal now"
        )
        print(f'\n=== POST /api/voice/text (triage → generate_response → Modal) ===\nText:\n{text}\n')

    code, data = _req("POST", base, "/api/voice/text", {"text": text}, timeout=300.0)
    if code != 200:
        print(f"FAIL HTTP {code}: {data}")
        return 1
    if not isinstance(data, dict):
        print(data)
        return 1

    print("mode:", data.get("mode"))
    print("transcript:", data.get("transcript", "")[:200])
    rt = data.get("response_text") or ""
    print("\n--- response_text (first 2000 chars) ---\n")
    print(rt[:2000] + ("…" if len(rt) > 2000 else ""))
    print("\n--- triage_queue length ---", len(data.get("triage_queue") or []))
    audio = data.get("audio_b64") or ""
    print("audio_b64 length (TTS):", len(audio))

    if not args.briefing_only and "===" in rt and "TREATMENT:" in rt and "TRIAGE REPORT" in rt:
        print(
            "\nNOTE: Output looks like the rules template. If you expected Llama prose, "
            "confirm ai_available, Modal deploy, and that the first request cold-starts Modal "
            "(can take 1–2 minutes)."
        )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
