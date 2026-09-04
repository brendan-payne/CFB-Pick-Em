from __future__ import annotations

from pickem import espn
from pickem.db import get_conn
from pickem.names import is_auburn_game, point_value_for, slug_game


def apply_event_to_game(conn, game: dict, event: dict) -> None:
    away, home = event["away"], event["home"]
    winner = event.get("winner")
    # If our stored home/away is swapped vs ESPN, still set winner by name.
    conn.execute(
        """UPDATE games SET
            espn_event_id = ?,
            espn_url = ?,
            away_espn_id = ?,
            home_espn_id = ?,
            away_logo = ?,
            home_logo = ?,
            away_rank = ?,
            home_rank = ?,
            spread = COALESCE(?, spread),
            kickoff = COALESCE(?, kickoff),
            winner = COALESCE(?, winner),
            status = ?,
            away_score = ?,
            home_score = ?,
            short_detail = ?
        WHERE id = ?""",
        (
            event["espn_event_id"],
            event["espn_url"],
            away["id"] or None,
            home["id"] or None,
            away.get("logo"),
            home.get("logo"),
            away.get("rank"),
            home.get("rank"),
            event.get("spread"),
            event.get("kickoff"),
            winner,
            event["status"],
            away.get("score"),
            home.get("score"),
            event.get("short_detail"),
            game["id"],
        ),
    )


def sync_week_scores(week_id: str | None = None, start=None, end=None) -> dict:
    conn = get_conn()
    if week_id:
        games = [dict(r) for r in conn.execute("SELECT * FROM games WHERE week_id = ?", (week_id,))]
    else:
        games = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM games WHERE status != 'final' OR winner IS NULL"
            )
        ]
        # Also refresh in-progress/open weeks
        games = [
            dict(r)
            for r in conn.execute(
                """SELECT g.* FROM games g
                   JOIN weeks w ON w.id = g.week_id
                   WHERE w.status IN ('open', 'locked') OR g.status IN ('scheduled', 'in_progress')"""
            )
        ]
    if not games:
        conn.close()
        return {"matched": 0, "updated": 0, "events": 0}

    if start is None or end is None:
        start, end = espn.default_window()
    events = espn.collect_events(start, end)
    matched = 0
    with conn:
        for game in games:
            ev = None
            if game.get("espn_event_id"):
                ev = next((e for e in events if e["espn_event_id"] == game["espn_event_id"]), None)
            if ev is None:
                ev = espn.match_event(events, game["away_team"], game["home_team"])
            if ev is None:
                continue
            matched += 1
            apply_event_to_game(conn, game, ev)

        # Auto-finalize a week when every game is final
        weeks = {g["week_id"] for g in games}
        for wid in weeks:
            statuses = [
                r["status"]
                for r in conn.execute("SELECT status FROM games WHERE week_id = ?", (wid,))
            ]
            if statuses and all(s == "final" for s in statuses):
                conn.execute("UPDATE weeks SET status = 'final' WHERE id = ?", (wid,))

    conn.close()
    return {"matched": matched, "updated": matched, "events": len(events)}


def search_espn_games(start, end) -> list[dict]:
    events = espn.collect_events(start, end)
    out = []
    for ev in events:
        away, home = ev["away"]["name"], ev["home"]["name"]
        out.append(
            {
                **ev,
                "is_auburn": is_auburn_game(away, home),
                "point_value": point_value_for(away, home),
            }
        )
    out.sort(key=lambda e: e.get("kickoff") or "")
    return out


def save_slate(week_id: str, event_payloads: list[dict], status: str = "open") -> None:
    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM picks WHERE game_id IN (SELECT id FROM games WHERE week_id = ?)", (week_id,))
        conn.execute("DELETE FROM games WHERE week_id = ?", (week_id,))
        for i, ev in enumerate(event_payloads):
            away = ev["away"]["name"] if isinstance(ev.get("away"), dict) else ev.get("away_team")
            home = ev["home"]["name"] if isinstance(ev.get("home"), dict) else ev.get("home_team")
            label = f"{away} @ {home}"
            gid = ev.get("id") or slug_game(week_id, away, home)
            auburn = is_auburn_game(away, home)
            conn.execute(
                """INSERT INTO games (
                    id, week_id, label, away_team, home_team, espn_event_id, espn_url,
                    away_espn_id, home_espn_id, away_logo, home_logo, away_rank, home_rank,
                    spread, kickoff, is_auburn, point_value, winner, status, away_score,
                    home_score, short_detail, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    gid,
                    week_id,
                    label,
                    away,
                    home,
                    ev.get("espn_event_id"),
                    ev.get("espn_url"),
                    (ev.get("away") or {}).get("id") if isinstance(ev.get("away"), dict) else ev.get("away_espn_id"),
                    (ev.get("home") or {}).get("id") if isinstance(ev.get("home"), dict) else ev.get("home_espn_id"),
                    (ev.get("away") or {}).get("logo") if isinstance(ev.get("away"), dict) else ev.get("away_logo"),
                    (ev.get("home") or {}).get("logo") if isinstance(ev.get("home"), dict) else ev.get("home_logo"),
                    (ev.get("away") or {}).get("rank") if isinstance(ev.get("away"), dict) else ev.get("away_rank"),
                    (ev.get("home") or {}).get("rank") if isinstance(ev.get("home"), dict) else ev.get("home_rank"),
                    ev.get("spread"),
                    ev.get("kickoff"),
                    1 if auburn else 0,
                    15 if auburn else int(ev.get("point_value") or 5),
                    ev.get("winner"),
                    ev.get("status") or "scheduled",
                    (ev.get("away") or {}).get("score") if isinstance(ev.get("away"), dict) else ev.get("away_score"),
                    (ev.get("home") or {}).get("score") if isinstance(ev.get("home"), dict) else ev.get("home_score"),
                    ev.get("short_detail"),
                    i,
                ),
            )
        conn.execute("UPDATE weeks SET status = ? WHERE id = ?", (status, week_id))
    conn.close()
