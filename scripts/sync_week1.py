from datetime import date
from pickem.db import get_conn
from pickem.sync import sync_week_scores

print(sync_week_scores("week-1", start=date(2026, 9, 4), end=date(2026, 9, 8)))
conn = get_conn()
for r in conn.execute(
    "SELECT label, winner, status, away_score, home_score FROM games WHERE week_id='week-1' ORDER BY sort_order"
):
    print(dict(r))
