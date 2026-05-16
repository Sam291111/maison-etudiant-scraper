"""
Small web dashboard for the combined listing store.

What it does:
- serves the active combined listing table
- exposes JSON endpoints for listings and status
- lets a protected refresh endpoint trigger the full scraper pipeline

Run locally:
  python3 listing_store/web_app.py
"""

from __future__ import annotations

import html
import json
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIServer, make_server


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "listing_store" / "outputs"
DB_PATH = Path(os.environ.get("LISTING_STORE_DB_PATH", str(OUTPUT_DIR / "listings.sqlite3")))
SUMMARY_PATH = Path(os.environ.get("LISTING_STORE_SUMMARY_PATH", str(OUTPUT_DIR / "latest_pipeline_summary.json")))
REFRESH_STATUS_PATH = Path(os.environ.get("LISTING_STORE_REFRESH_STATUS_PATH", str(OUTPUT_DIR / "latest_refresh_status.json")))
WORKBOOK_PATH = Path(os.environ.get("LISTING_STORE_WORKBOOK_PATH", str(OUTPUT_DIR / "lyon_master_listings.xlsx")))
ACTIVE_JSON_PATH = Path(os.environ.get("LISTING_STORE_ACTIVE_JSON_PATH", str(OUTPUT_DIR / "active_listings.json")))
ACTIVE_CSV_PATH = Path(os.environ.get("LISTING_STORE_ACTIVE_CSV_PATH", str(OUTPUT_DIR / "active_listings.csv")))
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "")
PORT = int(os.environ.get("PORT", "8000"))

REFRESH_LOCK = threading.Lock()
REFRESH_THREAD: threading.Thread | None = None


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def json_response(start_response, payload: Any, status: str = "200 OK"):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def text_response(start_response, body: str, status: str = "200 OK", content_type: str = "text/plain; charset=utf-8"):
    data = body.encode("utf-8")
    start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(data)))])
    return [data]


def file_response(start_response, path: Path, content_type: str):
    if not path.exists():
        return text_response(start_response, "Not found", "404 Not Found")
    data = path.read_bytes()
    start_response(
        "200 OK",
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(data))),
            ("Content-Disposition", f'attachment; filename="{path.name}"'),
        ],
    )
    return [data]


def load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_active_listings() -> list[dict[str, Any]]:
    if ACTIVE_JSON_PATH.exists():
        payload = load_json(ACTIVE_JSON_PATH)
        if isinstance(payload, list):
            return payload

    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT
                source,
                listing_uid,
                source_listing_id,
                title,
                price_eur,
                postcode,
                latitude,
                longitude,
                first_seen_at,
                last_seen_at,
                latest_status,
                url,
                latest_raw_json
            FROM listings
            WHERE is_active = 1
            ORDER BY COALESCE(price_eur, 999999), source, title
            """
        ).fetchall()
    finally:
        conn.close()

    result: list[dict[str, Any]] = []
    for row in rows:
        raw = json.loads(str(row[12]))
        result.append(
            {
                "source": row[0],
                "listing_uid": row[1],
                "source_listing_id": row[2],
                "title": row[3],
                "price_eur": row[4],
                "postcode": row[5],
                "latitude": row[6],
                "longitude": row[7],
                "first_seen_at": row[8],
                "last_seen_at": row[9],
                "latest_status": row[10],
                "url": row[11],
                "city": raw.get("city") or "",
                "address": raw.get("full_address") or raw.get("address") or raw.get("address_text") or raw.get("street") or raw.get("location_text") or "",
                "availability": raw.get("availability") or raw.get("available_from") or "",
                "extra_summary": "",
            }
        )
    return result


def refresh_running() -> bool:
    with REFRESH_LOCK:
        return REFRESH_THREAD is not None and REFRESH_THREAD.is_alive()


def launch_refresh(triggered_by: str) -> bool:
    global REFRESH_THREAD
    with REFRESH_LOCK:
        if REFRESH_THREAD is not None and REFRESH_THREAD.is_alive():
            return False

        def target() -> None:
            subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "listing_store" / "run_pipeline.py"), "--triggered-by", triggered_by],
                cwd=str(PROJECT_ROOT),
            )

        REFRESH_THREAD = threading.Thread(target=target, daemon=True)
        REFRESH_THREAD.start()
        return True


def render_dashboard(listings: list[dict[str, Any]], summary: dict[str, Any] | None, refresh_status: dict[str, Any] | None) -> str:
    summary = summary or {}
    refresh_status = refresh_status or {}
    embedded_rows = json.dumps(listings, ensure_ascii=False)
    source_options = sorted({row["source"] for row in listings})
    source_option_html = "".join(
        f'<option value="{html.escape(source)}">{html.escape(source)}</option>'
        for source in source_options
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lyon Accommodation Dashboard</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --ink: #182026;
      --muted: #6b7177;
      --accent: #0c6c67;
      --accent-2: #c45b39;
      --line: #ddd2c4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(196,91,57,0.12), transparent 28%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 28px 18px 40px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(12,108,103,0.98), rgba(16,54,68,0.96));
      color: white;
      padding: 22px 24px;
      border-radius: 18px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.12);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(1.8rem, 2vw, 2.6rem);
      line-height: 1.1;
    }}
    .hero p {{
      margin: 0;
      color: rgba(255,255,255,0.88);
      max-width: 70ch;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 18px 0 22px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 10px 24px rgba(24,32,38,0.05);
    }}
    .label {{
      color: var(--muted);
      font-size: 0.88rem;
      margin-bottom: 6px;
    }}
    .value {{
      font-size: 1.5rem;
      font-weight: 700;
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr auto auto auto;
      gap: 10px;
      margin: 18px 0;
    }}
    input, select, button, a.button {{
      font: inherit;
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 10px 12px;
      background: white;
      color: var(--ink);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    button, a.button {{
      background: var(--accent);
      border-color: var(--accent);
      color: white;
      cursor: pointer;
    }}
    button.secondary, a.button.secondary {{
      background: white;
      color: var(--accent);
    }}
    .table-wrap {{
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 12px 24px rgba(24,32,38,0.05);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1100px;
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid #ece3d9;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f3ece1;
      cursor: pointer;
      white-space: nowrap;
    }}
    td a {{
      color: var(--accent);
    }}
    .muted {{ color: var(--muted); }}
    .status {{
      margin: 10px 0 0;
      font-size: 0.95rem;
      color: var(--muted);
    }}
    @media (max-width: 980px) {{
      .toolbar {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Lyon Shared Accommodation Dashboard</h1>
      <p>Combined listings from ImmoJeune, La Carte des Colocs, Location Étudiant, and Studapart. Sort any column, filter by source, and download the latest exports.</p>
    </section>

    <section class="stats">
      <div class="card"><div class="label">Active Listings</div><div class="value">{summary.get("active_count", len(listings))}</div></div>
      <div class="card"><div class="label">Sources</div><div class="value">{len(summary.get("sources_ingested", source_options))}</div></div>
      <div class="card"><div class="label">New In Latest Run</div><div class="value">{summary.get("new_count", 0)}</div></div>
      <div class="card"><div class="label">Updated In Latest Run</div><div class="value">{summary.get("updated_count", 0)}</div></div>
      <div class="card"><div class="label">Removed In Latest Run</div><div class="value">{summary.get("removed_count", 0)}</div></div>
      <div class="card"><div class="label">Refresh Status</div><div class="value">{html.escape(str(refresh_status.get("status", "unknown")))}</div></div>
    </section>

    <div class="toolbar">
      <input id="searchInput" placeholder="Search title, address, postcode, source">
      <select id="sourceFilter">
        <option value="">All sources</option>
        {source_option_html}
      </select>
      <select id="statusFilter">
        <option value="">Any status</option>
        <option value="new">new</option>
        <option value="updated">updated</option>
        <option value="unchanged">unchanged</option>
      </select>
      <a class="button" href="/download/master.xlsx">Download XLSX</a>
      <a class="button secondary" href="/download/active.csv">Download CSV</a>
      <a class="button secondary" href="/api/listings">JSON API</a>
    </div>

    <div class="status">
      Latest refresh: {html.escape(str(refresh_status.get("finished_at") or refresh_status.get("started_at") or "unknown"))}
      <span class="muted">| Triggered by: {html.escape(str(refresh_status.get("triggered_by", "unknown")))}</span>
    </div>

    <div class="table-wrap">
      <table id="listingTable">
        <thead>
          <tr>
            <th data-key="source">Source</th>
            <th data-key="title">Title</th>
            <th data-key="price_eur">Price EUR</th>
            <th data-key="postcode">Postcode</th>
            <th data-key="city">City</th>
            <th data-key="address">Address</th>
            <th data-key="availability">Availability</th>
            <th data-key="extra_summary">Summary</th>
            <th data-key="first_seen_at">First Seen</th>
            <th data-key="last_seen_at">Last Seen</th>
            <th data-key="url">Link</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <script>
    const rows = {embedded_rows};
    const tbody = document.querySelector("#listingTable tbody");
    const searchInput = document.getElementById("searchInput");
    const sourceFilter = document.getElementById("sourceFilter");
    const statusFilter = document.getElementById("statusFilter");
    let sortKey = "price_eur";
    let sortDirection = "asc";

    function safe(value) {{
      return value === null || value === undefined ? "" : String(value);
    }}

    function compareValues(a, b) {{
      if (a === "" && b !== "") return 1;
      if (b === "" && a !== "") return -1;
      const numA = Number(a);
      const numB = Number(b);
      if (!Number.isNaN(numA) && !Number.isNaN(numB) && a !== "" && b !== "") {{
        return numA - numB;
      }}
      return safe(a).localeCompare(safe(b), undefined, {{ sensitivity: "base" }});
    }}

    function filteredRows() {{
      const query = searchInput.value.trim().toLowerCase();
      const source = sourceFilter.value;
      const status = statusFilter.value;
      return rows.filter((row) => {{
        if (source && row.source !== source) return false;
        if (status && safe(row.latest_status).toLowerCase() !== status) return false;
        if (!query) return true;
        const haystack = [
          row.source, row.title, row.postcode, row.city, row.address, row.availability, row.extra_summary
        ].map(safe).join(" ").toLowerCase();
        return haystack.includes(query);
      }});
    }}

    function render() {{
      const data = filteredRows().slice().sort((left, right) => {{
        const result = compareValues(left[sortKey], right[sortKey]);
        return sortDirection === "asc" ? result : -result;
      }});

      tbody.innerHTML = data.map((row) => `
        <tr>
          <td>${{safe(row.source)}}</td>
          <td>${{safe(row.title)}}</td>
          <td>${{safe(row.price_eur)}}</td>
          <td>${{safe(row.postcode)}}</td>
          <td>${{safe(row.city)}}</td>
          <td>${{safe(row.address)}}</td>
          <td>${{safe(row.availability)}}</td>
          <td>${{safe(row.extra_summary)}}</td>
          <td>${{safe(row.first_seen_at)}}</td>
          <td>${{safe(row.last_seen_at)}}</td>
          <td><a href="${{safe(row.url)}}" target="_blank" rel="noreferrer">Open</a></td>
        </tr>
      `).join("");
    }}

    document.querySelectorAll("th[data-key]").forEach((header) => {{
      header.addEventListener("click", () => {{
        const key = header.dataset.key;
        if (sortKey === key) {{
          sortDirection = sortDirection === "asc" ? "desc" : "asc";
        }} else {{
          sortKey = key;
          sortDirection = "asc";
        }}
        render();
      }});
    }});

    searchInput.addEventListener("input", render);
    sourceFilter.addEventListener("change", render);
    statusFilter.addEventListener("change", render);
    render();
  </script>
</body>
</html>
"""


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")
    query = parse_qs(environ.get("QUERY_STRING", ""))

    if method == "GET" and path == "/healthz":
        return json_response(start_response, {"ok": True, "refresh_running": refresh_running()})

    if method == "GET" and path == "/api/summary":
        return json_response(start_response, load_json(SUMMARY_PATH) or {})

    if method == "GET" and path == "/api/refresh-status":
        return json_response(start_response, load_json(REFRESH_STATUS_PATH) or {})

    if method == "GET" and path == "/api/listings":
        return json_response(start_response, load_active_listings())

    if method == "GET" and path == "/download/master.xlsx":
        return file_response(
            start_response,
            WORKBOOK_PATH,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if method == "GET" and path == "/download/active.csv":
        return file_response(start_response, ACTIVE_CSV_PATH, "text/csv; charset=utf-8")

    if method == "GET" and path == "/download/active.json":
        return file_response(start_response, ACTIVE_JSON_PATH, "application/json; charset=utf-8")

    if method == "POST" and path == "/admin/refresh":
        token = environ.get("HTTP_X_REFRESH_TOKEN") or query.get("token", [""])[0]
        if not REFRESH_TOKEN or token != REFRESH_TOKEN:
            return json_response(start_response, {"error": "forbidden"}, "403 Forbidden")
        if not launch_refresh("render_cron"):
            return json_response(start_response, {"status": "already_running"}, "409 Conflict")
        return json_response(start_response, {"status": "started"}, "202 Accepted")

    if method == "GET" and path == "/":
        listings = load_active_listings()
        summary = load_json(SUMMARY_PATH)
        refresh_status = load_json(REFRESH_STATUS_PATH)
        return text_response(start_response, render_dashboard(listings, summary, refresh_status), content_type="text/html; charset=utf-8")

    return text_response(start_response, "Not found", "404 Not Found")


def main() -> int:
    with make_server("0.0.0.0", PORT, application, server_class=ThreadingWSGIServer) as httpd:
        print(f"Serving listing dashboard on http://0.0.0.0:{PORT}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
