from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from pickem.db import get_conn, init_db
from pickem.import_xlsx import import_xlsx
from pickem.queries import league_state
from pickem.scoring import game_locked
from pickem.sync import save_slate, search_espn_games, sync_week_scores

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "core-10-dev-secret")
    app.config["ADMIN_PIN"] = os.environ.get("ADMIN_PIN", "2026")
    app.config["CRON_SECRET"] = os.environ.get("CRON_SECRET", "change-me-cron")

    init_db()
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
    conn.close()
    if n == 0:
        import_xlsx(force=True)

    @app.after_request
    def no_store(resp):
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/")
    def home():
        return render_template("index.html", view="standings")

    @app.get("/week")
    def week():
        return render_template("index.html", view="week")

    @app.get("/picks")
    def picks():
        return render_template("index.html", view="picks")

    @app.get("/season")
    def season():
        return render_template("index.html", view="season")

    @app.get("/rules")
    def rules():
        return render_template("index.html", view="rules")

    @app.get("/admin")
    def admin():
        return render_template("index.html", view="admin", admin=session.get("admin") is True)

    @app.get("/api/state")
    def api_state():
        week_id = request.args.get("week")
        return jsonify(league_state(week_id))

    @app.post("/api/picks")
    def api_picks():
        data = request.get_json(force=True, silent=True) or {}
        player_id = (data.get("playerId") or "").strip()
        picks = data.get("picks") or []
        if not player_id:
            return jsonify({"error": "Choose your name."}), 400
        conn = get_conn()
        player = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
        if not player:
            conn.close()
            return jsonify({"error": "Unknown player."}), 400
        now = datetime.now(timezone.utc)
        saved = 0
        skipped = []
        with conn:
            for item in picks:
                gid = item.get("gameId")
                team = (item.get("team") or "").strip()
                if not gid or not team:
                    continue
                game = conn.execute("SELECT * FROM games WHERE id = ?", (gid,)).fetchone()
                if not game:
                    continue
                game = dict(game)
                if game_locked(game, now):
                    skipped.append(game["label"])
                    continue
                conn.execute(
                    """INSERT INTO picks (player_id, game_id, picked_team, submitted_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(player_id, game_id) DO UPDATE SET
                         picked_team = excluded.picked_team,
                         submitted_at = excluded.submitted_at""",
                    (player_id, gid, team, now.isoformat()),
                )
                saved += 1
        conn.close()
        return jsonify({"ok": True, "saved": saved, "skipped": skipped, "state": league_state()})

    def _require_admin():
        if session.get("admin"):
            return None
        return jsonify({"error": "Admin PIN required."}), 401

    @app.post("/api/admin/login")
    def admin_login():
        data = request.get_json(force=True, silent=True) or {}
        pin = str(data.get("pin") or "")
        if pin != str(app.config["ADMIN_PIN"]):
            return jsonify({"error": "Wrong PIN."}), 403
        session["admin"] = True
        return jsonify({"ok": True})

    @app.post("/api/admin/logout")
    def admin_logout():
        session.pop("admin", None)
        return jsonify({"ok": True})

    @app.post("/api/admin/week-status")
    def admin_week_status():
        denied = _require_admin()
        if denied:
            return denied
        data = request.get_json(force=True, silent=True) or {}
        week_id = data.get("weekId")
        status = data.get("status")
        if status not in ("upcoming", "open", "locked", "final"):
            return jsonify({"error": "Bad status."}), 400
        conn = get_conn()
        with conn:
            conn.execute("UPDATE weeks SET status = ? WHERE id = ?", (status, week_id))
        conn.close()
        return jsonify({"ok": True, "state": league_state()})

    @app.get("/api/admin/espn-search")
    def admin_espn_search():
        denied = _require_admin()
        if denied:
            return denied
        start_s = request.args.get("start")
        end_s = request.args.get("end")
        try:
            start = date.fromisoformat(start_s) if start_s else date.today()
            end = date.fromisoformat(end_s) if end_s else date.today()
        except ValueError:
            return jsonify({"error": "Dates must be YYYY-MM-DD."}), 400
        if (end - start).days > 10:
            return jsonify({"error": "Search a window of 10 days or less."}), 400
        games = search_espn_games(start, end)
        return jsonify({"games": games})

    @app.post("/api/admin/slate")
    def admin_slate():
        denied = _require_admin()
        if denied:
            return denied
        data = request.get_json(force=True, silent=True) or {}
        week_id = data.get("weekId")
        events = data.get("games") or []
        status = data.get("status") or "open"
        if not week_id or not events:
            return jsonify({"error": "Pick a week and at least one game."}), 400
        save_slate(week_id, events, status)
        return jsonify({"ok": True, "state": league_state()})

    @app.post("/api/admin/sync")
    def admin_sync():
        denied = _require_admin()
        if denied:
            return denied
        data = request.get_json(force=True, silent=True) or {}
        result = sync_week_scores(data.get("weekId"))
        return jsonify({"ok": True, **result, "state": league_state()})

    @app.post("/api/admin/reimport")
    def admin_reimport():
        denied = _require_admin()
        if denied:
            return denied
        result = import_xlsx(force=True)
        return jsonify({"ok": True, **result, "state": league_state()})

    @app.get("/api/cron/sync-scores")
    @app.post("/api/cron/sync-scores")
    def cron_sync():
        secret = request.args.get("secret") or request.headers.get("X-Cron-Secret")
        if secret != app.config["CRON_SECRET"]:
            return jsonify({"error": "Unauthorized"}), 401
        result = sync_week_scores()
        return jsonify({"ok": True, **result})

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    return app
