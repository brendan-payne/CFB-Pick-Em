"""Import Core 10 2026 Pick'em.xlsx into SQLite and checksum Week 0."""

from __future__ import annotations

import json
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


def _load_sheet_grid(z: zipfile.ZipFile, strings: list[str], sheet: str) -> dict[int, dict[int, str]]:
    root = ET.fromstring(z.read(f"xl/worksheets/{sheet}.xml"))
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


def _excel_dt(serial: str) -> str:
    try:
        n = float(serial)
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    # Excel serial from 1899-12-30
    from datetime import datetime as dt, timedelta

    base = dt(1899, 12, 30, tzinfo=timezone.utc)
    return (base + timedelta(days=n)).isoformat()


def _header_map(row: dict[int, str]) -> dict[str, int]:
    return {str(v).strip(): k for k, v in row.items() if str(v).strip()}


def import_xlsx(force: bool = False) -> dict:
    init_db()
    with zipfile.ZipFile(XLSX) as z:
        ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        strings = []
        for si in ss_root.findall("m:si", NS):
            texts = [t.text or "" for t in si.findall(".//m:t", NS)]
            strings.append("".join(texts))
        pre = _load_sheet_grid(z, strings, "sheet2")
        week0 = _load_sheet_grid(z, strings, "sheet3")
        week1 = _load_sheet_grid(z, strings, "sheet4")

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

        for order, slug, label in WEEK_DEFS:
            status = "upcoming"
            if slug == "week-0":
                status = "final"
            elif slug == "week-1":
                status = "open"
            conn.execute(
                """INSERT INTO weeks (id, season, slug, label, sort_order, status)
                   VALUES (?, 2026, ?, ?, ?, ?)""",
                (slug, slug, label, order, status),
            )

        def load_week(grid: dict[int, dict[int, str]], week_id: str, is_final: bool) -> None:
            headers = _header_map(grid[1])
            skip = {"Timestamp", "Your Name", "Total"}
            game_cols = sorted(
                ((col, name) for name, col in headers.items() if name not in skip),
                key=lambda x: x[0],
            )
            game_ids: list[str] = []
            winners: dict[str, str] = {}
            results_row = None
            for rix, row in grid.items():
                if rix == 1:
                    continue
                name = str(row.get(headers.get("Your Name", 2), "")).strip()
                if name.lower() == "results":
                    results_row = row
            for sort_i, (col, label) in enumerate(game_cols):
                away, home = parse_matchup(label)
                gid = slug_game(week_id, away, home)
                game_ids.append(gid)
                auburn = is_auburn_game(away, home)
                winner = None
                status = "scheduled"
                if results_row:
                    winner = str(results_row.get(col, "")).strip() or None
                    if winner:
                        status = "final"
                elif is_final:
                    status = "final"
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
                if winner:
                    winners[gid] = winner

            for rix, row in grid.items():
                if rix == 1:
                    continue
                raw_name = str(row.get(headers.get("Your Name", 2), "")).strip()
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

        load_week(week0, "week-0", True)
        load_week(week1, "week-1", False)

        pre_headers = _header_map(pre[1])
        playoff_cols = sorted(
            (col for name, col in pre_headers.items() if name.startswith("Playoff Team")),
            key=lambda c: c,
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
                    str(row.get(pre_headers.get("Auburn Regular Season Record ", 3), "")).strip(),
                    str(row.get(pre_headers.get("Big 10 Champion", 4), "")).strip(),
                    str(row.get(pre_headers.get("Big 12 Champion", 5), "")).strip(),
                    str(row.get(pre_headers.get("ACC Champion", 6), "")).strip(),
                    str(row.get(pre_headers.get("SEC Champion", 7), "")).strip(),
                    json.dumps(teams),
                    str(row.get(pre_headers.get("National Champion", 19), "")).strip(),
                    _excel_dt(str(row.get(pre_headers.get("Timestamp", 1), ""))),
                ),
            )

        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("imported_at", datetime.now(timezone.utc).isoformat()),
        )

    checksum = _week0_checksum()
    return {"skipped": False, "week0": checksum}


def _week0_checksum() -> dict:
    conn = get_conn()
    games = [dict(r) for r in conn.execute("SELECT * FROM games WHERE week_id = 'week-0'").fetchall()]
    players = [dict(r) for r in conn.execute("SELECT * FROM players").fetchall()]
    excel_totals = {
        "mark": 35,
        "micah": 35,
        "max": 35,
        "brendan": 35,
        "murph": 35,
        "jacob": 35,
        "weston": 30,
        "will": 30,
        "mason": 30,
        "charlie": 30,
        "nathan": 25,
        "buck": 25,
    }
    out = []
    for p in players:
        picks = {
            r["game_id"]: r["picked_team"]
            for r in conn.execute(
                "SELECT game_id, picked_team FROM picks WHERE player_id = ?", (p["id"],)
            )
        }
        pts = week_points_for_player(games, picks)
        out.append(
            {
                "player": p["name"],
                "computed": pts,
                "excel": excel_totals.get(p["id"]),
                "delta_vs_excel": pts - excel_totals.get(p["id"], 0),
            }
        )
    conn.close()
    return {
        "note": (
            "Excel Week 0 totals run 5 high for everyone: the sheet formula "
            "SUMPRODUCT((D2:L2=D$14:L$14)*5) spans through empty column L, and blank=blank "
            "scores as a correct pick. Standings order is unaffected."
        ),
        "players": out,
    }


if __name__ == "__main__":
    result = import_xlsx(force=True)
    print(json.dumps(result, indent=2))
