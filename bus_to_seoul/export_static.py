"""Export live and historical bus data for the GitHub Pages static site."""
from __future__ import annotations

import json
from pathlib import Path

from . import db
from .config import ROOT
from .naver import NaverBusClient
from .service import live_status, stats


def export(output_dir: Path | None = None):
    output_dir = output_dir or ROOT / "site" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = db.connect()
    try:
        live = live_status(NaverBusClient(), conn)
        history = stats(conn)
    finally:
        conn.close()

    (output_dir / "live.json").write_text(
        json.dumps(live, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "stats.json").write_text(
        json.dumps(history, ensure_ascii=False),
        encoding="utf-8",
    )
