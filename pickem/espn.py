from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pickem.names import normalize_team, teams_match

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
UA = "Core10PickEm/1.0 (college football pickem; local league tracker)"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_scoreboard(day: date) -> dict:
    qs = urllib.parse.urlencode(
        {
            "dates": day.strftime("%Y%m%d"),
            "groups": "80",
            "limit": "300",
        }
    )
    return _get(f"{SCOREBOARD}?{qs}")


P4_CONFERENCE_IDS = {
    "1": "ACC",
    "4": "Big 12",
    "5": "Big Ten",
    "8": "SEC",
}
P4_NAME_HINTS = (
    "sec",
    "southeastern",
    "acc",
    "atlantic coast",
    "big 12",
    "big12",
    "big twelve",
    "big ten",
    "big10",
    "b1g",
)


def _conference_label(team: dict, competition: dict | None = None) -> str | None:
    cid = str(team.get("conferenceId") or "").strip()
    if cid in P4_CONFERENCE_IDS:
        return P4_CONFERENCE_IDS[cid]
    for group in team.get("groups") or []:
        name = (group.get("shortName") or group.get("name") or "").strip()
        gid = str(group.get("id") or "")
        if gid in P4_CONFERENCE_IDS:
            return P4_CONFERENCE_IDS[gid]
        folded = name.lower()
        for hint in P4_NAME_HINTS:
            if hint in folded:
                if "sec" in folded or "southeastern" in folded:
                    return "SEC"
                if "acc" in folded or "atlantic" in folded:
                    return "ACC"
                if "12" in folded or "twelve" in folded:
                    return "Big 12"
                if "ten" in folded or "10" in folded or "b1g" in folded:
                    return "Big Ten"
    groups = (competition or {}).get("groups")
    if isinstance(groups, dict):
        gid = str(groups.get("id") or "")
        if gid in P4_CONFERENCE_IDS:
            return P4_CONFERENCE_IDS[gid]
    return None


def _is_p4(*labels: str | None) -> bool:
    return any(label in {"SEC", "ACC", "Big 12", "Big Ten"} for label in labels)


def _competitor_payload(comp: dict, competition: dict | None = None) -> dict:
    team = comp.get("team") or {}
    rank = None
    curated = comp.get("curatedRank") or team.get("curatedRank") or {}
    if curated.get("current") not in (None, 99, 0, "99"):
        try:
            rank = int(curated["current"])
        except (TypeError, ValueError):
            rank = None
    records = comp.get("records") or []
    record = records[0]["summary"] if records else None
    score = comp.get("score")
    try:
        score_i = int(score) if score not in (None, "") else None
    except ValueError:
        score_i = None
    return {
        "id": str(team.get("id") or ""),
        "name": team.get("displayName") or team.get("name") or "",
        "short": team.get("shortDisplayName") or team.get("abbreviation") or "",
        "abbr": team.get("abbreviation") or "",
        "logo": (team.get("logo") or (team.get("logos") or [{}])[0].get("href")),
        "rank": rank,
        "home_away": comp.get("homeAway"),
        "winner": bool(comp.get("winner")),
        "score": score_i,
        "record": record,
        "conference": _conference_label(team, competition),
    }


def _odds(competition: dict) -> str | None:
    odds = competition.get("odds") or []
    if not odds:
        return None
    o = odds[0]
    return o.get("details") or o.get("spread")


def parse_event(event: dict) -> dict | None:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competition = competitions[0]
    comps = [_competitor_payload(c, competition) for c in competition.get("competitors") or []]
    home = next((c for c in comps if c["home_away"] == "home"), None)
    away = next((c for c in comps if c["home_away"] == "away"), None)
    if not home or not away:
        return None
    status = (competition.get("status") or {}).get("type") or {}
    state = (status.get("state") or "pre").lower()
    if state == "in" or status.get("name") == "STATUS_HALFTIME":
        game_status = "in_progress"
    elif status.get("completed") or state == "post":
        game_status = "final"
    else:
        game_status = "scheduled"
    winner = None
    if game_status == "final":
        if home["winner"]:
            winner = home["name"]
        elif away["winner"]:
            winner = away["name"]
        elif home.get("score") is not None and away.get("score") is not None:
            if home["score"] > away["score"]:
                winner = home["name"]
            elif away["score"] > home["score"]:
                winner = away["name"]
            # else: tie — leave unset
    kickoff = event.get("date")
    detail = (status.get("detail") or status.get("shortDetail") or "")
    espn_id = str(event.get("id") or "")
    return {
        "espn_event_id": espn_id,
        "espn_url": f"https://www.espn.com/college-football/game/_/gameId/{espn_id}",
        "name": event.get("name") or f"{away['name']} at {home['name']}",
        "short_name": event.get("shortName") or "",
        "away": away,
        "home": home,
        "status": game_status,
        "short_detail": detail,
        "kickoff": kickoff,
        "spread": _odds(competition),
        "neutral": bool(competition.get("neutralSite")),
        "is_p4": _is_p4(away.get("conference"), home.get("conference")),
        "conferences": [c for c in (away.get("conference"), home.get("conference")) if c],
        "is_top25": bool((away.get("rank") and away["rank"] <= 25) or (home.get("rank") and home["rank"] <= 25)),
    }


def scoreboard_events(day: date) -> list[dict]:
    payload = fetch_scoreboard(day)
    out = []
    for event in payload.get("events") or []:
        parsed = parse_event(event)
        if parsed:
            out.append(parsed)
    return out


def collect_events(start: date, end: date) -> list[dict]:
    seen: dict[str, dict] = {}
    day = start
    while day <= end:
        for ev in scoreboard_events(day):
            seen[ev["espn_event_id"]] = ev
        day += timedelta(days=1)
    return list(seen.values())


def match_event(events: list[dict], away: str, home: str) -> dict | None:
    for ev in events:
        if teams_match(away, ev["away"]["name"]) and teams_match(home, ev["home"]["name"]):
            return ev
        if teams_match(away, ev["home"]["name"]) and teams_match(home, ev["away"]["name"]):
            return ev
        # vs. listing may have swapped home/away vs ESPN
        names = {normalize_team(ev["away"]["name"]), normalize_team(ev["home"]["name"])}
        if normalize_team(away) in names and normalize_team(home) in names:
            return ev
    return None


def default_window() -> tuple[date, date]:
    from pickem.scoring import saturday_on_or_after

    sat = saturday_on_or_after(datetime.now(ZoneInfo("America/Chicago")).date())
    return sat, sat
