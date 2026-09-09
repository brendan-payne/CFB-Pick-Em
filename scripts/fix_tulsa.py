from datetime import date
from pickem.db import get_conn
from pickem.import_xlsx import _standings_snapshot
from pickem.sync import sync_week_scores

print(sync_week_scores("week-1", start=date(2026, 9, 4), end=date(2026, 9, 8)))
# Safety net: if scores exist but winner is blank, infer it.
conn = get_conn()
with conn:
    conn.execute(
        """UPDATE games
           SET winner = home_team
           WHERE week_id = 'week-1'
             AND winner IS NULL
             AND away_score IS NOT NULL
             AND home_score IS NOT NULL
             AND home_score > away_score"""
    )
    conn.execute(
        """UPDATE games
           SET winner = away_team
           WHERE week_id = 'week-1'
             AND winner IS NULL
             AND away_score IS NOT NULL
             AND home_score IS NOT NULL
             AND away_score > home_score"""
    )
for r in conn.execute(
    "SELECT label, winner, away_score, home_score FROM games WHERE week_id='week-1' ORDER BY sort_order"
):
    print(dict(r))
print("---")
for row in _standings_snapshot():
    print(row["player"], row["weekly"].get("week-0"), row["weekly"].get("week-1"), "=>", row["total"])
