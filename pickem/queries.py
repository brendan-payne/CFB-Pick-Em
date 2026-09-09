from __future__ import annotations

import json

from pickem.db import get_conn, rows
from pickem.scoring import game_locked, week_points_for_player


def league_state(current_week_id: str | None = None) -> dict:
    conn = get_conn()
    players = rows(conn, "SELECT * FROM players ORDER BY name")
    weeks = rows(conn, "SELECT * FROM weeks ORDER BY sort_order")
    games = rows(conn, "SELECT * FROM games ORDER BY sort_order, label")
    picks = rows(conn, "SELECT * FROM picks")
    preseason = rows(conn, "SELECT * FROM preseason_picks")
    conn.close()

    for p in preseason:
        try:
            p["playoff_teams"] = json.loads(p["playoff_teams"] or "[]")
        except json.JSONDecodeError:
            p["playoff_teams"] = []

    picks_map: dict[tuple[str, str], dict] = {(p["player_id"], p["game_id"]): p for p in picks}
    games_by_week: dict[str, list] = {}
    for g in games:
        games_by_week.setdefault(g["week_id"], []).append(g)

    if not current_week_id:
        current_week_id = _default_week(weeks)

    standings = []
    for player in players:
        weekly = {}
        total = 0
        for week in weeks:
            wg = games_by_week.get(week["id"], [])
            by_game = {
                g["id"]: (picks_map.get((player["id"], g["id"])) or {}).get("picked_team")
                for g in wg
            }
            pts = week_points_for_player(wg, {k: v for k, v in by_game.items() if v})
            weekly[week["id"]] = pts
            total += pts
        standings.append(
            {
                **player,
                "weekly": weekly,
                "total": total,
                "picks": [p for p in picks if p["player_id"] == player["id"]],
            }
        )
    standings.sort(key=lambda r: (-r["total"], r["name"]))
    for i, row in enumerate(standings):
        row["rank"] = i + 1
        if i > 0 and row["total"] == standings[i - 1]["total"]:
            row["rank"] = standings[i - 1]["rank"]

    games_out = []
    for g in games:
        games_out.append({**g, "locked": game_locked(g)})

    return {
        "players": players,
        "weeks": weeks,
        "games": games_out,
        "picks": picks,
        "preseason": preseason,
        "standings": standings,
        "currentWeekId": current_week_id,
        "scoring": {
            "weekly": 5,
            "auburn": 15,
            "preseason": {
                "auburnRecord": 50,
                "power4Champ": 10,
                "playoffTeam": 10,
                "nationalChampion": 50,
            },
            "cfp": {"first": 5, "quarters": 10, "semis": 20, "championship": 40},
        },
    }


def _default_week(weeks: list[dict]) -> str:
    for status in ("open", "locked", "upcoming"):
        for w in weeks:
            if w["status"] == status:
                return w["id"]
    for w in reversed(weeks):
        if w["status"] == "final":
            return w["id"]
    return weeks[0]["id"] if weeks else "week-1"
