"""
Minimal shared listing shape for multi-source scrapers.

This is intentionally small for now. It gives each scraper a common target
without forcing the full storage layer design too early.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class NormalizedListing:
    source: str
    url: str
    title: str
    price_eur: int | None
    postcode: str | None
    latitude: float | None = None
    longitude: float | None = None
    student_occupants: str = ""
    worker_occupants: str = ""
    scraped_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)
