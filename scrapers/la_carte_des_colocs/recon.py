"""
La Carte des Colocs recon tool
==============================

This source appears to be protected by Cloudflare, so this recon tool is
browser-first and explicitly reports when a challenge blocks access.

Examples:
  python3 scrapers/la_carte_des_colocs/recon.py --live
  python3 scrapers/la_carte_des_colocs/recon.py --offline-html scrapers/la_carte_des_colocs/raw_html/lyon.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
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


BASE_DIR = Path(__file__).resolve().parent
RAW_HTML_DIR = BASE_DIR / "raw_html"
OUTPUT_ROOT = BASE_DIR / "outputs" / "recon_output"
DEFAULT_URL = "https://www.lacartedescolocs.fr/logements/fr/auvergne-rhone-alpes/lyon"
FOCUS_PATTERNS = (
    "lacartedescolocs.fr",
    "cdn-cgi/challenge-platform",
    "__cf_chl",
    "api",
    "graphql",
    "logement",
    "annonce",
    "coloc",
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


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def decode_form_payload(post_data: str | None) -> dict[str, str] | None:
    if not post_data or "=" not in post_data:
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
        or resource_type in {"xhr", "fetch", "document", "script"}
        or any(pattern in url for pattern in FOCUS_PATTERNS)
    )


def detect_cloudflare_block(html: str, title: str) -> dict[str, Any]:
    html_lower = html.lower()
    title_lower = title.lower()
    return {
        "blocked": (
            "just a moment" in title_lower
            or "cdn-cgi/challenge-platform" in html_lower
            or "window._cf_chl_opt" in html
            or "enable javascript and cookies to continue" in html_lower
        ),
        "signals": [
            signal
            for signal, present in [
                ("title_just_a_moment", "just a moment" in title_lower),
                ("challenge_platform_script", "cdn-cgi/challenge-platform" in html_lower),
                ("cf_chl_opt", "window._cf_chl_opt" in html),
                ("enable_js_and_cookies", "enable javascript and cookies to continue" in html_lower),
            ]
            if present
        ],
    }


def summarize_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = compact(soup.title.get_text(" ", strip=True)) if soup.title else ""
    block_info = detect_cloudflare_block(html, title)
    js_hints = sorted(
        set(
            re.findall(
                r"(?:/api/[A-Za-z0-9_\-/?=&%.]+|graphql|apollo|__NEXT_DATA__|nuxt|pageProps|logement|annonce|coloc)",
                html,
                flags=re.I,
            )
        )
    )

    return {
        "title": title,
        "cloudflare": block_info,
        "link_count": len(soup.find_all("a")),
        "script_count": len(soup.find_all("script")),
        "forms_count": len(soup.find_all("form")),
        "candidate_article_count": len(soup.select("article, [class*=listing], [class*=card], [class*=annonce]")),
        "js_hints": js_hints[:100],
    }


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
        if request.post_data_form and len(bucket["sample_payloads"]) < 2:
            bucket["sample_payloads"].append(request.post_data_form)
        elif request.post_data and len(bucket["sample_payloads"]) < 2:
            bucket["sample_payloads"].append({"raw": request.post_data[:300]})
        for response in response_map.get((request.method, request.url), []):
            bucket["statuses"][str(response.status)] += 1
            if response.content_type:
                bucket["content_types"][response.content_type] += 1

    rows = []
    for path, data in by_path.items():
        rows.append(
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
    rows.sort(key=lambda row: (-row["count"], row["path"]))
    return {"request_groups": rows}


def extract_listing_search_insight(requests: list[RequestRecord], responses: list[ResponseRecord]) -> dict[str, Any] | None:
    target_path = "/listing_search/list_results"
    request = next((item for item in requests if item.path == target_path), None)
    response = next((item for item in responses if item.path == target_path and item.body_excerpt), None)
    if not request and not response:
        return None

    insight: dict[str, Any] = {"path": target_path}
    if request:
        insight["request_method"] = request.method
        insight["request_url"] = request.url
        try:
            insight["request_json"] = json.loads(request.post_data) if request.post_data else None
        except Exception:
            insight["request_json"] = {"raw": request.post_data}

    if response:
        insight["response_status"] = response.status
        insight["response_content_type"] = response.content_type
        excerpt = response.body_excerpt or ""
        try:
            payload = json.loads(excerpt) if excerpt else {}
            results_raw = payload.get("results")
            sample_listing = None
            if isinstance(results_raw, str) and results_raw.startswith("["):
                parsed_results = json.loads(results_raw)
                if parsed_results:
                    sample_listing = parsed_results[0]
            insight["response_json"] = {
                "results_count": payload.get("results_count"),
                "batch_size": payload.get("batch_size"),
                "sample_listing": sample_listing,
            }
        except Exception:
            results_count_match = re.search(r'"results_count":(\d+)', excerpt)
            batch_size_match = re.search(r'"batch_size":(\d+)', excerpt)
            sample_match = re.search(r'"results":"\[(\{.+?\})', excerpt)
            sample_listing = None
            if sample_match:
                sample_blob = sample_match.group(1).replace('\\"', '"')
                try:
                    sample_listing = json.loads(sample_blob)
                except Exception:
                    sample_listing = None
            insight["response_json"] = {
                "results_count": int(results_count_match.group(1)) if results_count_match else None,
                "batch_size": int(batch_size_match.group(1)) if batch_size_match else None,
                "sample_listing": sample_listing,
                "raw_excerpt": excerpt[:1000],
            }

    return insight


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
        if not looks_interesting(request.url, request.resource_type, request.method):
            return
        post_data = request.post_data
        self.requests.append(
            RequestRecord(
                scenario=self.current_scenario,
                method=request.method,
                url=request.url,
                path=urlparse(request.url).path,
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
        excerpt = None
        content_type = response.headers.get("content-type")
        if any(token in response.url for token in ("cdn-cgi", "api", "graphql", "logement", "annonce", "coloc", "listing_search")):
            try:
                text = compact(response.text())
                if response.url.endswith("/listing_search/list_results"):
                    excerpt = text[:40000]
                else:
                    excerpt = text[:1000]
            except Exception:
                excerpt = None
        self.responses.append(
            ResponseRecord(
                scenario=self.current_scenario,
                method=request.method,
                url=response.url,
                path=urlparse(response.url).path,
                status=response.status,
                resource_type=request.resource_type,
                content_type=content_type,
                body_excerpt=excerpt,
                timestamp=utc_now_iso(),
            )
        )


def ensure_playwright_available() -> None:
    if sync_playwright is None:
        raise SystemExit(
            "Playwright is not installed.\n"
            "Install with:\n"
            "  pip install playwright beautifulsoup4\n"
            "  playwright install chromium"
        )


def write_report_bundle(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "summary.md").write_text(render_markdown_summary(report), encoding="utf-8")


def render_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# La Carte des Colocs recon summary",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Generated at: `{report['generated_at']}`",
    ]

    if report["mode"] == "offline":
        page = report["page"]
        lines.extend(
            [
                f"- HTML file: `{page['file']}`",
                f"- Title: `{page['summary']['title']}`",
                f"- Cloudflare blocked: `{page['summary']['cloudflare']['blocked']}`",
                f"- Cloudflare signals: `{', '.join(page['summary']['cloudflare']['signals']) or 'none'}`",
                f"- Candidate listing nodes: `{page['summary']['candidate_article_count']}`",
                f"- JS hints found: `{len(page['summary']['js_hints'])}`",
            ]
        )
    else:
        lines.extend(
            [
                f"- Start URL: `{report['start_url']}`",
                f"- Final URL: `{report['final_url']}`",
                f"- Page title: `{report['page_summary']['title']}`",
                f"- Cloudflare blocked: `{report['page_summary']['cloudflare']['blocked']}`",
                f"- Cloudflare signals: `{', '.join(report['page_summary']['cloudflare']['signals']) or 'none'}`",
                f"- Requests captured: `{report['network']['request_count']}`",
                f"- Responses captured: `{report['network']['response_count']}`",
            ]
        )
        listing_search = report.get("listing_search")
        if listing_search:
            lines.extend(
                [
                    f"- Listing endpoint found: `{listing_search['path']}`",
                    f"- Listing results count: `{listing_search.get('response_json', {}).get('results_count')}`",
                    f"- Listing batch size: `{listing_search.get('response_json', {}).get('batch_size')}`",
                ]
            )
        lines.extend(
            [
                "",
                "## Top request groups",
            ]
        )
        for group in report["network"]["summary"]["request_groups"][:10]:
            lines.append(f"- `{group['path']}` x `{group['count']}`")
        if listing_search and listing_search.get("response_json", {}).get("sample_listing"):
            sample = listing_search["response_json"]["sample_listing"]
            lines.extend(
                [
                    "",
                    "## Sample listing",
                    f"- `id`: `{sample.get('id')}`",
                    f"- `relative_url`: `{sample.get('relative_url')}`",
                    f"- `main_title`: `{sample.get('main_title')}`",
                    f"- `address_city`: `{sample.get('address_city')}`",
                    f"- `rent_html`: `{sample.get('rent_html')}`",
                    f"- `housemates`: `{sample.get('housemates')}`",
                    f"- `listing_type`: `{sample.get('listing_type')}`",
                    f"- `lodging_type`: `{sample.get('lodging_type')}`",
                ]
            )
    return "\n".join(lines) + "\n"


def run_offline(html_path: Path, output_dir: Path) -> dict[str, Any]:
    html = html_path.read_text(encoding="utf-8")
    report = {
        "mode": "offline",
        "generated_at": utc_now_iso(),
        "page": {
            "file": str(html_path),
            "summary": summarize_html(html),
        },
    }
    write_report_bundle(report, output_dir)
    return report


def run_live(start_url: str, output_dir: Path, wait_ms: int) -> dict[str, Any]:
    ensure_playwright_available()
    output_dir.mkdir(parents=True, exist_ok=True)
    recorder = NetworkRecorder()

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
        page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)

        html = page.content()
        title = page.title()
        (RAW_HTML_DIR / "live_lyon_latest.html").write_text(html, encoding="utf-8")
        (output_dir / "page.html").write_text(html, encoding="utf-8")

        page_summary = summarize_html(html)
        page_summary["title"] = title

        context.close()
        browser.close()

    report = {
        "mode": "live",
        "generated_at": utc_now_iso(),
        "start_url": start_url,
        "final_url": start_url,
        "page_summary": page_summary,
        "listing_search": extract_listing_search_insight(recorder.requests, recorder.responses),
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recon La Carte des Colocs pages and report access blockers or page/API patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              python3 scrapers/la_carte_des_colocs/recon.py --live
              python3 scrapers/la_carte_des_colocs/recon.py --offline-html scrapers/la_carte_des_colocs/raw_html/lyon.html
            """
        ),
    )
    parser.add_argument("--live", action="store_true", help="Run a live browser session with Playwright.")
    parser.add_argument("--offline-html", type=Path, help="Analyse a saved HTML file.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Start URL for live mode.")
    parser.add_argument("--wait-ms", type=int, default=8000, help="How long to wait after page load in live mode.")
    parser.add_argument("--output-dir", type=Path, help="Optional output directory override.")
    return parser.parse_args()


def main() -> int:
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    args = parse_args()
    timestamp_dir = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (OUTPUT_ROOT / timestamp_dir)

    if args.live:
        report = run_live(start_url=args.url, output_dir=output_dir, wait_ms=args.wait_ms)
    elif args.offline_html:
        report = run_offline(html_path=args.offline_html, output_dir=output_dir)
    else:
        raise SystemExit("Choose either --live or --offline-html.")

    print(f"Saved recon output to: {output_dir}")
    print((output_dir / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
