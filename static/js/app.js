(function () {
  const view = document.body.dataset.view || "standings";
  let state = null;
  const selectedEspn = new Map();

  document.querySelectorAll(".nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === view);
  });
  document.querySelectorAll(".view").forEach((el) => {
    el.classList.toggle("active", el.id === `view-${view}`);
  });

  const $ = (id) => document.getElementById(id);

  function logoUrl(game, side) {
    const url = side === "away" ? game.away_logo : game.home_logo;
    if (url) return url;
    const id = side === "away" ? game.away_espn_id : game.home_espn_id;
    if (id) return `https://a.espncdn.com/i/teamlogos/ncaa/500/${id}.png`;
    return "";
  }

  function rank(n) {
    return n ? `#${n}` : "";
  }

  function weekLabel(id) {
    const w = (state.weeks || []).find((x) => x.id === id);
    return w ? w.label : id;
  }

  function gamesFor(weekId) {
    return (state.games || []).filter((g) => g.week_id === weekId);
  }

  function currentWeekId() {
    const sel = $("week-select");
    if (sel && sel.value) return sel.value;
    return state.currentWeekId;
  }

  function fillWeekSelects() {
    const weeks = state.weeks || [];
    ["week-select", "season-week-select", "admin-week"].forEach((id) => {
      const sel = $(id);
      if (!sel) return;
      const prev = sel.value;
      sel.innerHTML = weeks
        .map(
          (w) =>
            `<option value="${w.id}">${w.label} (${w.status})</option>`
        )
        .join("");
      sel.value = prev || state.currentWeekId;
    });
  }

  function renderHero() {
    const week = (state.weeks || []).find((w) => w.id === state.currentWeekId);
    const games = gamesFor(state.currentWeekId);
    const leader = (state.standings || [])[0];
    $("hero-title").textContent = week ? week.label : "Core 10";
    $("hero-meta").innerHTML = `
      <div>${games.length} games on the slate</div>
      <div>Leader: ${leader ? leader.name + " · " + leader.total + " pts" : "—"}</div>`;
  }

  function renderStandings() {
    const weeks = state.weeks || [];
    const shown = weeks.filter((w) =>
      (state.games || []).some((g) => g.week_id === w.id)
    );
    const thead = document.querySelector("#standings-table thead");
    const tbody = document.querySelector("#standings-table tbody");
    thead.innerHTML = `<tr><th>#</th><th>Name</th>${shown
      .map((w) => `<th title="${w.label}">${w.label.replace("Week ", "W")}</th>`)
      .join("")}<th>Total</th></tr>`;
    tbody.innerHTML = (state.standings || [])
      .map(
        (row) => `<tr>
          <td>${row.rank}</td>
          <td>${row.name}</td>
          ${shown.map((w) => `<td>${row.weekly[w.id] || 0}</td>`).join("")}
          <td><strong>${row.total}</strong></td>
        </tr>`
      )
      .join("");

    const cards = $("standings-cards");
    cards.innerHTML = (state.standings || [])
      .map((row) => {
        const detail = shown
          .map((w) => {
            const gs = gamesFor(w.id);
            const rows = gs
              .map((g) => {
                const pick = (row.picks || []).find((p) => p.game_id === g.id);
                const got = pick && g.status === "final" && g.winner && pick.picked_team
                  ? (g.winner.toLowerCase().includes(pick.picked_team.toLowerCase()) ||
                      pick.picked_team.toLowerCase().includes(String(g.winner).toLowerCase())
                      ? g.point_value
                      : 0)
                  : "—";
                return `<tr><td>${g.label}</td><td>${pick ? pick.picked_team : "—"}</td><td>${g.winner || "—"}</td><td>${got}</td></tr>`;
              })
              .join("");
            return `<h3>${w.label} · ${row.weekly[w.id] || 0} pts</h3>
              <table class="board"><thead><tr><th>Game</th><th>Pick</th><th>Winner</th><th>Pts</th></tr></thead><tbody>${rows}</tbody></table>`;
          })
          .join("");
        return `<article class="entry-card">
          <button class="entry-summary" type="button">
            <div class="rank-pip">${row.rank}</div>
            <div>
              <div class="team-name">${row.name}</div>
              <div class="muted">Tap to open weekly cards</div>
            </div>
            <div class="points">${row.total}<span>PTS</span></div>
          </button>
          <div class="roster">${detail}</div>
        </article>`;
      })
      .join("");
    cards.querySelectorAll(".entry-summary").forEach((btn) => {
      btn.addEventListener("click", () => btn.parentElement.classList.toggle("open"));
    });
  }

  function matchupCard(game, opts) {
    const { selectable, playerId } = opts || {};
    const pick = playerId
      ? (state.picks || []).find((p) => p.player_id === playerId && p.game_id === game.id)
      : null;
    const selected = pick ? pick.picked_team : "";
    const locked = !!game.locked;
    const score =
      game.away_score != null && game.home_score != null
        ? `<div class="scoreline">${game.away_score} – ${game.home_score}</div>`
        : "";
    const side = (team, which) => {
      const isSel = selected && (selected === team || selected.toLowerCase() === String(team).toLowerCase());
      const inner = `
        <div class="helmet">${logoUrl(game, which) ? `<img alt="" src="${logoUrl(game, which)}" />` : team.slice(0, 3)}</div>
        <div class="rank-chip">${rank(which === "away" ? game.away_rank : game.home_rank)}</div>
        <div class="team-name">${team}</div>`;
      if (!selectable) return inner;
      return `<button type="button" data-game="${game.id}" data-team="${team}" class="${isSel ? "selected" : ""}" ${locked ? "disabled" : ""}>${inner}</button>`;
    };
    return `<article class="matchup ${game.is_auburn ? "auburn" : ""}">
      <div class="side">${side(game.away_team, "away")}</div>
      <div class="mid">
        <div class="badge ${game.is_auburn ? "auburn" : ""}">${game.point_value} PTS</div>
        <div>${game.spread || "vs"}</div>
        ${score}
        <div>${game.short_detail || game.status}</div>
      </div>
      <div class="side">${side(game.home_team, "home")}</div>
    </article>`;
  }

  function renderWeek() {
    const weekId = $("week-select").value || state.currentWeekId;
    const games = gamesFor(weekId);
    $("week-lede").textContent = `${games.length} games · ${weekLabel(weekId)}`;
    $("matchups").innerHTML = games.map((g) => matchupCard(g, { selectable: false })).join("") || "<p class='muted'>No games on this slate yet.</p>";
  }

  function renderPicks() {
    const sel = $("player-select");
    const current = sel.value;
    sel.innerHTML =
      `<option value="">Select…</option>` +
      (state.players || []).map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
    sel.value = current;
    const weekId = state.currentWeekId;
    const games = gamesFor(weekId).filter((g) => {
      const w = state.weeks.find((x) => x.id === g.week_id);
      return w && (w.status === "open" || w.status === "locked" || w.status === "final");
    });
    const openGames = gamesFor(weekId);
    $("picks-matchups").innerHTML = openGames.map((g) => matchupCard(g, { selectable: true, playerId: sel.value })).join("");
    $("picks-matchups").querySelectorAll("button[data-game]").forEach((btn) => {
      btn.addEventListener("click", () => {
        $("picks-matchups")
          .querySelectorAll(`button[data-game="${btn.dataset.game}"]`)
          .forEach((b) => b.classList.remove("selected"));
        btn.classList.add("selected");
      });
    });
    const submitted = (state.players || []).map((p) => {
      const n = openGames.filter((g) =>
        (state.picks || []).some((x) => x.player_id === p.id && x.game_id === g.id)
      ).length;
      return `${p.name} ${n}/${openGames.length}`;
    });
    $("submitted-note").textContent = openGames.length ? `Cards in: ${submitted.join(" · ")}` : "";
  }

  function renderSeason() {
    const weekId = $("season-week-select").value || state.currentWeekId;
    const games = gamesFor(weekId);
    $("consensus").innerHTML = games
      .map((g) => {
        const related = (state.picks || []).filter((p) => p.game_id === g.id);
        const counts = {};
        related.forEach((p) => {
          counts[p.picked_team] = (counts[p.picked_team] || 0) + 1;
        });
        const bars = Object.entries(counts)
          .sort((a, b) => b[1] - a[1])
          .map(([team, n]) => {
            const pct = related.length ? Math.round((n / related.length) * 100) : 0;
            return `<div>${team} · ${n} (${pct}%)<div class="bar"><span style="width:${pct}%"></span></div></div>`;
          })
          .join("");
        return `<article class="rule-card"><h3>${g.label}</h3>${bars || "<p class='muted'>No picks yet.</p>"}</article>`;
      })
      .join("");

    $("preseason").innerHTML = (state.preseason || [])
      .map((p) => {
        const player = (state.players || []).find((x) => x.id === p.player_id);
        return `<article class="pre-card">
          <h3>${player ? player.name : p.player_id}</h3>
          <p>Auburn record: <strong>${p.auburn_record || "—"}</strong></p>
          <p>B1G ${p.big10 || "—"} · Big 12 ${p.big12 || "—"} · ACC ${p.acc || "—"} · SEC ${p.sec || "—"}</p>
          <p>Playoff: ${(p.playoff_teams || []).join(", ")}</p>
          <p>Natty: <strong>${p.national_champion || "—"}</strong></p>
        </article>`;
      })
      .join("");
  }

  function renderAdmin() {
    const unlocked = document.body.dataset.admin === "1";
    $("admin-login").classList.toggle("hidden", unlocked);
    $("admin-desk").classList.toggle("hidden", !unlocked);
    if ($("admin-week").value) {
      const w = (state.weeks || []).find((x) => x.id === $("admin-week").value);
      if (w) $("admin-status").value = w.status;
    }
  }

  function renderAll() {
    fillWeekSelects();
    renderHero();
    renderStandings();
    if ($("week-select")) renderWeek();
    renderPicks();
    renderSeason();
    renderAdmin();
  }

  async function loadState() {
    const res = await fetch("/api/state");
    state = await res.json();
    renderAll();
  }

  $("week-select")?.addEventListener("change", renderWeek);
  $("season-week-select")?.addEventListener("change", renderSeason);
  $("player-select")?.addEventListener("change", renderPicks);

  $("picks-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const playerId = $("player-select").value;
    const err = $("picks-errors");
    err.textContent = "";
    if (!playerId) {
      err.textContent = "Choose your name first.";
      return;
    }
    const picks = [...$("picks-matchups").querySelectorAll("button.selected")].map((btn) => ({
      gameId: btn.dataset.game,
      team: btn.dataset.team,
    }));
    const res = await fetch("/api/picks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playerId, picks }),
    });
    const data = await res.json();
    if (!res.ok) {
      err.textContent = data.error || "Could not save.";
      return;
    }
    state = data.state;
    renderAll();
    err.textContent = data.skipped?.length
      ? `Saved ${data.saved}. Locked (skipped): ${data.skipped.join(", ")}`
      : `Saved ${data.saved} picks.`;
  });

  $("admin-login")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: $("admin-pin").value }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("admin-login-error").textContent = data.error || "Nope.";
      return;
    }
    document.body.dataset.admin = "1";
    renderAdmin();
  });

  $("logout-btn")?.addEventListener("click", async () => {
    await fetch("/api/admin/logout", { method: "POST" });
    document.body.dataset.admin = "0";
    renderAdmin();
  });

  $("status-btn")?.addEventListener("click", async () => {
    const res = await fetch("/api/admin/week-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weekId: $("admin-week").value, status: $("admin-status").value }),
    });
    const data = await res.json();
    if (data.state) {
      state = data.state;
      renderAll();
    }
  });

  $("sync-btn")?.addEventListener("click", async () => {
    $("sync-status").textContent = "Syncing…";
    const res = await fetch("/api/admin/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weekId: $("admin-week").value }),
    });
    const data = await res.json();
    $("sync-status").textContent = res.ok
      ? `Matched ${data.matched} of ESPN events (${data.events} on the board).`
      : data.error || "Sync failed.";
    if (data.state) {
      state = data.state;
      renderAll();
    }
  });

  $("search-btn")?.addEventListener("click", async () => {
    $("search-status").textContent = "Searching ESPN…";
    const start = $("espn-start").value;
    const end = $("espn-end").value;
    const res = await fetch(`/api/admin/espn-search?start=${start}&end=${end}`);
    const data = await res.json();
    if (!res.ok) {
      $("search-status").textContent = data.error || "Search failed.";
      return;
    }
    selectedEspn.clear();
    $("search-status").textContent = `${(data.games || []).length} games found.`;
    $("espn-results").innerHTML = (data.games || [])
      .map((g) => {
        const id = g.espn_event_id;
        const label = `${g.away.name} @ ${g.home.name}`;
        const extra = [g.spread, g.short_detail, g.is_auburn ? "AUBURN 15" : "5 pts"]
          .filter(Boolean)
          .join(" · ");
        return `<label class="espn-item">
          <input type="checkbox" data-eid="${id}" />
          <span><strong>${label}</strong><br /><span class="muted">${extra}</span></span>
          <a href="${g.espn_url}" target="_blank" rel="noopener">ESPN</a>
        </label>`;
      })
      .join("");
    $("espn-results").querySelectorAll("input[type=checkbox]").forEach((box) => {
      box.addEventListener("change", () => {
        const g = data.games.find((x) => x.espn_event_id === box.dataset.eid);
        if (box.checked) selectedEspn.set(box.dataset.eid, g);
        else selectedEspn.delete(box.dataset.eid);
      });
    });
  });

  $("save-slate-btn")?.addEventListener("click", async () => {
    const games = [...selectedEspn.values()];
    $("search-status").textContent = "Saving slate…";
    const res = await fetch("/api/admin/slate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        weekId: $("admin-week").value,
        status: $("admin-status").value || "open",
        games,
      }),
    });
    const data = await res.json();
    $("search-status").textContent = res.ok ? `Saved ${games.length} games.` : data.error || "Save failed.";
    if (data.state) {
      state = data.state;
      renderAll();
    }
  });

  const today = new Date();
  const iso = (d) => d.toISOString().slice(0, 10);
  if ($("espn-start")) {
    const start = new Date(today);
    start.setDate(start.getDate() - 1);
    const end = new Date(today);
    end.setDate(end.getDate() + 6);
    $("espn-start").value = iso(start);
    $("espn-end").value = iso(end);
  }

  loadState();
  setInterval(loadState, 45000);
})();
