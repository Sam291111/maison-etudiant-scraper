async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.json();
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
  return date.toLocaleString();
}

function priceLabel(value) {
  if (value === null || value === undefined || value === "") return "Price unknown";
  return `${value} EUR`;
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
  const sources = [...new Set(listings.map((row) => row.source).filter(Boolean))].sort();
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source;
    option.textContent = source;
    select.appendChild(option);
  }
}

function populateStatusFilter(listings) {
  const select = document.getElementById("statusFilter");
  const statuses = [...new Set(listings.map((row) => safe(row.latest_status).toLowerCase()).filter(Boolean))].sort();
  for (const status of statuses) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    select.appendChild(option);
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
  document.getElementById("sourceBreakdown").textContent = parts.length ? `Current source mix: ${parts.join(" | ")}` : "";
}

function renderChanges(newRows, removedRows) {
  document.getElementById("newList").innerHTML = shortListHtml(newRows, "No new listings in the latest run.");
  document.getElementById("removedList").innerHTML = shortListHtml(removedRows, "No removed listings in the latest run.");
  document.getElementById("newMeta").textContent = `${newRows.length} listing${newRows.length === 1 ? "" : "s"}`;
  document.getElementById("removedMeta").textContent = `${removedRows.length} listing${removedRows.length === 1 ? "" : "s"}`;
}

function bootChangeViews() {
  const cards = Array.from(document.querySelectorAll(".stat-card[data-view-target]"));
  const panels = Array.from(document.querySelectorAll(".change-panel[data-view-panel]"));
  const views = document.getElementById("changeViews");

  function activate(viewName) {
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
      activate(card.dataset.viewTarget || "active");
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
          <a href="${safe(row.url)}" target="_blank" rel="noreferrer">Open listing</a>
        `,
      );
      layerGroup.addLayer(marker);
    }

    document.getElementById("mapMeta").textContent = `${withCoords.length} mapped listing${withCoords.length === 1 ? "" : "s"} in the current filtered view`;

    if (withCoords.length) {
      const bounds = L.latLngBounds(withCoords.map((row) => [row.latitude, row.longitude]));
      map.fitBounds(bounds.pad(0.18));
    }
  }

  return { update };
}

function bootTable(listings) {
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
      label: value === "__unknown__" ? "Unknown postcode" : value,
      count,
    }));

  let selectedPostcodes = new Set(postcodeOptions.map((option) => option.value));
  let sortKey = "price_eur";
  let sortDirection = "asc";

  function currentRowPostcode(row) {
    return safe(row.postcode).trim() || "__unknown__";
  }

  function activePostcodeFilterCount() {
    return postcodeOptions.length - selectedPostcodes.size;
  }

  function renderPostcodeFilter() {
    postcodeFilter.innerHTML = postcodeOptions
      .map((option) => {
        const checked = selectedPostcodes.has(option.value) ? "checked" : "";
        return `
          <label class="chip-option ${checked ? "active" : ""}">
            <input type="checkbox" value="${option.value}" ${checked}>
            <span>${safe(option.label)} <strong>${option.count}</strong></span>
          </label>
        `;
      })
      .join("");

    const hiddenCount = activePostcodeFilterCount();
    postcodeMeta.textContent = hiddenCount
      ? `${selectedPostcodes.size} of ${postcodeOptions.length} postcode groups selected`
      : `All ${postcodeOptions.length} postcode groups selected`;

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
      ]
        .map(safe)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }

  function render() {
    const rows = filteredRows().slice().sort((left, right) => {
      const result = compareValues(left[sortKey], right[sortKey]);
      return sortDirection === "asc" ? result : -result;
    });

    tbody.innerHTML = rows
      .map(
        (row) => `
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
          <td><a href="${safe(row.url)}" target="_blank" rel="noreferrer">Open</a></td>
        </tr>
      `,
      )
      .join("");

    visibleCount.textContent = `${rows.length} listing${rows.length === 1 ? "" : "s"} visible`;
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

  renderPostcodeFilter();
  render();
}

async function main() {
  try {
    const [listings, metadata, newRows, removedRows] = await Promise.all([
      fetchJson("./data/active_listings.json"),
      fetchJson("./data/site_metadata.json"),
      fetchJson("./data/new_in_run.json"),
      fetchJson("./data/removed_in_run.json"),
    ]);
    populateSourceFilter(listings);
    populateStatusFilter(listings);
    setSummary(metadata);
    renderChanges(newRows, removedRows);
    bootChangeViews();
    bootTable(listings);
  } catch (error) {
    document.querySelector(".table-shell").innerHTML = `<p class="source-note">Could not load listing data yet. ${safe(error.message)}</p>`;
    const mapEl = document.getElementById("map");
    if (mapEl) {
      mapEl.outerHTML = `<p class="source-note">Map unavailable. ${safe(error.message)}</p>`;
    }
  }
}

main();
