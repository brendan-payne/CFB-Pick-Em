from __future__ import annotations

from datetime import datetime, timezone

from pickem.names import teams_match


def parse_kickoff(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def game_locked(game: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if game.get("status") in ("in_progress", "final"):
        return True
    kick = parse_kickoff(game.get("kickoff"))
    if kick and now >= kick:
        return True
    return False


def pick_points(game: dict, picked_team: str | None) -> int:
    if game.get("status") != "final" or not game.get("winner") or not picked_team:
        return 0
    if teams_match(picked_team, game["winner"]):
        return int(game.get("point_value") or 5)
    return 0


def week_points_for_player(games: list[dict], picks_by_game: dict[str, str]) -> int:
    total = 0
    for game in games:
        total += pick_points(game, picks_by_game.get(game["id"]))
    return total
