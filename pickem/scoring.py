from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pickem.names import teams_match

CT = ZoneInfo("America/Chicago")


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


def saturday_on_or_after(day: date) -> date:
    # Monday=0 … Saturday=5. If it's Saturday, keep it.
    return day + timedelta(days=(5 - day.weekday()) % 7)


def next_gameday_saturday(now: datetime | None = None) -> date:
    now = now or datetime.now(CT)
    return saturday_on_or_after(now.date())


def lock_at_for_saturday(sat: date) -> datetime:
    return datetime(sat.year, sat.month, sat.day, 11, 0, tzinfo=CT)


def saturday_from_games(games: list[dict]) -> date | None:
    dates = []
    for game in games:
        kick = parse_kickoff(game.get("kickoff"))
        if kick:
            dates.append(kick.astimezone(CT).date())
    if not dates:
        return None
    # The Saturday of that football weekend (the Saturday on/after the earliest game).
    return saturday_on_or_after(min(dates))


def week_lock_at(week: dict | None, games: list[dict] | None = None) -> datetime | None:
    if week and week.get("lock_at"):
        return parse_kickoff(week["lock_at"])
    sat = saturday_from_games(games or [])
    if sat:
        return lock_at_for_saturday(sat)
    return None


def week_picks_locked(week: dict | None, games: list[dict] | None = None, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if week and week.get("status") in ("locked", "final"):
        return True
    lock_at = week_lock_at(week, games)
    if lock_at and now >= lock_at:
        return True
    return False


def game_locked(game: dict, now: datetime | None = None, week: dict | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if game.get("status") in ("in_progress", "final"):
        return True
    if week_picks_locked(week, [game], now):
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
