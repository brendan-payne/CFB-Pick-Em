"""Import Core 10 2026 Pick'em.xlsx into SQLite."""

from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pickem.db import get_conn, init_db
from pickem.names import (
    PLAYERS,
    is_auburn_game,
    parse_matchup,
    player_id_from_name,
    point_value_for,
    slug_game,
)
from pickem.scoring import week_points_for_player

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
ROOT = Path(__file__).resolve().parent.parent
XLSX = next(ROOT.glob("*.xlsx"))

WEEK_DEFS = [
    (0, "week-0", "Week 0"),
    (1, "week-1", "Week 1"),
    (2, "week-2", "Week 2"),
    (3, "week-3", "Week 3"),
    (4, "week-4", "Week 4"),
    (5, "week-5", "Week 5"),
    (6, "week-6", "Week 6"),
    (7, "week-7", "Week 7"),
    (8, "week-8", "Week 8"),
    (9, "week-9", "Week 9"),
    (10, "week-10", "Week 10"),
    (11, "week-11", "Week 11"),
    (12, "week-12", "Week 12"),
    (13, "week-13", "Week 13"),
    (14, "week-14", "Week 14"),
    (15, "champ-week", "Champ Week"),
    (16, "cfp-first", "Playoff - First Round"),
    (17, "cfp-quarters", "Playoff - Quarterfinals"),
    (18, "cfp-semis", "Playoff - Semifinals"),
    (19, "cfp-title", "Playoff - Championship"),
]


def _col_row(ref: str) -> tuple[int, int]:
    col, row = "", ""
    for ch in ref:
        if ch.isalpha():
            col += ch
        else:
            row += ch
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n, int(row)


def _load_sheet_grid(z: zipfile.ZipFile, strings: list[str], path: str) -> dict[int, dict[int, str]]:
    root = ET.fromstring(z.read(path if path.startswith("xl/") else f"xl/{path}"))
    rows: dict[int, dict[int, str]] = defaultdict(dict)
    for c in root.findall(".//m:c", NS):
        ref = c.attrib.get("r")
        cell_type = c.attrib.get("t")
        v = c.find("m:v", NS)
        if v is None or ref is None:
            continue
        val = v.text or ""
        if cell_type == "s":
            val = strings[int(val)]
        col, row = _col_row(ref)
        rows[row][col] = val
    return rows


def _sheet_map(z: zipfile.ZipFile) -> dict[str, str]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {
        r.attrib["Id"]: r.attrib["Target"]
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    }
    out: dict[str, str] = {}
    for s in wb.findall("m:sheets/m:sheet", NS):
        target = rels[s.attrib[REL]]
        if not target.startswith("xl/"):
            target = "xl/" + target
        out[s.attrib["name"]] = target
    return out


def _excel_dt(serial: str) -> str:
    try:
        n = float(serial)
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    from datetime import datetime as dt, timedelta

    base = dt(1899, 12, 30, tzinfo=timezone.utc)
    return (base + timedelta(days=n)).isoformat()


def _header_map(row: dict[int, str]) -> dict[str, int]:
    return {str(v).strip(): k for k, v in row.items() if str(v).strip()}


def _week_slug_from_label(label: str) -> str | None:
    m = re.fullmatch(r"Week\s+(\d+)", label.strip(), flags=re.I)
    if m:
        return f"week-{int(m.group(1))}"
    return None


def xlsx_mtime_iso() -> str:
    return datetime.fromtimestamp(XLSX.stat().st_mtime, tz=timezone.utc).isoformat()


def needs_reimport() -> bool:
    if not XLSX.exists():
        return False
    init_db()
    conn = get_conn()
    try:
        players = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
        if players == 0:
            return True
        imported = conn.execute(
            "SELECT value FROM meta WHERE key = 'xlsx_mtime'"
        ).fetchone()
        if not imported:
            return True
        return imported["value"] != xlsx_mtime_iso()
    finally:
        conn.close()


def import_xlsx(force: bool = False) -> dict:
    init_db()
    with zipfile.ZipFile(XLSX) as z:
        ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = []
        for si in ss_root.findall("m:si", NS):
            texts = [t.text or "" for t in si.findall(".//m:t", NS)]
            strings.append("".join(texts))
        sheets = _sheet_map(z)
        pre_path = sheets.get("Pre-Season Predictions")
        if not pre_path:
            raise FileNotFoundError("Pre-Season Predictions sheet missing from workbook")
        pre = _load_sheet_grid(z, strings, pre_path)
        week_grids: dict[str, dict[int, dict[int, str]]] = {}
        for name, path in sheets.items():
            slug = _week_slug_from_label(name)
            if slug:
                week_grids[slug] = _load_sheet_grid(z, strings, path)

    conn = get_conn()
    existing = conn.execute("SELECT COUNT(*) AS n FROM picks").fetchone()["n"]
    if existing and not force:
        conn.close()
        return {"skipped": True, "reason": "database already has picks"}

    with conn:
        conn.execute("DELETE FROM picks")
        conn.execute("DELETE FROM preseason_picks")
        conn.execute("DELETE FROM games")
        conn.execute("DELETE FROM weeks")
        conn.execute("DELETE FROM players")
        conn.execute("DELETE FROM meta")

        for p in PLAYERS:
            conn.execute("INSERT INTO players (id, name) VALUES (?, ?)", (p["id"], p["name"]))

        # Highest numbered week with a sheet (and no Results) becomes the open week.
        def week_has_results(grid: dict[int, dict[int, str]]) -> bool:
            headers = _header_map(grid[1])
            name_col = headers.get("Your Name", 2)
            for rix, row in grid.items():
                if rix == 1:
                    continue
                if str(row.get(name_col, "")).strip().lower() == "results":
                    return True
            return False

        present = sorted(
            week_grids.keys(),
            key=lambda s: next(o for o, slug, _ in WEEK_DEFS if slug == s),
        )
        # Prefer the latest week that has no Results row; else the latest sheet.
        open_week = present[-1] if present else "week-1"
        for slug in reversed(present):
            if not week_has_results(week_grids[slug]):
                open_week = slug
                break

        for order, slug, label in WEEK_DEFS:
            status = "upcoming"
            if slug in week_grids:
                if week_has_results(week_grids[slug]):
                    status = "final"
                elif slug == open_week:
                    status = "open"
                else:
                    status = "final"
            conn.execute(
                """INSERT INTO weeks (id, season, slug, label, sort_order, status)
                   VALUES (?, 2026, ?, ?, ?, ?)""",
                (slug, slug, label, order, status),
            )

        def load_week(grid: dict[int, dict[int, str]], week_id: str) -> dict:
            headers = _header_map(grid[1])
            skip = {"Timestamp", "Your Name", "Total"}
            game_cols = sorted(
                ((col, name) for name, col in headers.items() if name not in skip),
                key=lambda x: x[0],
            )
            results_row = None
            name_col = headers.get("Your Name", 2)
            for rix, row in grid.items():
                if rix == 1:
                    continue
                if str(row.get(name_col, "")).strip().lower() == "results":
                    results_row = row
            games_loaded = 0
            finals = 0
            for sort_i, (col, label) in enumerate(game_cols):
                away, home = parse_matchup(label)
                gid = slug_game(week_id, away, home)
                auburn = is_auburn_game(away, home)
                winner = None
                status = "scheduled"
                if results_row is not None:
                    winner = str(results_row.get(col, "")).strip() or None
                    if winner:
                        status = "final"
                        finals += 1
                conn.execute(
                    """INSERT INTO games (
                        id, week_id, label, away_team, home_team, is_auburn, point_value,
                        winner, status, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        gid,
                        week_id,
                        label,
                        away,
                        home,
                        1 if auburn else 0,
                        point_value_for(away, home),
                        winner,
                        status,
                        sort_i,
                    ),
                )
                games_loaded += 1

            picks_loaded = 0
            for rix, row in grid.items():
                if rix == 1:
                    continue
                raw_name = str(row.get(name_col, "")).strip()
                if not raw_name or raw_name.lower() == "results":
                    continue
                pid = player_id_from_name(raw_name)
                if not pid:
                    continue
                submitted = _excel_dt(str(row.get(headers.get("Timestamp", 1), "")))
                for col, label in game_cols:
                    away, home = parse_matchup(label)
                    gid = slug_game(week_id, away, home)
                    pick = str(row.get(col, "")).strip()
                    if not pick:
                        continue
                    conn.execute(
                        """INSERT OR REPLACE INTO picks (player_id, game_id, picked_team, submitted_at)
                           VALUES (?, ?, ?, ?)""",
                        (pid, gid, pick, submitted),
                    )
                    picks_loaded += 1
            return {"games": games_loaded, "finals": finals, "picks": picks_loaded}

        week_stats = {}
        for slug, grid in week_grids.items():
            week_stats[slug] = load_week(grid, slug)

        pre_headers = _header_map(pre[1])
        playoff_cols = sorted(
            (col for name, col in pre_headers.items() if name.startswith("Playoff Team")),
            key=lambda c: c,
        )
        # Auburn record header sometimes has a trailing space in the form export.
        auburn_key = next(
            (k for k in pre_headers if k.lower().startswith("auburn regular season")),
            "Auburn Regular Season Record",
        )
        for rix, row in pre.items():
            if rix == 1:
                continue
            raw_name = str(row.get(pre_headers.get("Your Name", 2), "")).strip()
            if not raw_name:
                continue
            pid = player_id_from_name(raw_name)
            if not pid:
                continue
            teams = [
                str(row.get(c, "")).strip()
                for c in playoff_cols
                if str(row.get(c, "")).strip()
            ]
            conn.execute(
                """INSERT OR REPLACE INTO preseason_picks (
                    player_id, auburn_record, big10, big12, acc, sec,
                    playoff_teams, national_champion, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid,
                    str(row.get(pre_headers.get(auburn_key, 3), "")).strip(),
                    str(row.get(pre_headers.get("Big 10 Champion", 4), "")).strip(),
                    str(row.get(pre_headers.get("Big 12 Champion", 5), "")).strip(),
                    str(row.get(pre_headers.get("ACC Champion", 6), "")).strip(),
                    str(row.get(pre_headers.get("SEC Champion", 7), "")).strip(),
                    json.dumps(teams),
                    str(row.get(pre_headers.get("National Champion", 19), "")).strip(),
                    _excel_dt(str(row.get(pre_headers.get("Timestamp", 1), ""))),
                ),
            )

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("imported_at", now),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("xlsx_mtime", xlsx_mtime_iso()),
        )

    return {
        "skipped": False,
        "weeks": week_stats,
        "open_week": open_week,
        "standings": _standings_snapshot(),
        "espn_fill": _fill_missing_from_espn(),
    }


def _fill_missing_from_espn() -> dict:
    """After import, pull ESPN scores for any unfinished/missing winners."""
    from datetime import date, timedelta

    from pickem.sync import sync_week_scores

    end = date.today()
    start = end - timedelta(days=16)
    return sync_week_scores(start=start, end=end)


def _standings_snapshot() -> list[dict]:
    conn = get_conn()
    players = [dict(r) for r in conn.execute("SELECT * FROM players").fetchall()]
    games = [dict(r) for r in conn.execute("SELECT * FROM games").fetchall()]
    by_week: dict[str, list] = defaultdict(list)
    for g in games:
        by_week[g["week_id"]].append(g)
    out = []
    for p in players:
        picks = {
            r["game_id"]: r["picked_team"]
            for r in conn.execute(
                "SELECT game_id, picked_team FROM picks WHERE player_id = ?", (p["id"],)
            )
        }
        weekly = {}
        total = 0
        for wid, wg in by_week.items():
            pts = week_points_for_player(wg, picks)
            weekly[wid] = pts
            total += pts
        out.append({"player": p["name"], "weekly": weekly, "total": total})
    conn.close()
    out.sort(key=lambda r: (-r["total"], r["player"]))
    return out


if __name__ == "__main__":
    result = import_xlsx(force=True)
    print(json.dumps(result, indent=2))
