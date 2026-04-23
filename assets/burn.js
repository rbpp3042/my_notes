// claude-burn client-side renderer. Fetches JSON from window.BURN_DATA_URL
// and paints the page. Mirrors what burn.py used to render server-side.

(function () {
  const VERBS = [
    "Burning…", "Smoldering…", "Scorching…", "Torching…",
    "Igniting…", "Blazing…", "Cooking…",
  ];

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function fmtNum(n) {
    return Number(n).toLocaleString("en-US").replace(/,/g, " ");
  }

  function fmtK(n) {
    if (n < 1000) return String(n);
    if (n < 10000) return (n / 1000).toFixed(2).replace(/\.?0+$/, "") + "k";
    if (n < 100000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
    return Math.round(n / 1000) + "k";
  }

  function fmtReset(iso, tz) {
    if (!iso) return "";
    const d = new Date(iso);
    const dt = new Intl.DateTimeFormat("en-US", { timeZone: tz, hour: "numeric", hour12: true });
    const nowParts = new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" })
      .formatToParts(d).reduce((a, p) => (a[p.type] = p.value, a), {});
    const todayParts = new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" })
      .formatToParts(new Date()).reduce((a, p) => (a[p.type] = p.value, a), {});
    const timeStr = dt.format(d).toLowerCase().replace(/\s+/g, "");
    const sameDay = nowParts.year === todayParts.year && nowParts.month === todayParts.month && nowParts.day === todayParts.day;
    if (sameDay) return `Resets ${timeStr} (${tz})`;
    const monthDay = new Intl.DateTimeFormat("en-US", { timeZone: tz, month: "short", day: "numeric" }).format(d);
    return `Resets ${monthDay} at ${timeStr} (${tz})`;
  }

  // ---- block builders (return HTML strings) ----

  function thinkingBlock() {
    return `<div class="thinking">
      <span class="star">✢</span>
      <span class="verb">Burning…</span>
      <span class="meta"> (<span class="elapsed">0s</span> · <span class="tokens"><span class="arr">↑</span> 1.5k <span class="arr">↓</span> 0</span> tokens)</span>
    </div>`;
  }

  function burnBlock(today) {
    const active = Number(today.input || 0) + Number(today.output || 0) + Number(today.cache_write || 0);
    return `<div class="burn">
      <div class="big">${fmtNum(active)}</div>
      <div class="big-sub">tokens burned today</div>
      <div class="breakdown">
        <span>in ${fmtNum(today.input)}</span> ·
        <span>out ${fmtNum(today.output)}</span> ·
        <span>cache write ${fmtNum(today.cache_write)}</span> ·
        <span>cache read ${fmtNum(today.cache_read)}</span>
      </div>
    </div>`;
  }

  function barBlock(title, util, resets_at, tz) {
    util = Math.max(0, Math.min(100, Number(util) || 0));
    const utilStr = Number.isInteger(util) ? String(util) : String(util);
    return `<div class="block">
      <div class="title">${escapeHtml(title)}</div>
      <div class="row">
        <div class="bar"><div class="fill" style="width:${util}%"></div></div>
        <div class="pct">${utilStr}% used</div>
      </div>
      <div class="reset">${escapeHtml(fmtReset(resets_at, tz))}</div>
    </div>`;
  }

  function computeLevel(c, peak) {
    if (c <= 0) return 0;
    const r = c / peak;
    if (r < 0.25) return 1;
    if (r < 0.50) return 2;
    if (r < 0.75) return 3;
    return 4;
  }

  function isoDate(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function localToday(tz) {
    // Compute today's date in the target tz.
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" })
      .formatToParts(new Date()).reduce((a, p) => (a[p.type] = p.value, a), {});
    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  function activityGraph(activity, streaks, tz, opts) {
    const weeks = opts.weeks || 7;
    const countWindow = opts.count_window || 30;
    const day_counts = activity.day_counts || {};

    // Today and window boundaries (work in ISO strings to avoid TZ pitfalls).
    const todayStr = localToday(tz);
    const [ty, tm, td] = todayStr.split("-").map(Number);
    const todayDate = new Date(Date.UTC(ty, tm - 1, td));

    const dow = (todayDate.getUTCDay() + 6) % 7; // Monday=0
    const endDate = new Date(todayDate.getTime() + (6 - dow) * 86400000);
    const totalDays = weeks * 7;
    const startDate = new Date(endDate.getTime() - (totalDays - 1) * 86400000);

    // Collect values within the visible window for peak.
    const values = [];
    for (let i = 0; i < totalDays; i++) {
      const d = new Date(startDate.getTime() + i * 86400000);
      const key = isoDate(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())));
      values.push(Number(day_counts[key] || 0));
    }
    const peak = Math.max(...values, 1);

    // Build cells.
    const cells = [];
    for (let i = 0; i < totalDays; i++) {
      const d = new Date(startDate.getTime() + i * 86400000);
      const key = isoDate(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())));
      const c = values[i];
      const lvl = computeLevel(c, peak);
      const cls = ["cell", "lvl-" + lvl];
      if (key === todayStr) cls.push("today");
      else if (key > todayStr) cls.push("future");
      cells.push(`<div class="${cls.join(" ")}" title="${key} — ${fmtNum(c)} msgs"></div>`);
    }

    // Active-day counter over last N days.
    let active = 0;
    const windowStart = new Date(todayDate.getTime() - (countWindow - 1) * 86400000);
    for (let i = 0; i < countWindow; i++) {
      const d = new Date(windowStart.getTime() + i * 86400000);
      const key = isoDate(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())));
      if ((day_counts[key] || 0) > 0) active++;
    }

    const cur = (streaks && streaks.current) || 0;
    const lng = (streaks && streaks.longest) || 0;

    return `<div class="block block-activity">
      <div class="title">Last ${countWindow} days — ${active}/${countWindow} days active</div>
      <div class="streaks">current streak <b>${cur}</b> days · longest <b>${lng}</b> days</div>
      <div class="agraph">${cells.join("")}</div>
    </div>`;
  }

  // ---- thinking widget animation ----

  function initThinkingWidget() {
    const el = document.querySelector(".thinking");
    if (!el) return;
    const verbEl = el.querySelector(".verb");
    const elapsedEl = el.querySelector(".elapsed");
    const tokenEl = el.querySelector(".tokens");
    const t0 = Date.now();

    function render(inp, out) {
      tokenEl.innerHTML =
        '<span class="arr">↑</span> ' + fmtK(inp) +
        ' <span class="arr">↓</span> ' + fmtK(out);
    }

    let vi = 0;
    setInterval(() => {
      vi = (vi + 1) % VERBS.length;
      verbEl.textContent = VERBS[vi];
    }, 5000);

    setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000);
      elapsedEl.textContent = s < 60 ? s + "s" : Math.floor(s / 60) + "m " + (s % 60) + "s";
    }, 1000);

    const LIMIT = 200000;
    let turnInput = 0, turnDur = 0, idle = false;
    let currentOut = 0, lastEmit = 0, pauseUntil = 0, outGoal = 0;

    function newTurn() {
      turnInput = 1500 + Math.floor(Math.random() * 6500);
      turnDur = 180000 + Math.random() * 240000;
      outGoal = LIMIT - turnInput;
      currentOut = 0;
      lastEmit = performance.now();
      pauseUntil = 0;
      idle = false;
      render(turnInput, 0);
    }
    newTurn();

    function tick(now) {
      if (!idle && now >= pauseUntil) {
        const gap = 120 + Math.random() * 400;
        if (now - lastEmit >= gap) {
          const elapsed = now - lastEmit;
          lastEmit = now;
          const baseRate = outGoal / turnDur;
          let jitter = 0.2 + Math.random() * 2.0;
          if (Math.random() < 0.08) jitter *= 3;
          const chunk = Math.max(1, Math.floor(baseRate * elapsed * jitter));
          currentOut += chunk;
          if (Math.random() < 0.15) pauseUntil = now + (800 + Math.random() * 3500);
        }
        if (currentOut >= outGoal) {
          currentOut = outGoal;
          idle = true;
          setTimeout(newTurn, 1500 + Math.random() * 2500);
        }
        render(turnInput, currentOut);
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ---- main ----

  async function main() {
    const url = window.BURN_DATA_URL;
    const content = document.getElementById("content");
    const updatedEl = document.getElementById("updated");

    let data;
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      data = await res.json();
    } catch (err) {
      content.innerHTML = '<div class="err">error loading data: ' + escapeHtml(String(err && err.message ? err.message : err)) + '</div>';
      return;
    }

    const tz = data.tz || "UTC";
    const parts = [];
    if (data.today) parts.push(burnBlock(data.today));
    if (data.usage) {
      if (data.usage.five_hour) {
        parts.push(barBlock("Current session", data.usage.five_hour.utilization, data.usage.five_hour.resets_at, tz));
      }
      if (data.usage.seven_day) {
        parts.push(barBlock("Current week (all models)", data.usage.seven_day.utilization, data.usage.seven_day.resets_at, tz));
      }
    }
    if (data.activity) {
      parts.push(activityGraph(data.activity, data.streaks, tz, { weeks: 7, count_window: 30 }));
    }
    parts.push(thinkingBlock());
    content.innerHTML = parts.join("");

    if (data.updated_at && updatedEl) {
      try {
        const d = new Date(data.updated_at);
        const time = new Intl.DateTimeFormat("en-GB", {
          timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
        }).format(d);
        const date = new Intl.DateTimeFormat("en-GB", {
          timeZone: tz, day: "numeric", month: "short",
        }).format(d).toLowerCase();
        updatedEl.textContent = `${time} · ${date}`;
      } catch {
        updatedEl.textContent = "—";
      }
    }

    initThinkingWidget();
  }

  main();
})();
