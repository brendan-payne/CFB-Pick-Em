from pickem.db import get_conn

c = get_conn()
print("players", c.execute("select count(*) from players").fetchone()[0])
print("w0", c.execute("select count(*) from games where week_id='week-0'").fetchone()[0])
print("w1", c.execute("select count(*) from games where week_id='week-1'").fetchone()[0])
print("picks", c.execute("select count(*) from picks").fetchone()[0])
print("pre", c.execute("select count(*) from preseason_picks").fetchone()[0])
for row in c.execute("select away_team, home_team, point_value from games where week_id='week-1'"):
    print("w1", dict(row))
for row in c.execute("select player_id, auburn_record, national_champion from preseason_picks"):
    print("pre", dict(row))
