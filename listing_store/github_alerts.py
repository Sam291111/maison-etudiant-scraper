"""
Create GitHub issue alerts for listing changes or workflow failures.

This keeps alerts inside GitHub so the free deployment path does not need any
external mail or database service.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data_store"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create GitHub issue alerts for scraper changes or failures.")
    parser.add_argument("--mode", choices=("changes", "failure"), required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def pages_url(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def api_request(method: str, url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "maison-etudiant-scraper",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def create_issue(repo: str, token: str, title: str, body: str) -> None:
    api_request("POST", f"https://api.github.com/repos/{repo}/issues", token, {"title": title, "body": body})


def issue_body_for_changes(repo: str, summary: dict[str, Any], new_rows: list[dict[str, Any]], removed_rows: list[dict[str, Any]]) -> str:
    site_url = pages_url(repo)

    def block(title: str, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return f"### {title}\n\nNone.\n"
        lines = [f"### {title}", ""]
        for row in rows[:25]:
            bits = [row.get("source"), row.get("price_eur"), row.get("postcode")]
            compact = " | ".join(str(bit) for bit in bits if bit not in (None, ""))
            lines.append(f"- [{row.get('title') or 'Untitled'}]({row.get('url')})")
            if compact:
                lines.append(f"  {compact}")
        lines.append("")
        return "\n".join(lines)

    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return "\n".join(
        [
            f"Automated listing alert for `{date_label}`.",
            "",
            f"- Active listings: **{summary.get('active_count', 0)}**",
            f"- New in latest run: **{len(new_rows)}**",
            f"- Removed in latest run: **{len(removed_rows)}**",
            f"- Dashboard: {site_url}",
            f"- JSON feed: {site_url}data/active_listings.json",
            "",
            block("New Listings", new_rows),
            block("Removed Listings", removed_rows),
        ]
    )


def issue_body_for_failure(repo: str) -> str:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server_url}/{repo}/actions/runs/{run_id}" if run_id else ""
    lines = [
        f"Automated refresh failure detected at `{utc_now_iso()}`.",
        "",
        f"- Repository: `{repo}`",
    ]
    if run_url:
        lines.append(f"- Workflow run: {run_url}")
    lines.extend(
        [
            "",
            "Please inspect the failed workflow logs and rerun once fixed.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if not args.repo or not args.token:
        raise SystemExit("Missing GITHUB_REPOSITORY or GITHUB_TOKEN for GitHub alerting.")

    if args.mode == "changes":
        summary = load_json(args.data_dir / "latest_pipeline_summary.json")
        new_rows = load_json(args.data_dir / "new_in_run.json")
        removed_rows = load_json(args.data_dir / "removed_in_run.json")
        if not new_rows and not removed_rows:
            print("No new or removed listings, skipping alert issue.")
            return 0
        title = (
            f"Listing alert: {len(new_rows)} new, {len(removed_rows)} removed "
            f"({datetime.now(timezone.utc).date().isoformat()})"
        )
        body = issue_body_for_changes(args.repo, summary, new_rows, removed_rows)
    else:
        title = f"Refresh workflow failed ({datetime.now(timezone.utc).date().isoformat()})"
        body = issue_body_for_failure(args.repo)

    try:
        create_issue(args.repo, args.token, title, body)
    except HTTPError as exc:
        raise SystemExit(f"GitHub alert issue creation failed: {exc}") from exc

    print(f"Created GitHub issue alert: {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
