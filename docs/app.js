const LANGUAGE_KEY = "maison_etudiant_language";

const translations = {
  en: {
    pageTitle: "Lyon Shared Accommodation",
    heroTitle: "Lyon Shared Accommodation Dashboard",
    heroLead: "Daily combined listings from ImmoJeune, La Carte des Colocs, Location Étudiant, and Studapart.",
    activeListings: "Active Listings",
    sources: "Sources",
    newInLatestRun: "New In Latest Run",
    updatedInLatestRun: "Updated In Latest Run",
    removedInLatestRun: "Removed In Latest Run",
    lastRefresh: "Last Refresh",
    searchPlaceholder: "Search by title, address, postcode, city",
    allSources: "All sources",
    anyStatus: "Any status",
    downloadXlsx: "Download XLSX",
    downloadCsv: "Download CSV",
    dashboardFilters: "Dashboard Filters",
    minimumPrice: "Minimum Price (EUR)",
    maximumPrice: "Maximum Price (EUR)",
    noMinimum: "No minimum",
    noMaximum: "No maximum",
    mappedOnly: "Only show listings with map coordinates",
    resetFilters: "Reset filters",
    postcodeFilter: "Postcode Filter",
    selectAll: "Select all",
    clearAll: "Clear all",
    mapView: "Map View",
    source: "Source",
    title: "Title",
    priceEur: "Price EUR",
    postcode: "Postcode",
    city: "City",
    address: "Address",
    availability: "Availability",
    summary: "Summary",
    firstSeen: "First Seen",
    lastSeen: "Last Seen",
    link: "Link",
    open: "Open",
    jsonError: "Could not load listing data yet.",
    mapUnavailable: "Map unavailable.",
    currentSourceMix: "Current source mix",
    noNewListings: "No new listings in the latest run.",
    noRemovedListings: "No removed listings in the latest run.",
    loadingVisible: "Loading listings…",
    loadingPostcodes: "Loading postcode options…",
    loadingMapped: "Loading mapped listings…",
    loadingNew: "Loading new listings…",
    loadingRemoved: "Loading removed listings…",
    listingSingular: "listing",
    listingPlural: "listings",
    visibleSuffix: "visible",
    mappedInCurrentView: "in the current filtered view",
    sourceCountLabel: "source",
    sourceCountPlural: "sources",
    statusNew: "new",
    statusUpdated: "updated",
    statusUnchanged: "unchanged",
    statusMissingButLive: "missing but live",
    statusPendingRemoval: "pending removal",
    priceUnknown: "Price unknown",
    unknownPostcode: "Unknown postcode",
    allPostcodesSelected: "All {count} postcode groups selected",
    somePostcodesSelected: "{selected} of {count} postcode groups selected",
  },
  fr: {
    pageTitle: "Logements partagés à Lyon",
    heroTitle: "Tableau de Bord des Logements Partagés à Lyon",
    heroLead: "Annonces combinées chaque jour depuis ImmoJeune, La Carte des Colocs, Location Étudiant et Studapart.",
    activeListings: "Annonces actives",
    sources: "Sources",
    newInLatestRun: "Nouvelles lors du dernier passage",
    updatedInLatestRun: "Mises à jour lors du dernier passage",
    removedInLatestRun: "Retirées lors du dernier passage",
    lastRefresh: "Dernière mise à jour",
    searchPlaceholder: "Rechercher par titre, adresse, code postal, ville",
    allSources: "Toutes les sources",
    anyStatus: "Tous les statuts",
    downloadXlsx: "Télécharger XLSX",
    downloadCsv: "Télécharger CSV",
    dashboardFilters: "Filtres du tableau de bord",
    minimumPrice: "Prix minimum (EUR)",
    maximumPrice: "Prix maximum (EUR)",
    noMinimum: "Pas de minimum",
    noMaximum: "Pas de maximum",
    mappedOnly: "Afficher uniquement les annonces avec coordonnées sur la carte",
    resetFilters: "Réinitialiser les filtres",
    postcodeFilter: "Filtre par code postal",
    selectAll: "Tout sélectionner",
    clearAll: "Tout effacer",
    mapView: "Vue carte",
    source: "Source",
    title: "Titre",
    priceEur: "Prix EUR",
    postcode: "Code postal",
    city: "Ville",
    address: "Adresse",
    availability: "Disponibilité",
    summary: "Résumé",
    firstSeen: "Première détection",
    lastSeen: "Dernière détection",
    link: "Lien",
    open: "Ouvrir",
    jsonError: "Impossible de charger les données pour le moment.",
    mapUnavailable: "Carte indisponible.",
    currentSourceMix: "Répartition actuelle des sources",
    noNewListings: "Aucune nouvelle annonce lors du dernier passage.",
    noRemovedListings: "Aucune annonce retirée lors du dernier passage.",
    loadingVisible: "Chargement des annonces…",
    loadingPostcodes: "Chargement des codes postaux…",
    loadingMapped: "Chargement des annonces cartographiées…",
    loadingNew: "Chargement des nouvelles annonces…",
    loadingRemoved: "Chargement des annonces retirées…",
    listingSingular: "annonce",
    listingPlural: "annonces",
    visibleSuffix: "visibles",
    mappedInCurrentView: "dans la vue filtrée actuelle",
    sourceCountLabel: "source",
    sourceCountPlural: "sources",
    statusNew: "nouvelle",
    statusUpdated: "mise à jour",
    statusUnchanged: "inchangée",
    statusMissingButLive: "manquante mais en ligne",
    statusPendingRemoval: "retrait en attente",
    priceUnknown: "Prix inconnu",
    unknownPostcode: "Code postal inconnu",
    allPostcodesSelected: "Les {count} groupes de codes postaux sont sélectionnés",
    somePostcodesSelected: "{selected} groupes sur {count} sont sélectionnés",
  },
};

let currentLanguage = localStorage.getItem(LANGUAGE_KEY) || "en";
let renderUI = null;

function t(key, params = {}) {
  const dict = translations[currentLanguage] || translations.en;
  const template = dict[key] ?? translations.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ""));
}

function statusLabel(status) {
  const key = `status${status.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join("")}`;
  return t(key);
}

function pluralListing(count) {
  return `${count} ${count === 1 ? t("listingSingular") : t("listingPlural")}`;
}

function fetchJson(path) {
  return fetch(path, { cache: "no-store" }).then((response) => {
    if (!response.ok) {
      throw new Error(`Failed to load ${path}: ${response.status}`);
    }
    return response.json();
  });
}

function safe(value) {
  return value === null || value === undefined ? "" : String(value);
}

function compareValues(a, b) {
  if (a === "" && b !== "") return 1;
  if (b === "" && a !== "") return -1;
  const numA = Number(a);
  const numB = Number(b);
  if (!Number.isNaN(numA) && !Number.isNaN(numB) && a !== "" && b !== "") {
    return numA - numB;
  }
  return safe(a).localeCompare(safe(b), undefined, { sensitivity: "base" });
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return safe(value);
  return date.toLocaleString(currentLanguage === "fr" ? "fr-FR" : undefined);
}

function priceLabel(value) {
  if (value === null || value === undefined || value === "") return t("priceUnknown");
  return `${value} EUR`;
}

function applyStaticTranslations() {
  document.documentElement.lang = currentLanguage;
  document.title = t("pageTitle");
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
  });
  const enButton = document.getElementById("langEn");
  const frButton = document.getElementById("langFr");
  if (enButton && frButton) {
    enButton.classList.toggle("is-active", currentLanguage === "en");
    frButton.classList.toggle("is-active", currentLanguage === "fr");
  }
}

function shortListHtml(rows, emptyLabel) {
  if (!rows.length) {
    return `<p class="empty-state">${emptyLabel}</p>`;
  }
  return rows
    .slice(0, 12)
    .map((row) => {
      const parts = [safe(row.source), priceLabel(row.price_eur), safe(row.postcode), safe(row.address)]
        .filter(Boolean)
        .join(" | ");
      return `
        <article class="change-item">
          <a href="${safe(row.url)}" target="_blank" rel="noreferrer">${safe(row.title) || "Untitled listing"}</a>
          <div class="change-line">${parts}</div>
        </article>
      `;
    })
    .join("");
}

function populateSourceFilter(listings) {
  const select = document.getElementById("sourceFilter");
  const currentValue = select.value;
  select.innerHTML = `<option value="">${t("allSources")}</option>`;
  const sources = [...new Set(listings.map((row) => row.source).filter(Boolean))].sort();
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source;
    option.textContent = source;
    select.appendChild(option);
  }
  if ([...select.options].some((option) => option.value === currentValue)) {
    select.value = currentValue;
  }
}

function populateStatusFilter(listings) {
  const select = document.getElementById("statusFilter");
  const currentValue = select.value;
  select.innerHTML = `<option value="">${t("anyStatus")}</option>`;
  const statuses = [...new Set(listings.map((row) => safe(row.latest_status).toLowerCase()).filter(Boolean))].sort();
  for (const status of statuses) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = statusLabel(status);
    select.appendChild(option);
  }
  if ([...select.options].some((option) => option.value === currentValue)) {
    select.value = currentValue;
  }
}

function setSummary(metadata) {
  const summary = metadata.summary || {};
  const sourceCounts = metadata.source_counts || {};

  document.getElementById("activeCount").textContent = safe(summary.active_count ?? metadata.active_count);
  document.getElementById("sourceCount").textContent = String(Object.keys(sourceCounts).length);
  document.getElementById("newCount").textContent = safe(summary.new_count ?? metadata.new_count ?? 0);
  document.getElementById("updatedCount").textContent = safe(summary.updated_count ?? metadata.updated_count ?? 0);
  document.getElementById("removedCount").textContent = safe(summary.removed_count ?? metadata.removed_count ?? 0);
  document.getElementById("lastRefresh").textContent = formatTimestamp(summary.generated_at || metadata.generated_at);

  const parts = Object.entries(sourceCounts)
    .sort((left, right) => left[0].localeCompare(right[0]))
    .map(([source, count]) => `${source}: ${count}`);
  document.getElementById("sourceBreakdown").textContent = parts.length ? `${t("currentSourceMix")}: ${parts.join(" | ")}` : "";
}

function renderChanges(newRows, removedRows) {
  document.getElementById("newList").innerHTML = shortListHtml(newRows, t("noNewListings"));
  document.getElementById("removedList").innerHTML = shortListHtml(removedRows, t("noRemovedListings"));
  document.getElementById("newMeta").textContent = pluralListing(newRows.length);
  document.getElementById("removedMeta").textContent = pluralListing(removedRows.length);
}

function bootChangeViews() {
  const cards = Array.from(document.querySelectorAll(".stat-card[data-view-target]"));
  const panels = Array.from(document.querySelectorAll(".change-panel[data-view-panel]"));
  const views = document.getElementById("changeViews");
  let currentView = "active";

  function activate(viewName) {
    currentView = viewName;
    for (const card of cards) {
      card.classList.toggle("is-active", card.dataset.viewTarget === viewName);
    }
    for (const panel of panels) {
      panel.classList.toggle("is-active", panel.dataset.viewPanel === viewName);
    }
    if (views) {
      views.classList.toggle("is-visible", viewName !== "active");
    }
    if (views && viewName !== "active") {
      views.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  for (const card of cards) {
    card.addEventListener("click", () => {
      const targetView = card.dataset.viewTarget || "active";
      activate(currentView === targetView ? "active" : targetView);
    });
  }

  activate("active");
}

function createMap(sourceColors) {
  const map = L.map("map", { scrollWheelZoom: true }).setView([45.75, 4.85], 11.8);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const layerGroup = L.layerGroup().addTo(map);

  function update(rows) {
    layerGroup.clearLayers();
    const withCoords = rows.filter((row) => Number.isFinite(row.latitude) && Number.isFinite(row.longitude));
    for (const row of withCoords) {
      const color = sourceColors[row.source] || "#0d6b66";
      const marker = L.circleMarker([row.latitude, row.longitude], {
        radius: 6,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.75,
      });
      marker.bindPopup(
        `
          <strong>${safe(row.title)}</strong><br>
          ${safe(row.source)}<br>
          ${priceLabel(row.price_eur)}<br>
          ${safe(row.address)}<br>
          <a href="${safe(row.url)}" target="_blank" rel="noreferrer">${t("open")}</a>
        `,
      );
      layerGroup.addLayer(marker);
    }

    document.getElementById("mapMeta").textContent =
      `${pluralListing(withCoords.length)} ${t("mappedInCurrentView")}`;

    if (withCoords.length) {
      const bounds = L.latLngBounds(withCoords.map((row) => [row.latitude, row.longitude]));
      map.fitBounds(bounds.pad(0.18));
    }
  }

  return { update };
}

function bootTable(listings, newRows, removedRows, metadata) {
  const tbody = document.querySelector("#listingTable tbody");
  const searchInput = document.getElementById("searchInput");
  const sourceFilter = document.getElementById("sourceFilter");
  const statusFilter = document.getElementById("statusFilter");
  const minPriceFilter = document.getElementById("minPriceFilter");
  const maxPriceFilter = document.getElementById("maxPriceFilter");
  const mappedOnlyFilter = document.getElementById("mappedOnlyFilter");
  const resetFiltersButton = document.getElementById("resetFilters");
  const postcodeFilter = document.getElementById("postcodeFilter");
  const postcodeMeta = document.getElementById("postcodeMeta");
  const visibleCount = document.getElementById("visibleCount");
  const postcodeSelectAll = document.getElementById("postcodeSelectAll");
  const postcodeClearAll = document.getElementById("postcodeClearAll");

  const sourceColors = {
    immojeune: "#c65b36",
    la_carte_des_colocs: "#0d6b66",
    location_etudiant: "#5f7d2b",
    studapart: "#5a4db2",
  };
  const mapView = createMap(sourceColors);

  const postcodeCounts = new Map();
  for (const row of listings) {
    const postcode = safe(row.postcode).trim() || "__unknown__";
    postcodeCounts.set(postcode, (postcodeCounts.get(postcode) || 0) + 1);
  }
  const postcodeOptions = [...postcodeCounts.entries()]
    .sort((left, right) => compareValues(left[0], right[0]))
    .map(([value, count]) => ({
      value,
      count,
    }));

  let selectedPostcodes = new Set(postcodeOptions.map((option) => option.value));
  let sortKey = "price_eur";
  let sortDirection = "asc";

  function currentRowPostcode(row) {
    return safe(row.postcode).trim() || "__unknown__";
  }

  function renderPostcodeFilter() {
    postcodeFilter.innerHTML = postcodeOptions
      .map((option) => {
        const checked = selectedPostcodes.has(option.value) ? "checked" : "";
        const label = option.value === "__unknown__" ? t("unknownPostcode") : option.value;
        return `
          <label class="chip-option ${checked ? "active" : ""}">
            <input type="checkbox" value="${option.value}" ${checked}>
            <span>${safe(label)} <strong>${option.count}</strong></span>
          </label>
        `;
      })
      .join("");

    postcodeMeta.textContent = selectedPostcodes.size === postcodeOptions.length
      ? t("allPostcodesSelected", { count: postcodeOptions.length })
      : t("somePostcodesSelected", { selected: selectedPostcodes.size, count: postcodeOptions.length });

    postcodeFilter.querySelectorAll("input[type='checkbox']").forEach((input) => {
      input.addEventListener("change", (event) => {
        const value = event.target.value;
        if (event.target.checked) {
          selectedPostcodes.add(value);
        } else {
          selectedPostcodes.delete(value);
        }
        renderPostcodeFilter();
        render();
      });
    });
  }

  function filteredRows() {
    const query = searchInput.value.trim().toLowerCase();
    const source = sourceFilter.value;
    const status = statusFilter.value;
    const minPrice = minPriceFilter.value === "" ? null : Number(minPriceFilter.value);
    const maxPrice = maxPriceFilter.value === "" ? null : Number(maxPriceFilter.value);
    const mappedOnly = mappedOnlyFilter.checked;

    return listings.filter((row) => {
      if (source && row.source !== source) return false;
      if (status && safe(row.latest_status).toLowerCase() !== status) return false;
      if (!selectedPostcodes.has(currentRowPostcode(row))) return false;
      if (mappedOnly && !(Number.isFinite(row.latitude) && Number.isFinite(row.longitude))) return false;

      if (minPrice !== null || maxPrice !== null) {
        if (!Number.isFinite(row.price_eur)) return false;
        if (minPrice !== null && row.price_eur < minPrice) return false;
        if (maxPrice !== null && row.price_eur > maxPrice) return false;
      }

      if (!query) return true;
      const haystack = [
        row.source,
        row.title,
        row.postcode,
        row.city,
        row.address,
        row.availability,
        row.extra_summary,
      ].map(safe).join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }

  function render() {
    const rows = filteredRows().slice().sort((left, right) => {
      const result = compareValues(left[sortKey], right[sortKey]);
      return sortDirection === "asc" ? result : -result;
    });

    tbody.innerHTML = rows.map((row) => `
      <tr>
        <td>${safe(row.source)}</td>
        <td>${safe(row.title)}</td>
        <td>${safe(row.price_eur)}</td>
        <td>${safe(row.postcode)}</td>
        <td>${safe(row.city)}</td>
        <td>${safe(row.address)}</td>
        <td>${safe(row.availability)}</td>
        <td>${safe(row.extra_summary)}</td>
        <td>${formatTimestamp(row.first_seen_at)}</td>
        <td>${formatTimestamp(row.last_seen_at)}</td>
        <td><a href="${safe(row.url)}" target="_blank" rel="noreferrer">${t("open")}</a></td>
      </tr>
    `).join("");

    visibleCount.textContent = `${pluralListing(rows.length)} ${t("visibleSuffix")}`;
    mapView.update(rows);
  }

  document.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      if (sortKey === key) {
        sortDirection = sortDirection === "asc" ? "desc" : "asc";
      } else {
        sortKey = key;
        sortDirection = "asc";
      }
      render();
    });
  });

  postcodeSelectAll.addEventListener("click", () => {
    selectedPostcodes = new Set(postcodeOptions.map((option) => option.value));
    renderPostcodeFilter();
    render();
  });

  postcodeClearAll.addEventListener("click", () => {
    selectedPostcodes = new Set();
    renderPostcodeFilter();
    render();
  });

  resetFiltersButton.addEventListener("click", () => {
    searchInput.value = "";
    sourceFilter.value = "";
    statusFilter.value = "";
    minPriceFilter.value = "";
    maxPriceFilter.value = "";
    mappedOnlyFilter.checked = false;
    selectedPostcodes = new Set(postcodeOptions.map((option) => option.value));
    renderPostcodeFilter();
    render();
  });

  searchInput.addEventListener("input", render);
  sourceFilter.addEventListener("change", render);
  statusFilter.addEventListener("change", render);
  minPriceFilter.addEventListener("input", render);
  maxPriceFilter.addEventListener("input", render);
  mappedOnlyFilter.addEventListener("change", render);

  renderUI = () => {
    applyStaticTranslations();
    populateSourceFilter(listings);
    populateStatusFilter(listings);
    setSummary(metadata);
    renderChanges(newRows, removedRows);
    renderPostcodeFilter();
    render();
  };

  renderUI();
}

function bootLanguageSwitcher() {
  const enButton = document.getElementById("langEn");
  const frButton = document.getElementById("langFr");

  function switchLanguage(nextLanguage) {
    currentLanguage = nextLanguage;
    localStorage.setItem(LANGUAGE_KEY, currentLanguage);
    applyStaticTranslations();
    if (typeof renderUI === "function") {
      renderUI();
    }
  }

  enButton.addEventListener("click", () => switchLanguage("en"));
  frButton.addEventListener("click", () => switchLanguage("fr"));
  applyStaticTranslations();
}

async function main() {
  bootLanguageSwitcher();
  try {
    const [listings, metadata, newRows, removedRows] = await Promise.all([
      fetchJson("./data/active_listings.json"),
      fetchJson("./data/site_metadata.json"),
      fetchJson("./data/new_in_run.json"),
      fetchJson("./data/removed_in_run.json"),
    ]);
    bootChangeViews();
    bootTable(listings, newRows, removedRows, metadata);
  } catch (error) {
    document.querySelector(".table-shell").innerHTML = `<p class="source-note">${t("jsonError")} ${safe(error.message)}</p>`;
    const mapEl = document.getElementById("map");
    if (mapEl) {
      mapEl.outerHTML = `<p class="source-note">${t("mapUnavailable")} ${safe(error.message)}</p>`;
    }
  }
}

main();
