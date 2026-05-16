"""
Publish tracked data files into the static GitHub Pages site.

What it does:
- copies the latest combined JSON/CSV/XLSX files into `docs/`
- writes a small metadata file for the static dashboard

Run:
  python3 listing_store/publish_pages.py --input-dir data_store --output-dir docs
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data_store"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing input file: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish combined listing outputs into the static Pages site.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    data_dir = output_dir / "data"
    download_dir = output_dir / "downloads"

    active_json = input_dir / "active_listings.json"
    active_csv = input_dir / "active_listings.csv"
    summary_json = input_dir / "latest_pipeline_summary.json"
    workbook = input_dir / "lyon_master_listings.xlsx"
    new_json = input_dir / "new_in_run.json"
    updated_json = input_dir / "updated_in_run.json"
    removed_json = input_dir / "removed_in_run.json"

    copy_file(active_json, data_dir / "active_listings.json")
    copy_file(summary_json, data_dir / "latest_pipeline_summary.json")
    copy_file(new_json, data_dir / "new_in_run.json")
    copy_file(updated_json, data_dir / "updated_in_run.json")
    copy_file(removed_json, data_dir / "removed_in_run.json")
    copy_file(active_csv, download_dir / "active_listings.csv")
    copy_file(workbook, download_dir / "lyon_master_listings.xlsx")

    active_payload = json.loads(active_json.read_text(encoding="utf-8"))
    summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
    new_payload = json.loads(new_json.read_text(encoding="utf-8"))
    updated_payload = json.loads(updated_json.read_text(encoding="utf-8"))
    removed_payload = json.loads(removed_json.read_text(encoding="utf-8"))

    source_counts: dict[str, int] = {}
    for row in active_payload:
        source = str(row.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1

    metadata: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "active_count": len(active_payload),
        "new_count": len(new_payload),
        "updated_count": len(updated_payload),
        "removed_count": len(removed_payload),
        "source_counts": source_counts,
        "summary": summary_payload,
    }
    (data_dir / "site_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Published static site data to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
