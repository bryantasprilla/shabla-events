(function () {
  "use strict";

  const CATEGORY_LABELS = {
    concert: "Concert",
    festival: "Festival",
    exhibition: "Exhibition",
    municipal: "Municipal",
    sports: "Sports",
    theater: "Theater",
    adult_18plus: "18+",
    "adult_18+": "18+",
    other: "Other",
  };

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : String(s);
    return div.innerHTML;
  }

  function formatDateHeading(isoDate) {
    if (!isoDate) return "Date to be announced";
    const [y, m, d] = isoDate.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    return dt.toLocaleDateString(undefined, {
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

  function renderEventCard(ev) {
    const catLabel = CATEGORY_LABELS[ev.category] || ev.category || "Other";
    const metaParts = [];
    if (ev.time) metaParts.push(ev.time);
    if (ev.location) metaParts.push(escapeHtml(ev.location));

    const sourceLinks = (ev.sources || [])
      .map((s) => `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.source_name)}</a>`)
      .join("");

    return `
      <div class="event-card">
        <div class="row1">
          <span class="title">${escapeHtml(ev.title)}</span>
          <span class="badge">${escapeHtml(catLabel)}</span>
        </div>
        ${metaParts.length ? `<div class="meta">${metaParts.join(" · ")}</div>` : ""}
        ${ev.description ? `<div class="description">${escapeHtml(ev.description)}</div>` : ""}
        ${sourceLinks ? `<div class="sources">Source: ${sourceLinks}</div>` : ""}
      </div>
    `;
  }

  function render(data) {
    const content = document.getElementById("content");
    const events = data.events || [];
    if (events.length === 0) {
      content.innerHTML = '<p class="empty-state">No upcoming events found right now — check back soon.</p>';
      return;
    }

    const groups = groupByDate(events);
    content.innerHTML = groups
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
      "Last updated " + new Date(data.generated_at).toLocaleString();
  }

  fetch("events.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then(render)
    .catch((err) => {
      document.getElementById("content").innerHTML =
        '<p class="empty-state">Could not load events right now.</p>';
      console.error(err);
    });
})();
