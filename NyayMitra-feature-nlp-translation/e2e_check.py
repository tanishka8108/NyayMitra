"""End-to-end check for the three NLP endpoints.

Run while translate_service.py is up on :8001.

    python _e2e.py
"""
import io
import os
import sys
import time

import requests

BASE = os.environ.get("TRANSLATION_API_URL", "http://127.0.0.1:8001")
KEY = "nyaymitra-local-test-2026"
HEADERS = {"Authorization": f"Bearer {KEY}"}
AUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio.wav")

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def wait_for_health(timeout=900):
    """Models load during uvicorn startup, so poll rather than assume."""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE}/health", timeout=10)
            if r.ok:
                record("GET /health", True, r.text)
                return True
            last = f"{r.status_code} {r.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)[:120]
        time.sleep(5)
    record("GET /health", False, f"timed out after {timeout}s; last={last}")
    return False


def check_auth_rejected():
    """The API key gate must actually gate."""
    r = requests.post(
        f"{BASE}/api/translate",
        json={
            "case_id": "C1",
            "source_text": "test",
            "source_lang": "en",
            "target_lang": "hi",
        },
        timeout=30,
    )
    ok = r.status_code == 401
    record("POST /api/translate rejects bad key", ok, f"status={r.status_code}")


def check_en_to_indic():
    r = requests.post(
        f"{BASE}/api/translate",
        headers=HEADERS,
        json={
            "case_id": "CASE-E2E-1",
            "source_text": "The accused has been convicted by the court.",
            "source_lang": "en",
            "target_lang": "hi",
        },
        timeout=300,
    )
    if not r.ok:
        record("POST /api/translate en->hi", False, f"{r.status_code} {r.text[:300]}")
        return
    body = r.json()
    text = body.get("translated_text", "")
    record(
        "POST /api/translate en->hi",
        bool(text),
        f"id={body.get('translation_id')} text={text[:90]!r}",
    )


def check_indic_to_indic():
    r = requests.post(
        f"{BASE}/api/translate/indic-to-indic",
        headers=HEADERS,
        json={
            "case_id": "CASE-E2E-2",
            "source_text": "यह एक परीक्षण वाक्य है।",
            "source_lang": "hi",
            "target_lang": "mr",
        },
        timeout=300,
    )
    if not r.ok:
        record(
            "POST /api/translate/indic-to-indic hi->mr",
            False,
            f"{r.status_code} {r.text[:300]}",
        )
        return
    body = r.json()
    text = body.get("translated_text", "")
    record(
        "POST /api/translate/indic-to-indic hi->mr",
        bool(text),
        f"text={text[:90]!r}",
    )


def check_voice():
    if not os.path.exists(AUDIO):
        record("POST /api/voice", False, f"missing fixture {AUDIO}")
        return
    with open(AUDIO, "rb") as handle:
        blob = handle.read()
    # target_lang is a QUERY param (bare `str = "mr"` annotation), and the
    # multipart field is named `audio`. Sending either wrong is silent: a
    # form-field target_lang is simply ignored and the default "mr" is used.
    r = requests.post(
        f"{BASE}/api/voice",
        headers=HEADERS,
        params={"target_lang": "hi"},
        files={"audio": ("test_audio.wav", blob, "audio/wav")},
        timeout=600,
    )
    if not r.ok:
        record("POST /api/voice", False, f"{r.status_code} {r.text[:300]}")
        return
    body = r.json()
    text = body.get("transcribed_text", "")
    record(
        "POST /api/voice",
        body.get("language") == "hi" and bool(text),
        f"lang={body.get('language')} text={text[:120]!r}",
    )


def check_auth_rejected_voice():
    r = requests.post(
        f"{BASE}/api/voice",
        params={"target_lang": "hi"},
        files={"audio": ("test_audio.wav", b"x" * 64, "audio/wav")},
        timeout=30,
    )
    record("POST /api/voice rejects bad key", r.status_code == 401, f"status={r.status_code}")


def main():
    if not wait_for_health():
        print("\nService never became healthy -- aborting.", flush=True)
        return 1

    check_auth_rejected()
    check_auth_rejected_voice()
    check_en_to_indic()
    check_indic_to_indic()
    check_voice()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{'=' * 60}")
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
