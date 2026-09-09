from __future__ import annotations

from pickem import espn
from pickem.db import get_conn
from pickem.names import is_auburn_game, point_value_for, slug_game, teams_match
from pickem.scoring import lock_at_for_saturday, saturday_from_games


def apply_event_to_game(conn, game: dict, event: dict) -> None:
    away, home = event["away"], event["home"]
    winner = event.get("winner")
    if not winner and event.get("status") == "final":
        ascore, hscore = away.get("score"), home.get("score")
        if ascore is not None and hscore is not None:
            if hscore > ascore:
                winner = home["name"]
            elif ascore > hscore:
                winner = away["name"]
    # Prefer our slate team names when ESPN returns a full display name.
    if winner:
        if teams_match(winner, game["home_team"]):
            winner = game["home_team"]
        elif teams_match(winner, game["away_team"]):
            winner = game["away_team"]
    # Keep spreadsheet winners; only fill blanks from ESPN.
    final_winner = game.get("winner") or winner
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
            winner = ?,
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
            final_winner,
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


def _ensure_auburn_on_slate(events: list[dict]) -> list[dict]:
    def auburnish(ev: dict) -> bool:
        if ev.get("is_auburn"):
            return True
        away = ev["away"]["name"] if isinstance(ev.get("away"), dict) else ev.get("away_team") or ""
        home = ev["home"]["name"] if isinstance(ev.get("home"), dict) else ev.get("home_team") or ""
        return is_auburn_game(away, home)

    if any(auburnish(ev) for ev in events):
        return events
    sat = saturday_from_games([{"kickoff": ev.get("kickoff")} for ev in events])
    if not sat:
        return events
    found = next((ev for ev in search_espn_games(sat, sat) if ev.get("is_auburn")), None)
    if not found:
        return events
    merged = [found] + list(events)
    auburn = [ev for ev in merged if auburnish(ev)][:1]
    rest = [ev for ev in merged if not auburnish(ev)][:9]
    return auburn + rest


def search_espn_games(start, end) -> list[dict]:
    events = espn.collect_events(start, end)
    # Auburn may play Friday; still pin them on this week's Saturday slate.
    from datetime import timedelta

    auburn_days = espn.collect_events(start - timedelta(days=2), end)
    events_by_id = {ev["espn_event_id"]: ev for ev in events}
    for ev in auburn_days:
        away, home = ev["away"]["name"], ev["home"]["name"]
        if is_auburn_game(away, home):
            events_by_id[ev["espn_event_id"]] = ev
    events = list(events_by_id.values())
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
    out.sort(key=lambda e: (0 if e.get("is_auburn") else 1, e.get("kickoff") or ""))
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
        sat = saturday_from_games(
            [
                {"kickoff": ev.get("kickoff")}
                for ev in event_payloads
            ]
        )
        lock_at = lock_at_for_saturday(sat).isoformat() if sat else None
        conn.execute(
            "UPDATE weeks SET status = ?, lock_at = COALESCE(?, lock_at) WHERE id = ?",
            (status, lock_at, week_id),
        )
    conn.close()
