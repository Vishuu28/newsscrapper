const form = document.getElementById("searchForm");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const submitBtn = document.getElementById("submitBtn");
const btnLabel = submitBtn.querySelector(".btn-label");
const btnSpinner = submitBtn.querySelector(".btn-spinner");
const countryEl = document.getElementById("country");
const regionEl = document.getElementById("region");
const cityEl = document.getElementById("city");
const filtersDataEl = document.getElementById("regionCityFilters");
const regionCityFilters = filtersDataEl ? JSON.parse(filtersDataEl.textContent || "{}") : {};

function fillSelect(selectEl, options, defaultText) {
  selectEl.innerHTML = `<option value="">${defaultText}</option>`;
  for (const option of options || []) {
    const opt = document.createElement("option");
    opt.value = option;
    opt.textContent = option;
    selectEl.appendChild(opt);
  }
}

function updateLocationFilters() {
  const country = countryEl.value;
  const cfg = regionCityFilters[country] || { regions: [], cities: [] };
  const regionNames = (cfg.regions || []).map((r) => r.name);
  fillSelect(regionEl, regionNames, "No region filter");
  fillSelect(cityEl, cfg.cities || [], "No city filter");
}

function updateCityByRegion() {
  const country = countryEl.value;
  const region = regionEl.value;
  const cfg = regionCityFilters[country] || { regions: [], cities: [] };
  if (!region) {
    fillSelect(cityEl, cfg.cities || [], "No city filter");
    return;
  }
  const selectedRegion = (cfg.regions || []).find((r) => r.name === region);
  fillSelect(cityEl, selectedRegion ? selectedRegion.cities : [], "No city filter");
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  btnSpinner.hidden = !isLoading;
  if (isLoading) {
    statusEl.className = "status is-busy";
    statusEl.textContent = "Fetching and ranking articles…";
    resultsEl.innerHTML = skeletonBlock();
  }
}

function skeletonBlock() {
  return [1, 2, 3]
    .map(
      () => `
    <div class="skeleton" aria-hidden="true">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
      <div class="skeleton-line short"></div>
    </div>
  `
    )
    .join("");
}

function renderResults(items) {
  if (!items.length) {
    resultsEl.innerHTML =
      '<div class="empty-state">No articles matched. Try <strong>Broader pool</strong>, a longer time window, <strong>Any / no trend</strong>, fewer exclude words, or different must-include keywords.</div>';
    return;
  }

  resultsEl.innerHTML = items
    .map(
      (item) => `
      <article class="item">
        <div class="item-header">
          <h3><a href="${escapeAttr(item.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></h3>
          ${
            typeof item.relevance === "number"
              ? `<span class="score-pill" title="Relevance score">Match ${item.relevance}</span>`
              : ""
          }
        </div>
        <div class="meta">
          <span>${escapeHtml(item.source || "Unknown")}</span>
          <span>${escapeHtml(item.published || "N/A")}</span>
        </div>
        <p>${escapeHtml(item.summary || "Summary unavailable.")}</p>
      </article>
    `
    )
    .join("");
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/'/g, "&#39;");
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setLoading(true);

  const payload = {
    country: countryEl.value,
    language_mode: document.getElementById("language_mode").value,
    index: document.getElementById("index").value,
    trend: document.getElementById("trend").value,
    duration: document.getElementById("duration").value,
    region: regionEl.value,
    city: cityEl.value,
    keywords: document.getElementById("keywords").value.trim(),
    exclude: document.getElementById("exclude").value.trim(),
    max_results: Number.parseInt(document.getElementById("max_results").value, 10) || 28,
    strict: document.getElementById("strict").checked,
    broaden: document.getElementById("broaden").checked
  };

  try {
    const response = await fetch("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Request failed.");
    }

    statusEl.className = "status is-ok";
    statusEl.textContent = `Showing ${data.count} ranked article(s).`;
    renderResults(data.results);
  } catch (error) {
    statusEl.className = "status is-error";
    statusEl.textContent = `Error: ${error.message}`;
    resultsEl.innerHTML = "";
  } finally {
    setLoading(false);
  }
});

countryEl.addEventListener("change", updateLocationFilters);
regionEl.addEventListener("change", updateCityByRegion);
updateLocationFilters();
