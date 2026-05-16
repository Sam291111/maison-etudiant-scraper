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
  const sources = [...new Set(listings.map((row) => row.source))].sort();
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source;
    option.textContent = source;
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

  const sourceColors = {
    immojeune: "#c65b36",
    la_carte_des_colocs: "#0d6b66",
    location_etudiant: "#5f7d2b",
    studapart: "#5a4db2",
  };
  const mapView = createMap(sourceColors);

  let sortKey = "price_eur";
  let sortDirection = "asc";

  function filteredRows() {
    const query = searchInput.value.trim().toLowerCase();
    const source = sourceFilter.value;
    const status = statusFilter.value;

    return listings.filter((row) => {
      if (source && row.source !== source) return false;
      if (status && safe(row.latest_status).toLowerCase() !== status) return false;
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

  searchInput.addEventListener("input", render);
  sourceFilter.addEventListener("change", render);
  statusFilter.addEventListener("change", render);
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
    setSummary(metadata);
    renderChanges(newRows, removedRows);
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
