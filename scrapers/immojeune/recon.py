"""
ImmoJeune recon tool
====================

Two modes:
1. Offline HTML recon against saved pages.
2. Live browser/network recon with Playwright.

Examples:
  python3 scrapers/immojeune/recon.py --offline-html scrapers/immojeune/raw_html/lyon_colocation.html
  python3 scrapers/immojeune/recon.py --live

Live mode needs:
  pip install playwright beautifulsoup4
  playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = None
    sync_playwright = None


DEFAULT_URL = "https://www.immojeune.com/colocation/lyon-69.html"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = BASE_DIR / "outputs" / "recon_output"
FOCUS_PATTERNS = (
    "immojeune.com",
    "/advert/searchadvance",
    "advert_searchquery_ajaxresults",
    "/candidate/",
)


@dataclass
class RequestRecord:
    scenario: str
    method: str
    url: str
    path: str
    resource_type: str
    post_data: str | None
    post_data_form: dict[str, str] | None
    timestamp: str


@dataclass
class ResponseRecord:
    scenario: str
    method: str
    url: str
    path: str
    status: int
    resource_type: str
    content_type: str | None
    body_excerpt: str | None
    timestamp: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "run"


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def decode_form_payload(post_data: str | None) -> dict[str, str] | None:
    if not post_data:
        return None
    if "=" not in post_data:
        return None
    pairs = parse_qsl(post_data, keep_blank_values=True)
    if not pairs:
        return None
    result: dict[str, str] = {}
    for key, value in pairs:
        if key in result:
            result[key] = f"{result[key]} | {value}"
        else:
            result[key] = value
    return result


def looks_interesting(url: str, resource_type: str, method: str) -> bool:
    return (
        method != "GET"
        or resource_type in {"xhr", "fetch", "document"}
        or any(pattern in url for pattern in FOCUS_PATTERNS)
    )


def html_card_summary(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("#resultsajax .card.col")
    badge_counter: Counter[str] = Counter()
    postcode_counter: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []

    for card in cards:
        badges = [compact_whitespace(node.get_text(" ", strip=True)) for node in card.select(".badge")]
        for badge in badges:
            badge_counter[badge] += 1

        title_node = card.select_one("p.title a, p.title span.obflink")
        title = compact_whitespace(title_node.get_text(" ", strip=True)) if title_node else ""

        geo_node = card.select_one(".geo")
        geo_text = compact_whitespace(geo_node.get_text(" ", strip=True).replace("Ville", "")) if geo_node else ""
        postcode_match = re.search(r"\b(69\d{3})\b", geo_text)
        if postcode_match:
            postcode_counter[postcode_match.group(1)] += 1

        desc_node = card.select_one("p.description")
        desc = compact_whitespace(desc_node.get_text(" ", strip=True)) if desc_node else ""
        student_friendly = bool(
            re.search(r"student|étudiant|jeunes actifs|young professionals|jeunes travailleurs", desc, re.I)
        )

        if len(samples) < 8:
            samples.append(
                {
                    "title": title,
                    "badges": badges,
                    "location": geo_text,
                    "student_friendly_cue": student_friendly,
                }
            )

    return {
        "card_count": len(cards),
        "badge_counts": dict(sorted(badge_counter.items())),
        "postcode_counts": dict(sorted(postcode_counter.items())),
        "sample_cards": samples,
    }


def extract_forms_and_js_hints(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    forms: list[dict[str, Any]] = []

    for form in soup.find_all("form"):
        controls = []
        for tag in form.find_all(["input", "select", "textarea"]):
            name = tag.get("name")
            if not name:
                continue
            controls.append(
                {
                    "name": name,
                    "type": tag.get("type", tag.name),
                    "value": tag.get("value"),
                }
            )
        forms.append(
            {
                "name": form.get("name"),
                "method": form.get("method", "get").upper(),
                "action": form.get("action"),
                "controls": controls[:25],
                "control_count": len(controls),
            }
        )

    js_hints = {
        "ajax_routes": sorted(set(re.findall(r"Routing\.generate\('([^']+)'\)", html))),
        "searchadvance_present": "/advert/searchadvance" in html,
        "encoded_links_present": "data-encoded-link" in html,
        "property_types": sorted(set(re.findall(r'name="advert_search_advance\[propertyType\]\[\]" value="([^"]+)"', html))),
        "candidate_statuses": sorted(set(re.findall(r'<option value="([^"]+)">[^<]+</option>', html))),
    }

    return {"forms": forms, "js_hints": js_hints}


def summarize_requests(requests: list[RequestRecord], responses: list[ResponseRecord]) -> dict[str, Any]:
    by_path: dict[str, dict[str, Any]] = {}
    response_map: dict[tuple[str, str], list[ResponseRecord]] = defaultdict(list)
    for response in responses:
        response_map[(response.method, response.url)].append(response)

    for request in requests:
        key = request.path or request.url
        bucket = by_path.setdefault(
            key,
            {
                "count": 0,
                "methods": Counter(),
                "resource_types": Counter(),
                "scenarios": Counter(),
                "sample_urls": [],
                "sample_payloads": [],
                "statuses": Counter(),
                "content_types": Counter(),
            },
        )
        bucket["count"] += 1
        bucket["methods"][request.method] += 1
        bucket["resource_types"][request.resource_type] += 1
        bucket["scenarios"][request.scenario] += 1
        if request.url not in bucket["sample_urls"] and len(bucket["sample_urls"]) < 3:
            bucket["sample_urls"].append(request.url)
        if request.post_data_form and len(bucket["sample_payloads"]) < 3:
            bucket["sample_payloads"].append(request.post_data_form)
        elif request.post_data and len(bucket["sample_payloads"]) < 3:
            bucket["sample_payloads"].append({"raw": request.post_data[:300]})

        for response in response_map.get((request.method, request.url), []):
            bucket["statuses"][str(response.status)] += 1
            if response.content_type:
                bucket["content_types"][response.content_type] += 1

    summary_rows = []
    for path, data in by_path.items():
        summary_rows.append(
            {
                "path": path,
                "count": data["count"],
                "methods": dict(data["methods"]),
                "resource_types": dict(data["resource_types"]),
                "scenarios": dict(data["scenarios"]),
                "sample_urls": data["sample_urls"],
                "sample_payloads": data["sample_payloads"],
                "statuses": dict(data["statuses"]),
                "content_types": dict(data["content_types"]),
            }
        )

    summary_rows.sort(key=lambda row: (-row["count"], row["path"]))
    return {"request_groups": summary_rows}


class NetworkRecorder:
    def __init__(self) -> None:
        self.current_scenario = "startup"
        self.requests: list[RequestRecord] = []
        self.responses: list[ResponseRecord] = []

    def set_scenario(self, name: str) -> None:
        self.current_scenario = name

    def attach(self, page: Any) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _on_request(self, request: Any) -> None:
        url = request.url
        if not looks_interesting(url, request.resource_type, request.method):
            return
        parsed = urlparse(url)
        post_data = request.post_data
        self.requests.append(
            RequestRecord(
                scenario=self.current_scenario,
                method=request.method,
                url=url,
                path=parsed.path,
                resource_type=request.resource_type,
                post_data=post_data[:1500] if post_data else None,
                post_data_form=decode_form_payload(post_data[:4000] if post_data else None),
                timestamp=utc_now_iso(),
            )
        )

    def _on_response(self, response: Any) -> None:
        request = response.request
        if not looks_interesting(response.url, request.resource_type, request.method):
            return
        body_excerpt = None
        content_type = response.headers.get("content-type")
        if any(token in response.url for token in ("/advert/", "/candidate/")):
            try:
                text = response.text()
                body_excerpt = compact_whitespace(text)[:1000]
            except Exception:
                body_excerpt = None
        self.responses.append(
            ResponseRecord(
                scenario=self.current_scenario,
                method=request.method,
                url=response.url,
                path=urlparse(response.url).path,
                status=response.status,
                resource_type=request.resource_type,
                content_type=content_type,
                body_excerpt=body_excerpt,
                timestamp=utc_now_iso(),
            )
        )


def run_offline(html_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    pages = []
    for html_path in html_paths:
        html = html_path.read_text(encoding="utf-8")
        pages.append(
            {
                "file": str(html_path),
                "forms_and_js": extract_forms_and_js_hints(html),
                "card_summary": html_card_summary(html),
            }
        )

    report = {
        "mode": "offline",
        "generated_at": utc_now_iso(),
        "pages": pages,
    }
    write_report_bundle(report, output_dir)
    return report


def ensure_playwright_available() -> None:
    if sync_playwright is None:
        raise SystemExit(
            "Playwright is not installed.\n"
            "Install with:\n"
            "  pip install playwright beautifulsoup4\n"
            "  playwright install chromium"
        )


def save_html_snapshot(page: Any, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    html = page.content()
    (output_dir / f"{name}.html").write_text(html, encoding="utf-8")


def apply_room_filter(page: Any) -> None:
    page.evaluate(
        """
        () => {
            const room = document.querySelector('#advert_search_advance_propertyType_0');
            const furnished = document.querySelector('#advert_search_advance_furnished');
            if (room) room.checked = true;
            if (furnished) furnished.checked = true;
            const form = document.querySelector('form[name="advert_search_advance"]');
            if (form) form.submit();
        }
        """
    )


def scroll_for_more_results(page: Any, max_scrolls: int, pause_seconds: float) -> None:
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(pause_seconds)


def run_live(start_url: str, output_dir: Path, max_scrolls: int, pause_seconds: float) -> dict[str, Any]:
    ensure_playwright_available()
    recorder = NetworkRecorder()
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            locale="fr-FR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        recorder.attach(page)

        recorder.set_scenario("initial_load")
        page.goto(start_url, wait_until="networkidle", timeout=45000)
        save_html_snapshot(page, output_dir, "01_initial_load")

        recorder.set_scenario("scroll_after_initial_load")
        scroll_for_more_results(page, max_scrolls=max_scrolls, pause_seconds=pause_seconds)
        save_html_snapshot(page, output_dir, "02_after_scroll")

        recorder.set_scenario("apply_room_and_furnished_filters")
        apply_room_filter(page)
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(pause_seconds)
        save_html_snapshot(page, output_dir, "03_after_filter_submit")

        recorder.set_scenario("scroll_after_filter_submit")
        scroll_for_more_results(page, max_scrolls=max_scrolls, pause_seconds=pause_seconds)
        save_html_snapshot(page, output_dir, "04_after_filtered_scroll")

        final_html = page.content()
        final_url = page.url
        context.close()
        browser.close()

    report = {
        "mode": "live",
        "generated_at": utc_now_iso(),
        "start_url": start_url,
        "final_url": final_url,
        "card_summary_final_page": html_card_summary(final_html),
        "forms_and_js_final_page": extract_forms_and_js_hints(final_html),
        "network": {
            "request_count": len(recorder.requests),
            "response_count": len(recorder.responses),
            "requests": [asdict(item) for item in recorder.requests],
            "responses": [asdict(item) for item in recorder.responses],
            "summary": summarize_requests(recorder.requests, recorder.responses),
        },
    }
    write_report_bundle(report, output_dir)
    return report


def render_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# ImmoJeune recon summary",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Generated at: `{report['generated_at']}`",
    ]

    if report["mode"] == "offline":
        lines.append(f"- Pages analysed: `{len(report['pages'])}`")
        lines.append("")
        for page in report["pages"]:
            card_summary = page["card_summary"]
            lines.append(f"## {Path(page['file']).name}")
            lines.append(f"- Cards found: `{card_summary['card_count']}`")
            lines.append(f"- Badge counts: `{json.dumps(card_summary['badge_counts'], ensure_ascii=False)}`")
            lines.append(f"- Postcodes: `{json.dumps(card_summary['postcode_counts'], ensure_ascii=False)}`")
            js_hints = page["forms_and_js"]["js_hints"]
            lines.append(f"- AJAX routes: `{', '.join(js_hints['ajax_routes']) or 'none'}`")
            lines.append(f"- Property types: `{', '.join(js_hints['property_types']) or 'none'}`")
            lines.append("")
    else:
        network_summary = report["network"]["summary"]["request_groups"][:10]
        lines.append(f"- Start URL: `{report['start_url']}`")
        lines.append(f"- Final URL: `{report['final_url']}`")
        lines.append(f"- Requests captured: `{report['network']['request_count']}`")
        lines.append(f"- Responses captured: `{report['network']['response_count']}`")
        lines.append("")
        lines.append("## Top request groups")
        for group in network_summary:
            lines.append(f"- `{group['path']}` x `{group['count']}`")
            if group["sample_payloads"]:
                lines.append(f"  payload sample: `{json.dumps(group['sample_payloads'][0], ensure_ascii=False)[:220]}`")
        lines.append("")
        lines.append("## Final page card mix")
        lines.append(
            f"- Badge counts: `{json.dumps(report['card_summary_final_page']['badge_counts'], ensure_ascii=False)}`"
        )
        lines.append(
            f"- Postcodes: `{json.dumps(report['card_summary_final_page']['postcode_counts'], ensure_ascii=False)}`"
        )

    return "\n".join(lines) + "\n"


def write_report_bundle(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(render_markdown_summary(report), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recon ImmoJeune pages and network activity before rebuilding the scraper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              python3 scrapers/immojeune/recon.py --offline-html scrapers/immojeune/raw_html/lyon_colocation.html
              python3 scrapers/immojeune/recon.py --live
            """
        ),
    )
    parser.add_argument("--live", action="store_true", help="Run live browser/network recon with Playwright.")
    parser.add_argument(
        "--offline-html",
        nargs="+",
        type=Path,
        help="Analyse saved HTML files without a browser.",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Live mode start URL.")
    parser.add_argument("--max-scrolls", type=int, default=2, help="How many scroll attempts to trigger lazy loads.")
    parser.add_argument("--pause-seconds", type=float, default=2.0, help="Pause after actions in live mode.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output directory. Default is recon_output/<timestamp>.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp_dir = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / timestamp_dir)

    if args.live:
        report = run_live(
            start_url=args.url,
            output_dir=output_dir,
            max_scrolls=args.max_scrolls,
            pause_seconds=args.pause_seconds,
        )
    elif args.offline_html:
        report = run_offline(html_paths=args.offline_html, output_dir=output_dir)
    else:
        raise SystemExit("Choose either --live or --offline-html.")

    print(f"Saved recon output to: {output_dir}")
    print((output_dir / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
