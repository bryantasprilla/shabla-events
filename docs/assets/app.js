(function () {
  "use strict";

  let data = null;

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : String(s);
    return div.innerHTML;
  }

  function formatDateHeading(isoDate) {
    if (!isoDate) return I18N.t("tbd");
    const [y, m, d] = isoDate.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    return dt.toLocaleDateString(I18N.locale, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "UTC",
    });
  }

  function groupByDate(events) {
    const groups = [];
    const byKey = new Map();
    for (const ev of events) {
      const key = ev.date || "";
      if (!byKey.has(key)) {
        const group = { key, events: [] };
        byKey.set(key, group);
        groups.push(group);
      }
      byKey.get(key).events.push(ev);
    }
    return groups;
  }

  function categoryLabel(category) {
    const key = "cat." + (category || "other");
    const label = I18N.t(key);
    return label === key ? category || I18N.t("cat.other") : label;
  }

  function renderEventCard(ev) {
    const metaParts = [];
    if (ev.time) metaParts.push(escapeHtml(ev.time));
    if (ev.location) metaParts.push(escapeHtml(ev.location));

    const description = I18N.pick(ev, "description");
    const sourceLinks = (ev.sources || [])
      .map((s) => `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.source_name)}</a>`)
      .join("");

    return `
      <div class="event-card">
        <div class="row1">
          <span class="title">${escapeHtml(I18N.pick(ev, "title"))}</span>
          <span class="badge">${escapeHtml(categoryLabel(ev.category))}</span>
        </div>
        ${metaParts.length ? `<div class="meta">${metaParts.join(" · ")}</div>` : ""}
        ${description ? `<div class="description">${escapeHtml(description)}</div>` : ""}
        ${sourceLinks ? `<div class="sources">${escapeHtml(I18N.t("source"))}: ${sourceLinks}</div>` : ""}
      </div>
    `;
  }

  function render() {
    const content = document.getElementById("content");
    const events = (data && data.events) || [];
    if (events.length === 0) {
      content.innerHTML = `<p class="empty-state">${escapeHtml(I18N.t("empty"))}</p>`;
      return;
    }

    content.innerHTML = groupByDate(events)
      .map(
        (g) => `
        <section class="date-group">
          <h2>${escapeHtml(formatDateHeading(g.key))}</h2>
          ${g.events.map(renderEventCard).join("")}
        </section>
      `
      )
      .join("");

    document.getElementById("footer").textContent =
      I18N.t("updated") + " " + new Date(data.generated_at).toLocaleString(I18N.locale);
  }

  window.addEventListener("langchange", () => {
    if (data) render();
  });

  fetch("events.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((json) => {
      data = json;
      render();
    })
    .catch((err) => {
      document.getElementById("content").innerHTML =
        `<p class="empty-state">${escapeHtml(I18N.t("loadError"))}</p>`;
      console.error(err);
    });
})();
