"""
Location Étudiant Lyon recon
============================

This source is mostly server-rendered, so the recon focuses on:
- counting residence cards on the Lyon page
- identifying shared-accommodation signals in the summaries
- optionally pulling a few detail pages for the strongest candidates

Examples:
  python3 scrapers/location_etudiant/recon.py --offline-html scrapers/location_etudiant/raw_html/lyon_residences.html
  python3 scrapers/location_etudiant/recon.py --live
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


BASE_URL = "https://www.location-etudiant.fr"
DEFAULT_URL = f"{BASE_URL}/residences-etudiantes-lyon.html"
BASE_DIR = Path(__file__).resolve().parent
RAW_HTML_DIR = BASE_DIR / "raw_html"
OUTPUT_ROOT = BASE_DIR / "outputs" / "recon_output"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
SHARED_PATTERNS = [
    (r"\bcoloc", 4, "colocation"),
    (r"\bpartag", 2, "sharing"),
    (r"\bchambres?\b", 2, "room"),
    (r"\bsolo ou en colocation\b", 5, "solo_or_coloc"),
    (r"\bcon[çc]us? pour la coloc", 5, "designed_for_coloc"),
    (r"\bT3\b", 1, "t3"),
]
SOLO_PATTERNS = [
    r"\bstudios?\b",
    r"\bT1\b",
    r"\bT2\b",
]
UNIT_PATTERNS = [
    r"\bstudio[s]?\b",
    r"\bT1\b",
    r"\bT2\b",
    r"\bT3\b",
    r"\bduplex\b",
    r"\bchambre[s]?\b",
    r"\bcolocation\b",
]


@dataclass
class ResidenceCard:
    title: str
    url: str
    operator: str
    address: str
    price_eur: int | None
    price_text: str
    availability: str
    description: str
    unit_types: list[str]
    shared_score: int
    shared_label: str
    shared_signals: list[str]


@dataclass
class DetailSummary:
    url: str
    title: str
    description: str
    unit_types: list[str]
    shared_score: int
    shared_label: str
    shared_signals: list[str]


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


def extract_price(text: str) -> tuple[int | None, str]:
    match = re.search(r"(\d[\d\s]*)\s*€", text)
    if not match:
        return None, ""
    price_num = int(match.group(1).replace(" ", ""))
    return price_num, f"{price_num} EUR"


def extract_unit_types(text: str) -> list[str]:
    found: list[str] = []
    for pattern in UNIT_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.I):
            raw = match.group(0).lower()
            token = "STUDIO" if raw.startswith("studio") else match.group(0).upper()
            if token not in found:
                found.append(token)
    return found


def shared_score_for_text(text: str) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    text_low = text.lower()
    for pattern, weight, label in SHARED_PATTERNS:
        if re.search(pattern, text_low, flags=re.I):
            score += weight
            signals.append(label)
    return score, signals


def shared_label(score: int, text: str) -> str:
    solo_hits = sum(bool(re.search(pattern, text, flags=re.I)) for pattern in SOLO_PATTERNS)
    if score >= 5:
        return "High"
    if score >= 2:
        return "Medium"
    if solo_hits >= 2:
        return "Low / mostly solo"
    return "Low"


def parse_residence_cards(html: str) -> list[ResidenceCard]:
    soup = BeautifulSoup(html, "html.parser")
    cards: list[ResidenceCard] = []
    for card in soup.select(".div-residence-sur"):
        link = card.select_one("a[href]")
        title_node = card.select_one(".div-residence__main__title")
        subtitle_node = card.select_one(".div-residence__main__subtitle")
        address_node = card.select_one(".div-residence__main__address")
        dispo_node = card.select_one(".div-residence__main__dispos")
        desc_node = card.select_one(".div-residence__main__p")
        if link is None or title_node is None:
            continue

        url = urljoin(BASE_URL, link.get("href"))
        title = compact(title_node.get_text(" ", strip=True))
        subtitle = compact(subtitle_node.get_text(" ", strip=True)) if subtitle_node else ""
        address = compact(address_node.get_text(" ", strip=True)) if address_node else ""
        availability = compact(dispo_node.get_text(" ", strip=True)) if dispo_node else ""
        description = compact(desc_node.get_text(" ", strip=True)) if desc_node else ""
        price_eur, price_text = extract_price(subtitle)
        operator = subtitle.split("A partir de")[0].strip() if subtitle else ""
        score, signals = shared_score_for_text(f"{title} {description}")

        cards.append(
            ResidenceCard(
                title=title,
                url=url,
                operator=operator,
                address=address,
                price_eur=price_eur,
                price_text=price_text,
                availability=availability,
                description=description,
                unit_types=extract_unit_types(f"{title} {description}"),
                shared_score=score,
                shared_label=shared_label(score, description),
                shared_signals=signals,
            )
        )
    return cards


def parse_detail_summary(url: str, html: str) -> DetailSummary:
    soup = BeautifulSoup(html, "html.parser")
    title = compact(soup.title.get_text(" ", strip=True)) if soup.title else ""
    meta_desc = ""
    meta_node = soup.find("meta", attrs={"name": "description"})
    if meta_node and meta_node.get("content"):
        meta_desc = compact(meta_node["content"])
    h1 = compact(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else ""
    body_desc = ""
    for node in soup.select(
        ".div-resi_main_left_desc,"
        "p[itemprop='description'],"
        ".div-residence-text,"
        ".div-detail-residence,"
        ".div-residence-description,"
        ".description,"
        ".detail"
    ):
        text = compact(node.get_text(" ", strip=True))
        if len(text) > len(body_desc):
            body_desc = text
    description = max([meta_desc, body_desc], key=len)
    score, signals = shared_score_for_text(f"{title} {h1} {description}")
    return DetailSummary(
        url=url,
        title=title or h1,
        description=description,
        unit_types=extract_unit_types(f"{title} {h1} {description}"),
        shared_score=score,
        shared_label=shared_label(score, description),
        shared_signals=signals,
    )


def summarize_cards(cards: list[ResidenceCard]) -> dict[str, Any]:
    operator_counts = Counter(card.operator for card in cards if card.operator)
    shared_counts = Counter(card.shared_label for card in cards)
    unit_type_counts = Counter(unit for card in cards for unit in card.unit_types)
    sorted_cards = sorted(cards, key=lambda card: (-card.shared_score, card.price_eur or 10**9, card.title))
    return {
        "card_count": len(cards),
        "operator_counts": dict(operator_counts.most_common(10)),
        "shared_label_counts": dict(shared_counts),
        "unit_type_counts": dict(unit_type_counts.most_common(12)),
        "top_shared_candidates": [asdict(card) for card in sorted_cards[:12]],
    }


def write_report_bundle(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "summary.md").write_text(render_markdown_summary(report), encoding="utf-8")


def render_markdown_summary(report: dict[str, Any]) -> str:
    page = report["page"]
    summary = report["summary"]
    lines = [
        "# Location Étudiant recon summary",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Page title: `{page['title']}`",
        f"- H1: `{page['h1']}`",
        f"- Residence cards found: `{summary['card_count']}`",
        f"- Shared labels: `{summary['shared_label_counts']}`",
        f"- Top operators: `{summary['operator_counts']}`",
        f"- Unit types seen: `{summary['unit_type_counts']}`",
        "",
        "## Top shared-friendly candidates",
    ]
    for card in summary["top_shared_candidates"][:8]:
        lines.append(
            f"- `{card['title']}` | `{card['price_text'] or 'N/A'}` | `{card['shared_label']}` | "
            f"signals: `{', '.join(card['shared_signals']) or 'none'}`"
        )
    if report.get("details"):
        lines.extend(["", "## Detail samples"])
        for detail in report["details"]:
            lines.append(
                f"- `{detail['title']}` | `{detail['shared_label']}` | "
                f"units: `{', '.join(detail['unit_types']) or 'none'}` | "
                f"signals: `{', '.join(detail['shared_signals']) or 'none'}`"
            )
    return "\n".join(lines) + "\n"


def build_page_summary(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "title": compact(soup.title.get_text(" ", strip=True)) if soup.title else "",
        "h1": compact(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else "",
        "link_count": len(soup.find_all("a")),
        "script_count": len(soup.find_all("script")),
        "form_count": len(soup.find_all("form")),
    }


def run_offline(html_path: Path, detail_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    html = read_html(html_path)
    cards = parse_residence_cards(html)
    report = {
        "mode": "offline",
        "generated_at": utc_now_iso(),
        "page": build_page_summary(html) | {"file": str(html_path)},
        "summary": summarize_cards(cards),
        "details": [],
    }
    for detail_path in detail_paths:
        detail_html = read_html(detail_path)
        report["details"].append(asdict(parse_detail_summary(str(detail_path), detail_html)))
    write_report_bundle(report, output_dir)
    return report


def run_live(start_url: str, fetch_detail_limit: int, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html = fetch_html(start_url)
    (output_dir / "page.html").write_text(html, encoding="utf-8")
    cards = parse_residence_cards(html)
    sorted_cards = sorted(cards, key=lambda card: (-card.shared_score, card.price_eur or 10**9, card.title))

    report = {
        "mode": "live",
        "generated_at": utc_now_iso(),
        "page": build_page_summary(html) | {"url": start_url},
        "summary": summarize_cards(cards),
        "details": [],
    }
    for card in sorted_cards[:fetch_detail_limit]:
        if card.shared_score <= 0:
            break
        detail_html = fetch_html(card.url)
        detail_name = re.sub(r"[^a-zA-Z0-9]+", "_", card.title).strip("_").lower()[:80] or "detail"
        (output_dir / f"{detail_name}.html").write_text(detail_html, encoding="utf-8")
        report["details"].append(asdict(parse_detail_summary(card.url, detail_html)))

    write_report_bundle(report, output_dir)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recon the Location Étudiant Lyon residences page and flag shared-friendly candidates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              python3 scrapers/location_etudiant/recon.py --offline-html scrapers/location_etudiant/raw_html/lyon_residences.html
              python3 scrapers/location_etudiant/recon.py --live
            """
        ),
    )
    parser.add_argument("--live", action="store_true", help="Fetch the live Lyon residences page.")
    parser.add_argument("--offline-html", type=Path, help="Analyse a saved Lyon residences HTML file.")
    parser.add_argument("--detail-html", type=Path, action="append", default=[], help="Optional saved detail page(s) to include in the report.")
    parser.add_argument("--fetch-detail-limit", type=int, default=2, help="Live mode: fetch this many strong shared-detail candidates.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Live mode start URL.")
    parser.add_argument("--output-dir", type=Path, help="Optional output directory override.")
    return parser.parse_args()


def main() -> int:
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    args = parse_args()
    timestamp_dir = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (OUTPUT_ROOT / timestamp_dir)

    if args.live:
        report = run_live(start_url=args.url, fetch_detail_limit=args.fetch_detail_limit, output_dir=output_dir)
    elif args.offline_html:
        report = run_offline(html_path=args.offline_html, detail_paths=args.detail_html, output_dir=output_dir)
    else:
        raise SystemExit("Choose either --live or --offline-html.")

    print(f"Saved recon output to: {output_dir}")
    print((output_dir / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
