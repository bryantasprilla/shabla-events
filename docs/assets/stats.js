(function () {
  "use strict";

  let data = null;

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
    if (!source.active) return I18N.t("statusInactive");
    if (source.last_run_status === "success") return I18N.t("statusSuccess");
    if (source.last_run_status === "error") return I18N.t("statusError");
    return I18N.t("statusNoRuns");
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
        <td>${s.last_error ? `<span class="status-error" title="${escapeHtml(s.last_error)}">${escapeHtml(I18N.t("statusError"))}</span>` : "—"}</td>
      </tr>
    `;
  }

  function render() {
    const content = document.getElementById("content");
    const sources = ((data && data.sources) || []).slice().sort((a, b) => {
      const ra = a.pass_rate == null ? -1 : a.pass_rate;
      const rb = b.pass_rate == null ? -1 : b.pass_rate;
      return rb - ra;
    });
    const cols = [
      "colSource", "colTier", "colStatus", "colLastRun", "colFetched", "colNew",
      "colPassed", "colEvents", "colPassRate", "colConfirmRate", "colError",
    ];

    content.innerHTML = `
      <div class="overflow-x">
        <table class="stats">
          <thead><tr>${cols.map((c) => `<th>${escapeHtml(I18N.t(c))}</th>`).join("")}</tr></thead>
          <tbody>${sources.map(row).join("")}</tbody>
        </table>
      </div>
    `;

    document.getElementById("footer").textContent =
      I18N.t("windowLast", { n: data.window_days }) + " " + I18N.t("generated") + " " +
      new Date(data.generated_at).toLocaleString(I18N.locale);
  }

  window.addEventListener("langchange", () => {
    if (data) render();
  });

  fetch("source_stats.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((json) => {
      data = json;
      render();
    })
    .catch((err) => {
      document.getElementById("content").innerHTML =
        `<p class="empty-state">${escapeHtml(I18N.t("statsLoadError"))}</p>`;
      console.error(err);
    });
})();
