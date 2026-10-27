const LOCAL_STATE_SOURCES = [
  './data/us-states.geojson',
  './data/us-states.json',
  'data/us-states.geojson',
  'data/us-states.json',
  '/apps/web/data/us-states.geojson',
];

const EXCLUDED_STATE_CODES = new Set(['PR']);
const NON_RENDERED_STATE_CODES = new Set(['AK', 'HI']);
const FALLBACK_STATE_NAMES = {
  DC: 'District of Columbia',
};

const stateNameToCode = {};

const svg = document.getElementById('us-map');
const selectedEl = document.getElementById('selected');
const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const form = document.getElementById('lookup-form');
const addressInput = document.getElementById('address');
const suggestionsEl = document.getElementById('address-suggestions');
const marketSummaryEl = document.getElementById('market-summary');
const marketListEl = document.getElementById('market-list');
const electionFiltersEl = document.getElementById('election-filters');
const seatFiltersEl = document.getElementById('seat-filters');
let selectedStateCode = null;
let suggestionsAbortController = null;
let suggestionRequestId = 0;
let stateMarketIndex = {};
let activeElectionTypes = new Set();
let activeSeatTypes = new Set();
let availableElectionTypes = [];
let availableSeatTypes = [];
let stateNameEntries = [];
let renderedStateCodes = new Set();

function createSvgElement(tagName) {
  return document.createElementNS('http://www.w3.org/2000/svg', tagName);
}

function clearSvg() {
  while (svg.firstChild) {
    svg.removeChild(svg.firstChild);
  }
}

async function fetchJsonWithFallback(sources) {
  for (const source of sources) {
    try {
      const response = await fetch(source);
      if (!response.ok) {
        continue;
      }

      return {
        data: await response.json(),
        source,
      };
    } catch {
      // Try the next candidate.
    }
  }

  throw new Error(`Unable to load any JSON source from: ${sources.join(', ')}`);
}

function getFeatureProperty(feature, names) {
  const properties = feature?.properties || {};
  for (const name of names) {
    if (properties[name] !== undefined && properties[name] !== null && properties[name] !== '') {
      return String(properties[name]);
    }
  }

  return null;
}

function normalizeStateFeature(feature) {
  const stateCode = getFeatureProperty(feature, ['STATE_ABBR', 'STUSPS', 'stateCode']);
  if (!stateCode || EXCLUDED_STATE_CODES.has(stateCode)) {
    return null;
  }

  const stateName = getFeatureProperty(feature, ['STATE_NAME', 'NAME', 'stateName']) || FALLBACK_STATE_NAMES[stateCode] || stateCode;

  return {
    ...feature,
    properties: {
      ...feature.properties,
      stateCode,
      stateName,
    },
  };
}

function albersUsaLower48Projection(lon, lat) {
  const lambda = (lon * Math.PI) / 180;
  const phi = (lat * Math.PI) / 180;
  const phi1 = (29.5 * Math.PI) / 180;
  const phi2 = (45.5 * Math.PI) / 180;
  const phi0 = (23 * Math.PI) / 180;
  const lambda0 = (-96 * Math.PI) / 180;

  const n = 0.5 * (Math.sin(phi1) + Math.sin(phi2));
  const c = Math.cos(phi1) ** 2 + 2 * n * Math.sin(phi1);
  const rho0 = Math.sqrt(c - 2 * n * Math.sin(phi0)) / n;
  const rho = Math.sqrt(c - 2 * n * Math.sin(phi)) / n;
  const theta = n * (lambda - lambda0);

  return {
    x: rho * Math.sin(theta),
    y: rho0 - rho * Math.cos(theta),
  };
}

function eachCoordinate(geometry, callback) {
  if (!geometry) return;

  const visitRingSet = (ringSet) => {
    ringSet.forEach((ring) => {
      ring.forEach(([lon, lat]) => callback(lon, lat));
    });
  };

  if (geometry.type === 'Polygon') {
    visitRingSet(geometry.coordinates);
    return;
  }

  if (geometry.type === 'MultiPolygon') {
    geometry.coordinates.forEach(visitRingSet);
  }
}

function buildProjector(features, width, height, padding = 24) {
  const projectedPoints = [];

  features.forEach((feature) => {
    eachCoordinate(feature.geometry, (lon, lat) => {
      projectedPoints.push(albersUsaLower48Projection(lon, lat));
    });
  });

  const minX = Math.min(...projectedPoints.map((point) => point.x));
  const maxX = Math.max(...projectedPoints.map((point) => point.x));
  const minY = Math.min(...projectedPoints.map((point) => point.y));
  const maxY = Math.max(...projectedPoints.map((point) => point.y));
  const scale = Math.min(
    (width - padding * 2) / (maxX - minX),
    (height - padding * 2) / (maxY - minY),
  );

  return (lon, lat) => {
    const projected = albersUsaLower48Projection(lon, lat);
    return {
      x: padding + (projected.x - minX) * scale,
      y: height - padding - (projected.y - minY) * scale,
    };
  };
}

function ringToPath(ring, project) {
  return ring
    .map(([lon, lat], index) => {
      const point = project(lon, lat);
      return `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`;
    })
    .join(' ') + ' Z';
}

function geometryToPath(geometry, project) {
  if (!geometry) return '';

  if (geometry.type === 'Polygon') {
    return geometry.coordinates.map((ring) => ringToPath(ring, project)).join(' ');
  }

  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates
      .map((polygon) => polygon.map((ring) => ringToPath(ring, project)).join(' '))
      .join(' ');
  }

  return '';
}

function computeVisualCentroid(feature, project) {
  let sumX = 0;
  let sumY = 0;
  let count = 0;

  eachCoordinate(feature.geometry, (lon, lat) => {
    const point = project(lon, lat);
    sumX += point.x;
    sumY += point.y;
    count += 1;
  });

  if (!count) {
    return null;
  }

  return { x: sumX / count, y: sumY / count };
}

function normalizeSeatType(seatType = '') {
  const normalized = String(seatType).trim();
  if (!normalized) return normalized;

  if (/^statewide$/i.test(normalized) || /^[A-Z]{2}-statewide$/i.test(normalized)) {
    return 'Statewide';
  }

  if (/^us[-\s]sen(?:ator)?$/i.test(normalized) || /^[A-Z]{2}-sen(?:ator)?$/i.test(normalized)) {
    return 'US-SEN';
  }

  if (/^us[-\s](rep|del)$/i.test(normalized) || /^[A-Z]{2}-(rep|other)$/i.test(normalized)) {
    return 'US-REP';
  }

  if (/^state[-\s]sen$/i.test(normalized)) {
    return 'State-SEN';
  }

  if (/^state[-\s]rep$/i.test(normalized)) {
    return 'State-REP';
  }

  return normalized;
}

function formatOddsPercent(oddsPercent) {
  if (oddsPercent === null || oddsPercent === undefined || Number.isNaN(Number(oddsPercent))) {
    return 'N/A';
  }

  return `${Number(oddsPercent).toFixed(2)}%`;
}

function getFilteredMarketsForState(code) {
  const stateMarkets = stateMarketIndex[code] || [];
  return stateMarkets.filter((market) => activeElectionTypes.has(market.electionType) && activeSeatTypes.has(market.normalizedSeatType));
}

function stateHasMatchingMarkets(code) {
  return getFilteredMarketsForState(code).length > 0;
}

function refreshMapStateClasses() {
  document.querySelectorAll('.state').forEach((node) => {
    const code = node.dataset.code;
    const hasMatch = stateHasMatchingMarkets(code);
    node.classList.toggle('match', hasMatch);
    node.classList.toggle('no-match', !hasMatch);
    node.classList.toggle('selected', code === selectedStateCode);
  });
}

function renderMarketsForState(code) {
  const matchingMarkets = getFilteredMarketsForState(code);
  marketListEl.innerHTML = '';

  if (!matchingMarkets.length) {
    marketSummaryEl.textContent = `No winner-focused markets match the active filters for ${code}.`;
    return;
  }

  const elections = new Map();
  matchingMarkets.forEach((market) => {
    const groupKey = market.title;
    if (!elections.has(groupKey)) {
      elections.set(groupKey, {
        title: market.title,
        normalizedSeatType: market.normalizedSeatType,
        electionType: market.electionType,
        seatId: market.seatId,
        candidates: []
      });
    }

    elections.get(groupKey).candidates.push({
      entityName: market.entityName || 'Unknown',
      oddsPercent: market.oddsPercent,
      marketTicker: market.marketTicker,
      seriesTicker: market.seriesTicker
    });
  });

  marketSummaryEl.textContent = `${elections.size} election${elections.size === 1 ? '' : 's'} and ${matchingMarkets.length} candidate market${matchingMarkets.length === 1 ? '' : 's'} match the active filters for ${code}.`;

  [...elections.values()].forEach((election) => {
    const item = document.createElement('li');
    item.className = 'market-item';

    const candidates = election.candidates
      .sort((a, b) => (Number(b.oddsPercent) || 0) - (Number(a.oddsPercent) || 0))
      .map((candidate) => `
        <li>
          <strong>${candidate.entityName}</strong>: ${formatOddsPercent(candidate.oddsPercent)}
          <span class="candidate-market-meta">(${candidate.marketTicker})</span>
        </li>
      `)
      .join('');

    item.innerHTML = `
      <p class="market-title">${election.title}</p>
      <p class="market-meta">
        <span><strong>Seat Type:</strong> ${election.normalizedSeatType}</span>
        <span><strong>Election:</strong> ${election.electionType}</span>
        <span><strong>Seat ID:</strong> ${election.seatId || 'N/A'}</span>
      </p>
      <ul class="candidate-list">${candidates}</ul>
    `;
    marketListEl.append(item);
  });
}

function setSelected(code) {
  selectedStateCode = code;
  const name = stateNameEntries.find(([stateCode]) => stateCode === code)?.[1] || FALLBACK_STATE_NAMES[code];
  selectedEl.textContent = code ? `${name || code} (${code})` : 'None yet';
  refreshMapStateClasses();

  if (code) {
    renderMarketsForState(code);
  }
}

function buildFilterSection(containerEl, options, selectedValues, onChange, onToggleAll) {
  containerEl.innerHTML = '';

  if (!options.length) {
    const emptyState = document.createElement('span');
    emptyState.className = 'toggle-empty';
    emptyState.textContent = 'No filters available';
    containerEl.append(emptyState);
    return;
  }

  const controls = document.createElement('div');
  controls.className = 'toggle-controls';

  const selectAllButton = document.createElement('button');
  selectAllButton.type = 'button';
  selectAllButton.className = 'toggle-all-button';
  const allSelected = options.every((value) => selectedValues.has(value));
  selectAllButton.textContent = allSelected ? 'Unselect all' : 'Select all';
  selectAllButton.addEventListener('click', () => {
    onToggleAll(!allSelected);
  });

  controls.append(selectAllButton);
  containerEl.append(controls);

  options.forEach((value) => {
    const id = `${containerEl.id}-${value.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`;
    const wrapper = document.createElement('label');
    wrapper.className = 'toggle-item';
    wrapper.setAttribute('for', id);

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = id;
    checkbox.checked = selectedValues.has(value);
    checkbox.addEventListener('change', () => {
      onChange(value, checkbox.checked);
    });

    const text = document.createElement('span');
    text.textContent = value;

    wrapper.append(checkbox, text);
    containerEl.append(wrapper);
  });
}

function setFilterValue(setRef, value, isChecked) {
  if (isChecked) {
    setRef.add(value);
  } else {
    setRef.delete(value);
  }

  applyFilterState();
}

function setAllFilterValues(setRef, allValues, shouldSelectAll) {
  if (shouldSelectAll) {
    setRef.clear();
    allValues.forEach((value) => setRef.add(value));
  } else {
    setRef.clear();
  }

  applyFilterState();
}

function applyFilterState() {
  refreshMapStateClasses();
  if (selectedStateCode) {
    renderMarketsForState(selectedStateCode);
  } else {
    marketSummaryEl.textContent = 'Select a state to load relevant Kalshi markets.';
  }
}

function renderFilterSections() {
  buildFilterSection(electionFiltersEl, availableElectionTypes, activeElectionTypes, (value, isChecked) => {
    setFilterValue(activeElectionTypes, value, isChecked);
    renderFilterSections();
  }, (shouldSelectAll) => {
    setAllFilterValues(activeElectionTypes, availableElectionTypes, shouldSelectAll);
    renderFilterSections();
  });

  buildFilterSection(seatFiltersEl, availableSeatTypes, activeSeatTypes, (value, isChecked) => {
    setFilterValue(activeSeatTypes, value, isChecked);
    renderFilterSections();
  }, (shouldSelectAll) => {
    setAllFilterValues(activeSeatTypes, availableSeatTypes, shouldSelectAll);
    renderFilterSections();
  });
}

function initializeFilters() {
  const allMarkets = Object.values(stateMarketIndex).flat();
  availableElectionTypes = [...new Set(allMarkets.map((market) => market.electionType).filter(Boolean))].sort();

  const seatTypeOrder = ['Statewide', 'US-SEN', 'US-REP', 'State-SEN', 'State-REP'];
  availableSeatTypes = [...new Set(allMarkets.map((market) => market.normalizedSeatType).filter(Boolean))]
    .sort((a, b) => {
      const aIndex = seatTypeOrder.indexOf(a);
      const bIndex = seatTypeOrder.indexOf(b);
      if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
      if (aIndex === -1) return 1;
      if (bIndex === -1) return -1;
      return aIndex - bIndex;
    });

  activeElectionTypes = new Set(availableElectionTypes);
  activeSeatTypes = new Set(availableSeatTypes);

  renderFilterSections();
}

function buildStateNameIndex(features) {
  stateNameEntries = features.map((feature) => [feature.properties.stateCode, feature.properties.stateName]);
  stateNameEntries.forEach(([code, name]) => {
    stateNameToCode[name.toLowerCase()] = code;
  });
  Object.entries(FALLBACK_STATE_NAMES).forEach(([code, name]) => {
    stateNameToCode[name.toLowerCase()] = code;
  });
}

function renderStateMap(stateFeatures, source) {
  clearSvg();

  const viewBox = svg.viewBox.baseVal;
  const renderedFeatures = stateFeatures.filter((feature) => !NON_RENDERED_STATE_CODES.has(feature.properties.stateCode));
  const project = buildProjector(renderedFeatures, viewBox.width, viewBox.height);
  renderedStateCodes = new Set(renderedFeatures.map((feature) => feature.properties.stateCode));

  const stateLayer = createSvgElement('g');
  stateLayer.setAttribute('aria-label', 'State borders');
  svg.appendChild(stateLayer);

  const labelLayer = createSvgElement('g');
  labelLayer.setAttribute('aria-label', 'State labels');
  svg.appendChild(labelLayer);

  renderedFeatures.forEach((feature) => {
    const stateCode = feature.properties.stateCode;
    const path = createSvgElement('path');
    path.setAttribute('class', 'state no-match');
    path.setAttribute('d', geometryToPath(feature.geometry, project));
    path.dataset.code = stateCode;
    path.dataset.name = feature.properties.stateName;
    path.addEventListener('click', () => {
      statusEl.textContent = '';
      resultEl.textContent = '';
      setSelected(stateCode);
    });
    stateLayer.append(path);

    const centroid = computeVisualCentroid(feature, project);
    if (centroid) {
      const label = createSvgElement('text');
      label.setAttribute('x', centroid.x.toFixed(2));
      label.setAttribute('y', centroid.y.toFixed(2));
      label.setAttribute('class', 'label');
      label.textContent = stateCode;
      labelLayer.append(label);
    }
  });

  resultEl.textContent = `Rendered ${renderedFeatures.length} state outlines from ${source}.`;
  refreshMapStateClasses();
}

function clearSuggestions() {
  suggestionsEl.innerHTML = '';
}

async function updateAddressSuggestions(query) {
  const trimmedQuery = query.trim();
  if (trimmedQuery.length < 3) {
    clearSuggestions();
    return;
  }

  if (suggestionsAbortController) {
    suggestionsAbortController.abort();
  }

  const requestId = ++suggestionRequestId;
  suggestionsAbortController = new AbortController();

  try {
    const params = new URLSearchParams({
      q: trimmedQuery,
      format: 'jsonv2',
      countrycodes: 'us',
      addressdetails: '1',
      limit: '5'
    });
    const response = await fetch(`https://nominatim.openstreetmap.org/search?${params.toString()}`, {
      signal: suggestionsAbortController.signal
    });
    if (!response.ok) throw new Error(`Suggestion lookup failed with status ${response.status}`);
    const data = await response.json();

    if (requestId !== suggestionRequestId) return;

    const values = [...new Set(data.map((entry) => entry.display_name).filter(Boolean))];
    suggestionsEl.innerHTML = '';
    values.forEach((value) => {
      const option = document.createElement('option');
      option.value = value;
      suggestionsEl.append(option);
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return;
    }
    clearSuggestions();
  }
}

let suggestionTimeout = null;
addressInput.addEventListener('input', () => {
  if (suggestionTimeout) {
    window.clearTimeout(suggestionTimeout);
  }

  suggestionTimeout = window.setTimeout(() => {
    updateAddressSuggestions(addressInput.value);
  }, 250);
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  statusEl.textContent = '';
  resultEl.textContent = '';

  const address = addressInput.value.trim();
  if (!address) {
    statusEl.textContent = 'Please enter an address before searching.';
    return;
  }

  try {
    const params = new URLSearchParams({ q: address, format: 'jsonv2', countrycodes: 'us', addressdetails: '1', limit: '1' });
    const response = await fetch(`https://nominatim.openstreetmap.org/search?${params.toString()}`);
    if (!response.ok) throw new Error(`Lookup failed with status ${response.status}`);
    const data = await response.json();

    if (!data.length) {
      statusEl.textContent = 'No U.S. result found for that address.';
      return;
    }

    const match = data[0];
    const stateName = match.address?.state?.toLowerCase();
    const code = stateNameToCode[stateName];
    if (!code) {
      statusEl.textContent = 'Address found, but no state match could be resolved.';
      return;
    }

    setSelected(code);

    if (!renderedStateCodes.has(code)) {
      statusEl.textContent = `${code} was resolved from the address, but only the contiguous U.S. + DC are currently drawn on the map.`;
    }

    resultEl.textContent = `Matched ${match.display_name} → ${code} (${Number(match.lat).toFixed(4)}, ${Number(match.lon).toFixed(4)})`;
  } catch (error) {
    statusEl.textContent = error instanceof Error ? error.message : 'Unexpected lookup error.';
  }
});

async function loadMarketIndex() {
  const candidateUrls = [
    './data/state-election-markets.json',
    'data/state-election-markets.json',
    '/data/state-election-markets.json',
    '/apps/web/data/state-election-markets.json'
  ];

  const loadJsonFromCandidates = async () => {
    for (const url of candidateUrls) {
      try {
        const response = await fetch(url);
        if (!response.ok) continue;
        return await response.json();
      } catch {
        // Try next candidate path.
      }
    }

    throw new Error('Market index load failed for all known paths.');
  };

  const normalizeMarket = (market = {}) => {
    const seatType = market.seatType || market.seat_type || 'Unknown';
    const electionType = market.electionType || market.election_type || 'Unknown';
    const oddsPercent = market.oddsPercent ?? market.odds_percent;

    return {
      ...market,
      seatType,
      electionType,
      oddsPercent: oddsPercent === null || oddsPercent === undefined ? null : Number(oddsPercent),
      entityName: market.entityName || market.entity_name || market.yes_sub_title || 'Unknown',
      normalizedSeatType: normalizeSeatType(seatType)
    };
  };

  try {
    const payload = await loadJsonFromCandidates();
    const rawStateMarkets = payload.stateMarkets || payload.state_markets || {};

    stateMarketIndex = Object.fromEntries(
      Object.entries(rawStateMarkets).map(([stateCode, markets]) => [
        stateCode,
        Array.isArray(markets) ? markets.map((market) => normalizeMarket(market)) : []
      ])
    );

    initializeFilters();
    refreshMapStateClasses();

    const totalMarkets = Object.values(stateMarketIndex).reduce((sum, markets) => sum + markets.length, 0);
    marketSummaryEl.textContent = totalMarkets > 0
      ? 'Select a state to load relevant Kalshi markets.'
      : 'No market data is available. Verify the state market index JSON contains markets.';
  } catch {
    marketSummaryEl.textContent = 'Unable to load state market index.';
  }
}

async function initializeApp() {
  try {
    const payload = await fetchJsonWithFallback(LOCAL_STATE_SOURCES);
    const stateFeatures = (payload.data.features || []).map(normalizeStateFeature).filter(Boolean);
    if (!stateFeatures.length) {
      throw new Error('State geometry loaded, but no features were available to render.');
    }

    buildStateNameIndex(stateFeatures);
    renderStateMap(stateFeatures, payload.source);
  } catch (error) {
    statusEl.textContent = error instanceof Error ? error.message : 'Unable to load state borders.';
  }

  await loadMarketIndex();
}

initializeApp();
