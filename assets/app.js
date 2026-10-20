(function () {
  "use strict";
  var REPO = "suhasdasari/hackathon-afterlife";
  var LABEL = { active: "Active (≤30d)", recent: "Recent (31–90d)", site_only: "Site up only", quiet: "Quiet", unknown: "Insufficient data", graduated: "Graduated" };
  var CP = { active: "✓ active", no_activity: "no public commits", pending: "pending", unknown: "unknown" };
  var COLORS = ["#58a6ff", "#3fb950", "#f0883e", "#d2a8ff", "#ff7b72", "#e3b341", "#39c5cf", "#a5d6ff", "#ffa198", "#7ee787", "#bc8cff", "#ffd33d", "#79c0ff"];
  var DATA, P;

  function el(tag, attrs, html) { var e = document.createElement(tag); for (var k in attrs || {}) e.setAttribute(k, attrs[k]); if (html != null) e.innerHTML = html; return e; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function d10(s) { return s ? s.slice(0, 10) : ""; }
  function daysAgo(s) { return s ? Math.floor((Date.parse(DATA.generated_at) - Date.parse(s)) / 864e5) : null; }
  function pct(a, b) { return b ? Math.round(100 * a / b) + "%" : "–"; }

  fetch("data/projects.json", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
    DATA = d; P = d.projects;
    document.getElementById("stamp").textContent = "Data as of " + d.generated_at.replace("T", " ").replace("+00:00", " UTC") +
      " · " + P.length + " projects · X snapshot: " + (d.x_snapshot_as_of || "none") + " · refreshed nightly";
    kpis(); checkpoints(); filters(); table(); km();
    document.getElementById("groupBy").onchange = km;
  }).catch(function (e) { document.getElementById("stamp").textContent = "Could not load data/projects.json: " + e; });

  function kpis() {
    var withRepo = P.filter(function (p) { return p.signals.github.status === "checked"; });
    var c = {}; P.forEach(function (p) { c[p.status] = (c[p.status] || 0) + 1; });
    var r30 = withRepo.filter(function (p) { return p.checkpoints["30"] === "active" || p.checkpoints["30"] === "no_activity"; });
    var a30 = r30.filter(function (p) { return p.checkpoints["30"] === "active"; });
    var anySignal = P.filter(function (p) { return p.status !== "unknown"; });
    var items = [
      [P.length, "projects tracked"],
      [withRepo.length, "with a reachable public repo"],
      [pct(c.active || 0, anySignal.length), "active in last 30 days (of " + anySignal.length + " with ≥1 checkable signal)"],
      [pct(a30.length, r30.length), "still committing at day 30 (n=" + r30.length + ")"],
      [c.unknown || 0, "with insufficient public data"]
    ];
    var box = document.getElementById("kpis");
    items.forEach(function (i) { box.appendChild(el("div", { "class": "kpi" }, "<b>" + i[0] + "</b><span>" + esc(i[1]) + "</span>")); });
  }

  function checkpoints() {
    var groups = {};
    P.forEach(function (p) { (groups[p.hackathon] = groups[p.hackathon] || []).push(p); });
    var keys = Object.keys(groups).sort();
    var h = "<tr><th>Hackathon</th><th>Demo day</th><th>Projects</th><th>Public repo</th><th>Day 30</th><th>Day 90</th><th>Day 180</th><th>Active now (any signal)</th></tr>";
    function cell(arr, n) {
      var reached = arr.filter(function (p) { var c = p.checkpoints[n]; return c === "active" || c === "no_activity"; });
      if (!reached.length) {
        return arr.some(function (p) { return p.checkpoints[n] === "pending"; }) ? '<span class="c-pending">pending</span>' : '<span class="c-unknown">–</span>';
      }
      var a = reached.filter(function (p) { return p.checkpoints[n] === "active"; }).length;
      return pct(a, reached.length) + ' <span class="small">(' + a + "/" + reached.length + ")</span>";
    }
    keys.forEach(function (k) {
      var a = groups[k], known = a.filter(function (p) { return p.status !== "unknown"; });
      var act = a.filter(function (p) { return p.status === "active"; }).length;
      h += "<tr><td>" + esc(k) + "</td><td>" + esc(a[0].demo_day) + "</td><td>" + a.length + "</td><td>" +
        a.filter(function (p) { return p.signals.github.status === "checked"; }).length + "</td><td>" + cell(a, "30") + "</td><td>" + cell(a, "90") +
        "</td><td>" + cell(a, "180") + "</td><td>" + pct(act, known.length) + ' <span class="small">(' + act + "/" + known.length + ")</span></td></tr>";
    });
    document.getElementById("cp").innerHTML = h;
  }

  function filters() {
    var orgs = {}, st = {};
    P.forEach(function (p) { orgs[p.organizer] = 1; st[p.status] = 1; });
    Object.keys(orgs).sort().forEach(function (o) { document.getElementById("fOrg").appendChild(el("option", { value: o }, esc(o))); });
    Object.keys(LABEL).forEach(function (s) { if (st[s]) document.getElementById("fStatus").appendChild(el("option", { value: s }, LABEL[s])); });
    ["q", "fOrg", "fStatus"].forEach(function (id) { document.getElementById(id).oninput = table; });
  }

  function claimUrl(p) {
    var body = "**Project:** " + p.name + "\n**Hackathon:** " + p.hackathon + " (" + p.placing + ")\n**Current label:** " + (LABEL[p.status] || p.status) +
      " — " + p.status_reason + "\n**Data as of:** " + DATA.generated_at + "\n\n" +
      "I am on the team / have a correction. Please add or fix (link evidence for each):\n" +
      "- [ ] Public repo URL: \n- [ ] Website: \n- [ ] Project X account: \n- [ ] Contract / program address: \n- [ ] Token address: \n- [ ] Announced raise (source link): \n- [ ] Other: \n";
    return "https://github.com/" + REPO + "/issues/new?labels=correction&title=" + encodeURIComponent("Claim/correct: " + p.name) + "&body=" + encodeURIComponent(body);
  }

  function sig(p) {
    var g = p.signals.github, s = p.signals.site, x = p.signals.x, out = [];
    if (g.status === "checked") {
      var la = daysAgo(g.last_commit);
      out.push('<a href="' + esc(g.repo) + '" target="_blank" rel="noopener">GitHub</a>: ' + (g.last_commit ? "last commit " + d10(g.last_commit) + " (" + la + "d ago), " + g.commits_last_30d + " in last 30d" : "no commits"));
    } else out.push("GitHub: <i>unknown</i>" + (g.note ? ' <span class="small">(' + esc(g.note.split(":")[0]) + ")</span>" : ""));
    if (s.status === "unknown") out.push("Site: <i>unknown</i>" + (s.url ? ' <span class="small">(<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.note || "") + "</a>)</span>" : ""));
    else out.push('Site: <a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.status) + "</a>" + (s.http ? " (" + s.http + ")" : " (no response)"));
    if (x.status === "checked") out.push('X <a href="https://x.com/' + esc(x.handle) + '" target="_blank" rel="noopener">@' + esc(x.handle) + "</a>: " + (x.last_post ? 'last post <a href="' + esc(x.post_url || "#") + '" target="_blank" rel="noopener">' + d10(x.last_post) + "</a> (" + daysAgo(x.last_post) + "d ago)" : "no posts"));
    else out.push("X: <i>unknown</i>" + (x.handle ? " (@" + esc(x.handle) + ")" : ""));
    out.push("Token: <i>" + (p.signals.token.status === "checked" ? (p.signals.token.exists ? "listed" : "none found") : "unknown") + "</i> · Raise: <i>" + esc(p.signals.raise.status) + "</i>");
    return out.join("<br>");
  }

  var sortKey = "days_since_demo", sortDir = 1;
  function table() {
    var q = document.getElementById("q").value.toLowerCase(), fo = document.getElementById("fOrg").value, fs = document.getElementById("fStatus").value;
    var rows = P.filter(function (p) { return (!q || p.name.toLowerCase().indexOf(q) >= 0 || p.hackathon.toLowerCase().indexOf(q) >= 0) && (!fo || p.organizer === fo) && (!fs || p.status === fs); });
    rows.sort(function (a, b) { var x = a[sortKey], y = b[sortKey]; return (x > y ? 1 : x < y ? -1 : 0) * sortDir; });
    var cols = [["name", "Project"], ["hackathon", "Hackathon · placing"], ["segment", "Track"], ["days_since_demo", "Demo day"], ["status", "Status"], [null, "30d"], [null, "90d"], [null, "180d"], [null, "Evidence"], [null, ""]];
    var h = "<tr>" + cols.map(function (c) { return "<th" + (c[0] ? ' data-k="' + c[0] + '"' : "") + ">" + c[1] + (c[0] === sortKey ? (sortDir > 0 ? " ▲" : " ▼") : "") + "</th>"; }).join("") + "</tr>";
    rows.forEach(function (p) {
      h += "<tr><td><b>" + esc(p.name) + '</b><br><a class="small" href="' + esc(p.listing_url || p.source_url) + '" target="_blank" rel="noopener">source</a></td>' +
        "<td>" + esc(p.hackathon) + '<br><span class="small">' + esc(p.placing) + " · " + esc(p.track) + "</span></td><td>" + esc(p.segment) + "</td>" +
        "<td>" + esc(p.demo_day) + '<br><span class="small">' + p.days_since_demo + "d ago</span></td>" +
        '<td><span class="pill s-' + p.status + '">' + LABEL[p.status] + '</span><br><span class="small">' + esc(p.status_reason) + "</span></td>" +
        ["30", "90", "180"].map(function (n) { var c = p.checkpoints[n]; return '<td class="c-' + c + '">' + CP[c] + "</td>"; }).join("") +
        "<td>" + sig(p) + '</td><td><a class="small" href="' + claimUrl(p) + '" target="_blank" rel="noopener">claim / correct</a></td></tr>';
    });
    var t = document.getElementById("projects"); t.innerHTML = h;
    Array.prototype.forEach.call(t.querySelectorAll("th[data-k]"), function (th) {
      th.onclick = function () { var k = th.getAttribute("data-k"); if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = 1; } table(); };
    });
  }

  // Kaplan-Meier, inline SVG (no external libraries)
  function kmCurve(obs) {
    obs = obs.slice().sort(function (a, b) { return a.t - b.t || b.event - a.event; });
    var n = obs.length, s = 1, pts = [[0, 1]], i = 0;
    while (i < obs.length) {
      var t = obs[i].t, d = 0, c = 0;
      while (i < obs.length && obs[i].t === t) { if (obs[i].event) d++; else c++; i++; }
      if (d) { pts.push([t, s]); s = s * (1 - d / n); pts.push([t, s]); }
      n -= d + c;
    }
    pts.push([obs.length ? obs[obs.length - 1].t : 0, s]);
    return pts;
  }
  function km() {
    var key = document.getElementById("groupBy").value, groups = {};
    P.forEach(function (p) { if (p.survival) (groups[p[key]] = groups[p[key]] || []).push(p.survival); });
    var W = 900, H = 360, L = 50, R = 20, T = 15, B = 40, maxT = 180;
    var X = function (t) { return L + (W - L - R) * Math.min(t, maxT) / maxT; }, Y = function (s) { return T + (H - T - B) * (1 - s); };
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Survival curves">';
    for (var g = 0; g <= 1.0001; g += 0.25) svg += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(g) + '" y2="' + Y(g) + '" stroke="#30363d"/><text x="' + (L - 8) + '" y="' + (Y(g) + 4) + '" fill="#8b949e" font-size="11" text-anchor="end">' + Math.round(g * 100) + "%</text>";
    [0, 30, 60, 90, 120, 150, 180].forEach(function (t) { svg += '<line x1="' + X(t) + '" x2="' + X(t) + '" y1="' + T + '" y2="' + (H - B) + '" stroke="' + (t % 90 === 30 || t === 180 ? "#444c56" : "#21262d") + '"/><text x="' + X(t) + '" y="' + (H - B + 16) + '" fill="#8b949e" font-size="11" text-anchor="middle">' + t + "d</text>"; });
    svg += '<text x="' + (W / 2) + '" y="' + (H - 5) + '" fill="#8b949e" font-size="12" text-anchor="middle">days since demo day</text>';
    var leg = "", i = 0;
    Object.keys(groups).sort().forEach(function (k) {
      var obs = groups[k], col = COLORS[i++ % COLORS.length], pts = kmCurve(obs);
      svg += '<polyline fill="none" stroke="' + col + '" stroke-width="2.2" points="' + pts.map(function (p) { return X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1); }).join(" ") + '"/>';
      obs.forEach(function (o) { if (!o.event) { var s = 1; pts.forEach(function (p) { if (p[0] <= o.t) s = p[1]; }); svg += '<line x1="' + X(o.t) + '" x2="' + X(o.t) + '" y1="' + (Y(s) - 4) + '" y2="' + (Y(s) + 4) + '" stroke="' + col + '"/>'; } });
      leg += '<span><i style="background:' + col + '"></i>' + esc(k) + " (n=" + obs.length + ")</span>";
    });
    if (!i) svg += '<text x="' + W / 2 + '" y="' + H / 2 + '" fill="#8b949e" text-anchor="middle">No projects with a public repo in this grouping yet</text>';
    document.getElementById("km").innerHTML = svg + "</svg>";
    document.getElementById("kmLegend").innerHTML = leg + '<span class="small">Tick marks = still committing (censored). Groups with no public repos are omitted.</span>';
  }
})();
