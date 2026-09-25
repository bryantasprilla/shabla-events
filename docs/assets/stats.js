(function () {
  "use strict";

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : String(s);
    return div.innerHTML;
  }

  function pct(v) {
    return v == null ? "—" : Math.round(v * 100) + "%";
  }

  function statusClass(source) {
    if (!source.active) return "status-inactive";
    if (source.last_run_status === "error") return "status-error";
    if (source.last_run_status === "success") return "status-ok";
    return "";
  }

  function statusLabel(source) {
    if (!source.active) return "inactive";
    return source.last_run_status || "no runs yet";
  }

  function row(s) {
    return `
      <tr>
        <td>${escapeHtml(s.source_name)}</td>
        <td>${s.tier}</td>
        <td class="${statusClass(s)}">${escapeHtml(statusLabel(s))}</td>
        <td>${s.last_run_at ? escapeHtml(s.last_run_at) : "—"}</td>
        <td>${s.articles_fetched}</td>
        <td>${s.articles_new_or_changed}</td>
        <td>${s.articles_passed_filter}</td>
        <td>${s.events_confirmed}</td>
        <td>${pct(s.pass_rate)}</td>
        <td>${pct(s.confirm_rate)}</td>
        <td>${s.last_error ? `<span class="status-error" title="${escapeHtml(s.last_error)}">error</span>` : "—"}</td>
      </tr>
    `;
  }

  function render(data) {
    const content = document.getElementById("content");
    const sources = (data.sources || []).slice().sort((a, b) => {
      const ra = a.pass_rate == null ? -1 : a.pass_rate;
      const rb = b.pass_rate == null ? -1 : b.pass_rate;
      return rb - ra;
    });

    content.innerHTML = `
      <div class="overflow-x">
        <table class="stats">
          <thead>
            <tr>
              <th>Source</th><th>Tier</th><th>Status</th><th>Last run</th>
              <th>Fetched</th><th>New</th><th>Passed filter</th><th>Events</th>
              <th>Pass rate</th><th>Confirm rate</th><th>Error</th>
            </tr>
          </thead>
          <tbody>${sources.map(row).join("")}</tbody>
        </table>
      </div>
    `;

    document.getElementById("footer").textContent =
      "Window: last " + data.window_days + " days. Generated " + new Date(data.generated_at).toLocaleString();
  }

  fetch("source_stats.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then(render)
    .catch((err) => {
      document.getElementById("content").innerHTML =
        '<p class="empty-state">Could not load source stats right now.</p>';
      console.error(err);
    });
})();
