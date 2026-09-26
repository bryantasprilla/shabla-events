(function () {
  "use strict";

  const SUPPORTED = ["en", "bg", "ro"];
  const LOCALES = { en: "en-GB", bg: "bg-BG", ro: "ro-RO" };

  const STRINGS = {
    en: {
      pageTitle: "Shabla Events",
      title: "Shabla Events",
      subtitle: "Local events near Shabla, Bulgaria and southeastern Romania, gathered and extracted automatically.",
      tabEvents: "Events",
      tabHealth: "Source health",
      loading: "Loading events…",
      empty: "No upcoming events found right now — check back soon.",
      loadError: "Could not load events right now.",
      tbd: "Date to be announced",
      source: "Source",
      updated: "Last updated",
      "cat.concert": "Concert",
      "cat.festival": "Festival",
      "cat.exhibition": "Exhibition",
      "cat.municipal": "Municipal",
      "cat.sports": "Sports",
      "cat.theater": "Theater",
      "cat.adult_18+": "18+",
      "cat.other": "Other",
      statsPageTitle: "Shabla Events — Source health",
      statsTitle: "Source health",
      statsSubtitle: "Per-source pipeline stats over the trailing window — how much each source contributes.",
      loadingStats: "Loading stats…",
      statsLoadError: "Could not load source stats right now.",
      colSource: "Source",
      colTier: "Tier",
      colStatus: "Status",
      colLastRun: "Last run",
      colFetched: "Fetched",
      colNew: "New",
      colPassed: "Passed filter",
      colEvents: "Events",
      colPassRate: "Pass rate",
      colConfirmRate: "Confirm rate",
      colError: "Error",
      statusSuccess: "success",
      statusError: "error",
      statusInactive: "inactive",
      statusNoRuns: "no runs yet",
      windowLast: "Window: last {n} days.",
      generated: "Generated",
    },
    bg: {
      pageTitle: "Събития край Шабла",
      title: "Събития край Шабла",
      subtitle: "Местни събития около Шабла, България и югоизточна Румъния, събрани и извлечени автоматично.",
      tabEvents: "Събития",
      tabHealth: "Състояние на източниците",
      loading: "Зареждане на събитията…",
      empty: "В момента няма предстоящи събития — проверете отново скоро.",
      loadError: "В момента не могат да се заредят събитията.",
      tbd: "Датата предстои да бъде обявена",
      source: "Източник",
      updated: "Последна актуализация",
      "cat.concert": "Концерт",
      "cat.festival": "Фестивал",
      "cat.exhibition": "Изложба",
      "cat.municipal": "Общински",
      "cat.sports": "Спорт",
      "cat.theater": "Театър",
      "cat.adult_18+": "18+",
      "cat.other": "Друго",
      statsPageTitle: "Събития край Шабла — Състояние на източниците",
      statsTitle: "Състояние на източниците",
      statsSubtitle: "Статистика по източници за последния период — колко допринася всеки източник.",
      loadingStats: "Зареждане на статистиката…",
      statsLoadError: "В момента не може да се зареди статистиката.",
      colSource: "Източник",
      colTier: "Ниво",
      colStatus: "Статус",
      colLastRun: "Последно изпълнение",
      colFetched: "Извлечени",
      colNew: "Нови",
      colPassed: "Минали филтъра",
      colEvents: "Събития",
      colPassRate: "Дял минали",
      colConfirmRate: "Дял потвърдени",
      colError: "Грешка",
      statusSuccess: "успешно",
      statusError: "грешка",
      statusInactive: "неактивен",
      statusNoRuns: "все още няма изпълнения",
      windowLast: "Период: последните {n} дни.",
      generated: "Генерирано",
    },
    ro: {
      pageTitle: "Evenimente în zona Shabla",
      title: "Evenimente în zona Shabla",
      subtitle: "Evenimente locale din jurul Shabla, Bulgaria, și din sud-estul României, adunate și extrase automat.",
      tabEvents: "Evenimente",
      tabHealth: "Starea surselor",
      loading: "Se încarcă evenimentele…",
      empty: "Momentan nu există evenimente viitoare — reveniți în curând.",
      loadError: "Momentan nu s-au putut încărca evenimentele.",
      tbd: "Data urmează să fie anunțată",
      source: "Sursă",
      updated: "Ultima actualizare",
      "cat.concert": "Concert",
      "cat.festival": "Festival",
      "cat.exhibition": "Expoziție",
      "cat.municipal": "Municipal",
      "cat.sports": "Sport",
      "cat.theater": "Teatru",
      "cat.adult_18+": "18+",
      "cat.other": "Altele",
      statsPageTitle: "Evenimente în zona Shabla — Starea surselor",
      statsTitle: "Starea surselor",
      statsSubtitle: "Statistici pe surse pentru perioada recentă — cât contribuie fiecare sursă.",
      loadingStats: "Se încarcă statisticile…",
      statsLoadError: "Momentan nu s-au putut încărca statisticile.",
      colSource: "Sursă",
      colTier: "Nivel",
      colStatus: "Stare",
      colLastRun: "Ultima rulare",
      colFetched: "Preluate",
      colNew: "Noi",
      colPassed: "Au trecut de filtru",
      colEvents: "Evenimente",
      colPassRate: "Rata de trecere",
      colConfirmRate: "Rata de confirmare",
      colError: "Eroare",
      statusSuccess: "succes",
      statusError: "eroare",
      statusInactive: "inactiv",
      statusNoRuns: "nicio rulare încă",
      windowLast: "Perioadă: ultimele {n} zile.",
      generated: "Generat",
    },
  };

  function safeGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function safeSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      /* storage may be unavailable (private mode) -- language just won't persist */
    }
  }

  function detectLang() {
    const fromUrl = new URLSearchParams(window.location.search).get("lang");
    if (SUPPORTED.includes(fromUrl)) return fromUrl;
    const stored = safeGet("lang");
    if (SUPPORTED.includes(stored)) return stored;
    const browser = (navigator.language || "en").slice(0, 2).toLowerCase();
    return SUPPORTED.includes(browser) ? browser : "en";
  }

  const I18N = {
    lang: detectLang(),
    get locale() {
      return LOCALES[this.lang];
    },
    t(key, vars) {
      let text = (STRINGS[this.lang] && STRINGS[this.lang][key]) || STRINGS.en[key] || key;
      if (vars) {
        Object.keys(vars).forEach((k) => {
          text = text.replace("{" + k + "}", vars[k]);
        });
      }
      return text;
    },
    // Picks a translated field for an event, falling back to the original
    // text when a translation is missing or empty (e.g. events not yet
    // translated by the pipeline).
    pick(ev, field) {
      const tr = ev.translations && ev.translations[this.lang];
      return (tr && tr[field]) || ev[field] || "";
    },
    setLang(lang) {
      if (!SUPPORTED.includes(lang) || lang === this.lang) return;
      this.lang = lang;
      safeSet("lang", lang);
      const url = new URL(window.location.href);
      url.searchParams.set("lang", lang);
      window.history.replaceState(null, "", url);
      this.applyStatic();
      window.dispatchEvent(new CustomEvent("langchange"));
    },
    applyStatic() {
      document.documentElement.lang = this.lang;
      document.querySelectorAll("[data-i18n]").forEach((el) => {
        el.textContent = this.t(el.getAttribute("data-i18n"));
      });
      const titleKey = document.body.getAttribute("data-title-key");
      if (titleKey) document.title = this.t(titleKey);
      document.querySelectorAll("#lang-switch button").forEach((btn) => {
        btn.setAttribute("aria-pressed", String(btn.dataset.lang === this.lang));
      });
      // Keep the tab links on the same language.
      document.querySelectorAll("nav.tabs a").forEach((a) => {
        const u = new URL(a.getAttribute("href"), window.location.href);
        u.searchParams.set("lang", this.lang);
        a.setAttribute("href", u.pathname.split("/").pop() + u.search);
      });
    },
  };

  function buildSwitcher() {
    const host = document.getElementById("lang-switch");
    if (!host) return;
    host.setAttribute("role", "group");
    host.setAttribute("aria-label", "Language");
    SUPPORTED.forEach((lang) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.lang = lang;
      btn.textContent = lang.toUpperCase();
      btn.addEventListener("click", () => I18N.setLang(lang));
      host.appendChild(btn);
    });
  }

  window.I18N = I18N;
  buildSwitcher();
  I18N.applyStatic();
})();
