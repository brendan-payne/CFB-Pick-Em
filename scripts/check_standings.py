from pickem.db import get_conn
from pickem.import_xlsx import _standings_snapshot

conn = get_conn()
print("Week 1 games:")
for r in conn.execute(
    "SELECT label, winner, status, away_score, home_score FROM games WHERE week_id='week-1' ORDER BY sort_order"
):
    print(dict(r))
print("\nStandings:")
for row in _standings_snapshot():
    print(row["player"], row["weekly"].get("week-0"), row["weekly"].get("week-1"), row["total"])
print("\nWeeks:")
for r in conn.execute("SELECT id, status FROM weeks WHERE id LIKE 'week-%' ORDER BY sort_order LIMIT 5"):
    print(dict(r))
