# 4th Annual Core 10 CFB Pick'em

Python web app (Flask + SQLite). Node.js is not required.

## Run locally

```powershell
python -m pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open [http://127.0.0.1:5050](http://127.0.0.1:5050).

First launch imports `Core 10 2026 Pick'em.xlsx` into `data/pickem.db`.

- Friends open one URL, choose their name, and submit picks.
- Picks lock at each game’s kickoff (once ESPN has a start time).
- Admin: `/admin` with `ADMIN_PIN` (default in `.env.example` is `140Toomer`). Search ESPN, tick 8–10 games, save the slate. Auburn is auto 15 points.
- **Sync scores from ESPN** on the admin desk, or hit `/api/cron/sync-scores?secret=YOUR_CRON_SECRET` on a weekend schedule.

## Scoring

- Each game: 5 points if you pick the winner.
- Auburn game: 15 points.
- Wrong picks score 0.
- Preseason / CFP point values are listed on How it works; those settle later (picks are already imported).

Week 0 Excel “Total” column runs 5 points high for every player. The sheet formula
`=SUMPRODUCT((D2:L2=D$14:L$14)*5)` extends through empty column L, so blank-equals-blank scores as
a correct pick — the Results row shows 45 on a slate that maxes out at 40. The site scores the eight
actual games, so Week 0 reads 30/25/20. Standings order is identical either way.

## Public URL (Render)

Intended service name: **core10-2026cfbpickem**
(apostrophe dropped — URLs cannot include `'`).

Live address after deploy would look like:
`https://core10-2026cfbpickem.onrender.com`

This stack deploys as a Python web service, not Vercel/Node.

1. Push the folder to GitHub.
2. Create a [Render](https://render.com) Web Service from the repo (`render.yaml` is included).
3. Set `ADMIN_PIN`, `FLASK_SECRET_KEY`, and `CRON_SECRET`.
4. Add a Render cron job to `GET /api/cron/sync-scores?secret=...` every few hours on Saturday/Sunday.

SQLite on Render’s free disk is ephemeral unless you attach a persistent disk at `data/`. Attach one, or the database resets on redeploy (you can re-import the spreadsheet from admin if you add that later).
