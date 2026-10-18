#!/usr/bin/env python3
"""Smoke checks for the My Cases endpoints (stdlib only)."""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

KNOWN_CNR = "MHPU210000042026"
UNKNOWN_CNR = "MHPU999999992026"

failures = []


def call(path):
    request = urllib.request.Request(f"{BASE}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body


def check(name, condition, detail=""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        failures.append(name)


def payload(body):
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


print("== My Cases smoke checks ==")

status, body = call("/")
check("root 200", status == 200, f"got {status}")

status, body = call(f"/api/cases/cnr/{KNOWN_CNR}")
data = payload(body)
check("known CNR -> 200", status == 200, f"got {status}: {body[:200]}")
check("known CNR -> success flag", bool(data and data.get("success")))
case = (data or {}).get("case") or {}
check("case has parties", bool(case.get("petitioner_name")), str(case)[:200])
check("case has court", bool(case.get("court_name")))
check("case has timeline", isinstance(case.get("case_history_timeline"), list))
check("case has orders key", isinstance(case.get("orders"), list))
check("case has metrics", "calculated_metrics" in case, str(case.get("calculated_metrics")))
check("case has status", bool(case.get("case_status")))
check("data_source disclosed", (data or {}).get("data_source", {}).get("provider") == "development")
check(
    "not claimed as live data",
    (data or {}).get("data_source", {}).get("live_ecourts_data") is False,
)
check("no stack trace", "Traceback" not in body)

status, body = call("/api/cases/cnr/not-a-cnr")
check("malformed CNR -> 400", status == 400, f"got {status}")
check("malformed CNR message safe", "Invalid CNR" in body, body[:200])
check("malformed: no stack trace", "Traceback" not in body and "File \"" not in body)

status, body = call(f"/api/cases/cnr/{UNKNOWN_CNR}")
check("unknown CNR -> 404", status == 404, f"got {status}")
check("unknown CNR message safe", "No case with CNR" in body, body[:200])
check("unknown: no stack trace", "Traceback" not in body)

status, body = call("/api/cases?limit=3")
data = payload(body)
check("list -> 200", status == 200, f"got {status}: {body[:200]}")
check("list has items", len((data or {}).get("items", [])) == 3, body[:200])
check("list has total", (data or {}).get("total", 0) >= 100, str((data or {}).get("total")))
check("list metrics computed", "calculated_metrics" in ((data or {}).get("items") or [{}])[0])

status, body = call("/api/cases?status=pending")
data = payload(body)
pending = (data or {}).get("total", 0)
check("pending filter", 0 < pending < 109, f"total={pending}")

status, body = call("/api/cases?q=MHPU210000042026")
data = payload(body)
check("search by CNR", (data or {}).get("total") == 1, str((data or {}).get("total")))

status, body = call("/api/cases/meta")
data = payload(body)
check("meta -> 200", status == 200, f"got {status}")
check("meta records", (data or {}).get("data_source", {}).get("records") == 109, body[:200])

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)

print("all smoke checks passed")
