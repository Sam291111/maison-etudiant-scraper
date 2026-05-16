"""
End-to-end listing pipeline runner.

What it does:
- runs every source scraper in sequence
- refreshes the cross-source listing store
- writes a log file and machine-readable run status

Run:
  python3 listing_store/run_pipeline.py
"""

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "listing_store" / "outputs"
LOG_DIR = OUTPUT_DIR / "pipeline_logs"
LOCK_PATH = OUTPUT_DIR / "pipeline.lock"
STATUS_PATH = OUTPUT_DIR / "latest_refresh_status.json"

SCRAPER_STEPS = [
    ("immojeune", [sys.executable, str(PROJECT_ROOT / "scrapers" / "immojeune" / "scraper.py")]),
    ("la_carte_des_colocs", [sys.executable, str(PROJECT_ROOT / "scrapers" / "la_carte_des_colocs" / "scraper.py")]),
    ("location_etudiant", [sys.executable, str(PROJECT_ROOT / "scrapers" / "location_etudiant" / "scraper.py")]),
    ("studapart", [sys.executable, str(PROJECT_ROOT / "scrapers" / "studapart" / "scraper.py")]),
    ("listing_store", [sys.executable, str(PROJECT_ROOT / "listing_store" / "update_store.py")]),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def acquire_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise SystemExit("Another refresh is already running.")
    handle.write(f"{utc_now_iso()}\n")
    handle.flush()
    return handle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all scrapers and refresh the combined listing store.")
    parser.add_argument("--triggered-by", default="manual")
    parser.add_argument(
        "--skip-source",
        action="append",
        default=[],
        choices=[name for name, _ in SCRAPER_STEPS if name != "listing_store"],
        help="Skip one or more source scrapers.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock_handle = acquire_lock(LOCK_PATH)

    started_at = utc_now_iso()
    log_path = LOG_DIR / f"refresh_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    steps_payload: list[dict[str, Any]] = []
    status_payload: dict[str, Any] = {
        "started_at": started_at,
        "finished_at": None,
        "triggered_by": args.triggered_by,
        "status": "running",
        "log_path": str(log_path),
        "steps": steps_payload,
    }
    write_status(STATUS_PATH, status_payload)

    selected_steps = []
    skipped = set(args.skip_source)
    for step_name, command in SCRAPER_STEPS:
        if step_name in skipped:
            continue
        selected_steps.append((step_name, command))

    try:
        with log_path.open("w", encoding="utf-8") as log_handle:
            log_handle.write(f"Refresh started at {started_at}\n")
            log_handle.write(f"Triggered by: {args.triggered_by}\n\n")

            for step_name, command in selected_steps:
                step_started = utc_now_iso()
                started_monotonic = time.monotonic()
                step_record = {
                    "name": step_name,
                    "command": command,
                    "started_at": step_started,
                    "finished_at": None,
                    "duration_seconds": None,
                    "returncode": None,
                    "status": "running",
                }
                steps_payload.append(step_record)
                write_status(STATUS_PATH, status_payload)

                log_handle.write(f"== [{step_name}] ==\n")
                log_handle.write(f"Command: {' '.join(command)}\n")
                log_handle.flush()

                completed = subprocess.run(
                    command,
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                )

                duration = round(time.monotonic() - started_monotonic, 2)
                step_record["finished_at"] = utc_now_iso()
                step_record["duration_seconds"] = duration
                step_record["returncode"] = completed.returncode
                step_record["status"] = "succeeded" if completed.returncode == 0 else "failed"

                if completed.stdout:
                    log_handle.write(completed.stdout)
                    if not completed.stdout.endswith("\n"):
                        log_handle.write("\n")
                if completed.stderr:
                    log_handle.write("[stderr]\n")
                    log_handle.write(completed.stderr)
                    if not completed.stderr.endswith("\n"):
                        log_handle.write("\n")
                log_handle.write(f"[exit code] {completed.returncode}\n\n")
                log_handle.flush()
                write_status(STATUS_PATH, status_payload)

                if completed.returncode != 0:
                    status_payload["status"] = "failed"
                    status_payload["finished_at"] = utc_now_iso()
                    write_status(STATUS_PATH, status_payload)
                    return completed.returncode

            status_payload["status"] = "succeeded"
            status_payload["finished_at"] = utc_now_iso()
            write_status(STATUS_PATH, status_payload)
            return 0
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
