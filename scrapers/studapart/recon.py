"""
Studapart Lyon recon
====================

This source uses a public search page shell plus a client-side search API.
The recon focuses on:
- extracting the embedded Lyon search configuration from HTML
- capturing the live search-api requests when the page loads
- summarizing whether the source looks viable for a shared-housing scraper

Examples:
  python3 scrapers/studapart/recon.py --offline-html scrapers/studapart/raw_html/logement_etudiant_lyon.html
  python3 scrapers/studapart/recon.py --live
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
from urllib.request import Request, urlopen

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
DEFAULT_URL = "https://www.studapart.com/fr/logement-etudiant-lyon"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
INTERESTING_PATTERNS = (
    "search-api.studapart.com/property",
    "search-api.studapart.com/open_search",
    "portal_propertysearch",
    "propertysearch",
    "autocomplete",
)


@dataclass
class RequestRecord:
    method: str
    url: str
    resource_type: str
    post_data: str | None
    timestamp: str


@dataclass
class ResponseRecord:
    method: str
    url: str
    status: int
    resource_type: str
    content_type: str | None
    body_excerpt: str | None
    timestamp: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def decode_html_bytes(payload: bytes) -> str:
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def read_html(path: Path) -> str:
    return decode_html_bytes(path.read_bytes())


def fetch_html(url: str) -> str:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=30) as response:
        return decode_html_bytes(response.read())


def parse_json_assignment(html: str, variable_name: str) -> Any | None:
    patterns = [
        rf"{re.escape(variable_name)}\s*=\s*(\{{.*?\}});",
        rf"{re.escape(variable_name)}\s*=\s*(\[.*?\]);",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.S)
        if not match:
            continue
        raw = match.group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def parse_string_assignment(html: str, variable_name: str) -> str | None:
    match = re.search(rf"{re.escape(variable_name)}\s*=\s*'([^']*)'", html)
    if match:
        return match.group(1)
    return None


def extract_meta_property(soup: BeautifulSoup, name: str) -> str | None:
    node = soup.find("meta", attrs={"property": name})
    if node and node.get("content") is not None:
        return str(node["content"])
    return None


def summarize_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = compact(soup.title.get_text(" ", strip=True)) if soup.title else ""
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = compact(str(meta_desc["content"]))

    filters_data = parse_json_assignment(html, "filtersData") or {}
    vars_data = parse_json_assignment(html, "window.vars") or {}
    page_config = {
        "locale": parse_string_assignment(html, "window.locale"),
        "elastic_property_url": parse_string_assignment(html, "window.elasticPropertyUrl"),
        "elastic_suggestion_url": parse_string_assignment(html, "window.elasticPropertySuggestionUrl"),
        "elastic_open_search_url": parse_string_assignment(html, "window.elasticOpenSearchUrl"),
        "elastic_open_search_index": parse_string_assignment(html, "window.elasticSearchOpenSearchIndex"),
        "open_search_id": parse_string_assignment(html, "window.openSearchId"),
    }

    meta_numbers: dict[str, int | None] = {}
    for key, meta_name in {
        "count": "meta:os-count",
        "min_price": "meta:os-min",
        "max_price": "meta:os-max",
        "surface_min": "meta:os-propertySurfaceMin",
        "surface_max": "meta:os-propertySurfaceMax",
    }.items():
        value = extract_meta_property(soup, meta_name)
        meta_numbers[key] = int(value) if value and value.isdigit() else None

    enabled_types = [
        key
        for key in ("rental", "flatShare", "coliving", "homestay", "service")
        if filters_data.get(key) is True
    ]
    disabled_types = [
        key
        for key in ("rental", "flatShare", "coliving", "homestay", "service")
        if filters_data.get(key) is False
    ]

    search_choice = filters_data.get("searchChoice") or []
    postcode_groups = search_choice[0] if search_choice and isinstance(search_choice[0], list) else []

    return {
        "title": title,
        "description": description,
        "link_count": len(soup.find_all("a")),
        "script_count": len(soup.find_all("script")),
        "meta": {
            "city": extract_meta_property(soup, "meta:os-city"),
            "zip_code": extract_meta_property(soup, "meta:os-zipCode"),
            **meta_numbers,
        },
        "vars": vars_data,
        "page_config": page_config,
        "filters": filters_data,
        "enabled_listing_types": enabled_types,
        "disabled_listing_types": disabled_types,
        "postcode_groups": postcode_groups,
    }


def looks_interesting(url: str, resource_type: str | None = None) -> bool:
    if any(pattern in url for pattern in INTERESTING_PATTERNS):
        return True
    return bool(resource_type in {"xhr", "fetch", "document", "script"} and "studapart.com" in url)


def summarize_network(requests: list[RequestRecord], responses: list[ResponseRecord]) -> dict[str, Any]:
    response_map: dict[tuple[str, str], list[ResponseRecord]] = defaultdict(list)
    for response in responses:
        response_map[(response.method, response.url)].append(response)

    grouped: dict[str, dict[str, Any]] = {}
    for request in requests:
        key = request.url
        bucket = grouped.setdefault(
            key,
            {
                "method": request.method,
                "resource_type": request.resource_type,
                "count": 0,
                "sample_post_data": None,
                "statuses": Counter(),
                "content_types": Counter(),
            },
        )
        bucket["count"] += 1
        if request.post_data and bucket["sample_post_data"] is None:
            bucket["sample_post_data"] = request.post_data[:2000]
        for response in response_map.get((request.method, request.url), []):
            bucket["statuses"][str(response.status)] += 1
            if response.content_type:
                bucket["content_types"][response.content_type] += 1

    rows = []
    for url, data in grouped.items():
        rows.append(
            {
                "url": url,
                "method": data["method"],
                "resource_type": data["resource_type"],
                "count": data["count"],
                "sample_post_data": data["sample_post_data"],
                "statuses": dict(data["statuses"]),
                "content_types": dict(data["content_types"]),
            }
        )
    def priority(url: str) -> tuple[int, str]:
        if "search-api.studapart.com/property" in url:
            return (0, url)
        if "search-api.studapart.com/open_search" in url:
            return (1, url)
        if "portal_propertysearch" in url or "autocomplete" in url:
            return (2, url)
        return (3, url)

    rows.sort(key=lambda item: (priority(item["url"])[0], -item["count"], priority(item["url"])[1]))
    return {"requests": rows}


def summarize_search_api_response(responses: list[ResponseRecord]) -> dict[str, Any] | None:
    target = next((item for item in responses if "search-api.studapart.com/property" in item.url and item.body_excerpt), None)
    if target is None:
        return None

    insight: dict[str, Any] = {
        "url": target.url,
        "status": target.status,
        "content_type": target.content_type,
    }
    try:
        payload = json.loads(target.body_excerpt)
    except Exception:
        insight["raw_excerpt"] = target.body_excerpt[:2000]
        return insight

    results = payload.get("results") or []
    first = results[0] if results else None
    sample = None
    if isinstance(first, dict):
        sample = {key: first.get(key) for key in list(first.keys())[:20]}

    insight["response_summary"] = {
        "nb_hits": payload.get("nbHits"),
        "is_last_page": payload.get("isLastPage"),
        "result_count_in_payload": len(results) if isinstance(results, list) else None,
        "price_data": payload.get("priceData"),
        "property_surface_data": payload.get("propertySurfaceData"),
        "sample_listing_keys": sorted(first.keys())[:40] if isinstance(first, dict) else [],
        "sample_listing": sample,
    }
    return insight


def capture_live(url: str, wait_ms: int) -> tuple[str, str, list[RequestRecord], list[ResponseRecord]]:
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed. Run: python3 -m pip install playwright && python3 -m playwright install")

    requests: list[RequestRecord] = []
    responses: list[ResponseRecord] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            locale="fr-FR",
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1440, "height": 1100},
        )
        page = context.new_page()

        def on_request(request: Any) -> None:
            if looks_interesting(request.url, request.resource_type):
                requests.append(
                    RequestRecord(
                        method=request.method,
                        url=request.url,
                        resource_type=request.resource_type,
                        post_data=request.post_data,
                        timestamp=utc_now_iso(),
                    )
                )

        def on_response(response: Any) -> None:
            if not looks_interesting(response.url, response.request.resource_type):
                return
            content_type = response.headers.get("content-type")
            body_excerpt = None
            try:
                if content_type and "application/json" in content_type:
                    if "search-api.studapart.com/property" in response.url:
                        body_excerpt = response.text()
                    else:
                        body_excerpt = response.text()[:8000]
            except Exception:
                body_excerpt = None
            responses.append(
                ResponseRecord(
                    method=response.request.method,
                    url=response.url,
                    status=response.status,
                    resource_type=response.request.resource_type,
                    content_type=content_type,
                    body_excerpt=body_excerpt,
                    timestamp=utc_now_iso(),
                )
            )

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(wait_ms)

        html = page.content()
        title = page.title()
        browser.close()
        return html, title, requests, responses


def viability_assessment(html_summary: dict[str, Any], search_api_summary: dict[str, Any] | None) -> dict[str, Any]:
    enabled_types = set(html_summary.get("enabled_listing_types") or [])
    supports_shared = bool({"flatShare", "coliving", "homestay"} & enabled_types)
    hit_count = html_summary.get("meta", {}).get("count")
    search_hits = None
    if search_api_summary and search_api_summary.get("response_summary"):
        search_hits = search_api_summary["response_summary"].get("nb_hits")

    return {
        "supports_shared_modes": supports_shared,
        "shared_modes_enabled": sorted({"flatShare", "coliving", "homestay"} & enabled_types),
        "page_meta_hit_count": hit_count,
        "live_search_hit_count": search_hits,
        "recommended_direction": (
            "search_api_first"
            if search_api_summary and search_api_summary.get("response_summary")
            else "html_config_plus_browser_capture"
        ),
    }


def render_markdown_summary(report: dict[str, Any]) -> str:
    html_summary = report["html_summary"]
    network_summary = report.get("network_summary") or {"requests": []}
    search_api_summary = report.get("search_api_summary")
    viability = report["viability"]

    request_lines = []
    for item in network_summary["requests"][:8]:
        request_lines.append(
            f"- `{item['method']}` {item['url']} "
            f"(count={item['count']}, statuses={item['statuses']})"
        )
    if not request_lines:
        request_lines.append("- No interesting live requests were captured.")

    sample_keys = []
    if search_api_summary and search_api_summary.get("response_summary"):
        sample_keys = search_api_summary["response_summary"].get("sample_listing_keys") or []

    return textwrap.dedent(
        f"""\
        # Studapart Recon

        - URL: `{report['start_url']}`
        - Captured at: `{report['captured_at']}`
        - Title: `{html_summary['title']}`
        - Meta hit count: `{html_summary['meta'].get('count')}`
        - Price range in meta: `{html_summary['meta'].get('min_price')}` to `{html_summary['meta'].get('max_price')}` EUR
        - Enabled listing types: `{", ".join(html_summary.get("enabled_listing_types") or []) or "None"}`
        - Search API: `{html_summary['page_config'].get('elastic_property_url') or 'Not found'}`
        - Recommendation: `{viability['recommended_direction']}`

        ## Shared Signals

        - Shared-capable modes enabled on page: `{", ".join(viability['shared_modes_enabled']) or "None"}`
        - Supports shared search in principle: `{viability['supports_shared_modes']}`
        - Live search hit count: `{viability['live_search_hit_count']}`

        ## Live Requests

        {chr(10).join(request_lines)}

        ## Search API Sample Keys

        - {", ".join(sample_keys[:25]) if sample_keys else "No JSON search result sample captured."}
        """
    )


def write_report_bundle(report: dict[str, Any], output_dir: Path, html: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "summary.md").write_text(render_markdown_summary(report), encoding="utf-8")
    (output_dir / "page.html").write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recon Studapart Lyon search behavior.")
    parser.add_argument("--live", action="store_true", help="Use a browser to capture live search-api requests.")
    parser.add_argument("--offline-html", type=Path, help="Use a saved HTML page instead of fetching live.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--wait-ms", type=int, default=5000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    html = ""
    title = ""
    requests: list[RequestRecord] = []
    responses: list[ResponseRecord] = []

    if args.offline_html:
        html = read_html(args.offline_html)
        soup = BeautifulSoup(html, "html.parser")
        title = compact(soup.title.get_text(" ", strip=True)) if soup.title else ""
    elif args.live:
        html, title, requests, responses = capture_live(url=args.url, wait_ms=args.wait_ms)
        (RAW_HTML_DIR / "logement_etudiant_lyon_live_latest.html").write_text(html, encoding="utf-8")
    else:
        html = fetch_html(args.url)
        soup = BeautifulSoup(html, "html.parser")
        title = compact(soup.title.get_text(" ", strip=True)) if soup.title else ""
        (RAW_HTML_DIR / "logement_etudiant_lyon_latest.html").write_text(html, encoding="utf-8")

    html_summary = summarize_html(html)
    if title and not html_summary.get("title"):
        html_summary["title"] = title
    network_summary = summarize_network(requests, responses) if requests or responses else None
    search_api_summary = summarize_search_api_response(responses)
    viability = viability_assessment(html_summary, search_api_summary)

    report = {
        "source": "studapart",
        "start_url": args.url,
        "captured_at": utc_now_iso(),
        "html_summary": html_summary,
        "network_summary": network_summary,
        "search_api_summary": search_api_summary,
        "viability": viability,
        "requests": [asdict(item) for item in requests],
        "responses": [asdict(item) for item in responses],
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_ROOT / timestamp
    write_report_bundle(report, output_dir, html)

    print(f"Saved recon summary to: {output_dir / 'summary.md'}")
    print(f"Saved recon report to: {output_dir / 'report.json'}")
    print(f"Saved HTML snapshot to: {output_dir / 'page.html'}")
    print(
        "Found search API: "
        f"{html_summary['page_config'].get('elastic_property_url') or 'No'}; "
        f"shared modes: {', '.join(viability['shared_modes_enabled']) or 'none'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
