import {
  buildKalshiCandidateLookup,
  matchCandidateToKalshi,
  normalizeName as normalizeKalshiName,
  normalizePartyCode as normalizeSharedPartyCode,
} from './kalshi-candidate-match.js';

const LOCAL_DISTRICT_SOURCES = [
  './data/congressional-districts.geojson',
  './data/congressional-districts.json',
];

const LOCAL_STATE_SOURCES = [
  './data/us-states.geojson',
  './data/us-states.json',
];

const REMOTE_DISTRICT_SOURCE =
  'https://services7.arcgis.com/F4iYwOOvXLYhkPXF/arcgis/rest/services/Congressional_Districts_118th_final/FeatureServer/257/query?where=STATE_ABBR%20NOT%20IN%20(%27AK%27%2C%27HI%27%2C%27PR%27)&outFields=STATE_ABBR,DISTRICT,NAME,GEOID&returnGeometry=true&f=geojson';

const REMOTE_STATE_SOURCE =
  'https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_States_Generalized/FeatureServer/0/query?where=STATE_ABBR%20NOT%20IN%20(%27AK%27%2C%27HI%27%2C%27PR%27)&outFields=STATE_ABBR,STATE_NAME&returnGeometry=true&f=geojson';

const EXCLUDED_STATES = new Set(['AK', 'HI', 'PR']);

const svg = document.getElementById('district-map');
const statusEl = document.getElementById('district-map-status');
const sourceEl = document.getElementById('district-map-source');
const selectedEl = document.getElementById('district-selected');
const metaEl = document.getElementById('district-meta');
const electionSummaryEl = document.getElementById('district-election-summary');
const candidateGroupsEl = document.getElementById('district-candidate-groups');
const marketSummaryEl = document.getElementById('district-market-summary');
const marketListEl = document.getElementById('district-market-list');
const selectionHintEl = document.getElementById('district-selection-hint');
const colorSchemeSelectEl = document.getElementById('district-color-scheme');
const colorSchemeDescriptionEl = document.getElementById('district-color-scheme-description');
const detailViewSelectEl = document.getElementById('district-detail-view');
const electionViewSelectEl = document.getElementById('district-election-view');

const LOCAL_HOUSE_MARKET_INDEX_SOURCES = [
  './data/us-house-market-index.json',
  './data/us-house-market-index.json',
];

const LOCAL_HOUSE_ELECTION_SOURCES = [
  './data/us-house-seats.json',
];

// Derived election-view data is intended for UI presentation fields such as
// displayCandidates and primaryElections.
const LOCAL_HOUSE_ELECTION_VIEW_SOURCES = [
  './data/us-house-election-view.json',
];

const LOCAL_HOUSE_BALLOTPEDIA_SOURCES = [
  './data/us-house-ballotpedia.json',
];

const CONTENTION_STYLES = {
  no_election: { fill: '#ffffff', hover: '#f8fafc', pinned: '#e2e8f0' },
  uncontested: { fill: '#cbd5e1', hover: '#94a3b8', pinned: '#64748b' },
  contested_primary_only_dem: { fill: '#93c5fd', hover: '#60a5fa', pinned: '#2563eb' },
  contested_primary_only_rep: { fill: '#fca5a5', hover: '#f87171', pinned: '#dc2626' },
  contested_primary_only_other: { fill: '#bbf7d0', hover: '#86efac', pinned: '#16a34a' },
  contested: { fill: '#d8b4fe', hover: '#c084fc', pinned: '#9333ea' },
};

const INCUMBENT_STYLES = {
  DEM: { fill: '#93c5fd', hover: '#60a5fa', pinned: '#2563eb' },
  REP: { fill: '#fca5a5', hover: '#f87171', pinned: '#dc2626' },
  IND: { fill: '#d8b4fe', hover: '#c084fc', pinned: '#9333ea' },
  LIB: { fill: '#fde68a', hover: '#fcd34d', pinned: '#d97706' },
  GRN: { fill: '#86efac', hover: '#4ade80', pinned: '#16a34a' },
  OTH: { fill: '#bbf7d0', hover: '#86efac', pinned: '#16a34a' },
};

const MARKET_ODDS_STYLES = {
  DEM: { fill: '#93c5fd', hover: '#60a5fa', pinned: '#2563eb' },
  REP: { fill: '#fca5a5', hover: '#f87171', pinned: '#dc2626' },
  IND: { fill: '#d8b4fe', hover: '#c084fc', pinned: '#9333ea' },
  LIB: { fill: '#fde68a', hover: '#fcd34d', pinned: '#d97706' },
  GRN: { fill: '#86efac', hover: '#4ade80', pinned: '#16a34a' },
  OTH: { fill: '#bbf7d0', hover: '#86efac', pinned: '#16a34a' },
  NO_MARKET: { fill: '#e5e7eb', hover: '#d1d5db', pinned: '#9ca3af' },
  ISSUE: { fill: '#fde68a', hover: '#fcd34d', pinned: '#d97706' },
  PRIMARY_ONLY: { fill: '#86efac', hover: '#4ade80', pinned: '#16a34a' },
};

const PRIMARY_STYLES = {
  DEM: { fill: '#93c5fd', hover: '#60a5fa', pinned: '#2563eb' },
  REP: { fill: '#fca5a5', hover: '#f87171', pinned: '#dc2626' },
  OTH: { fill: '#bbf7d0', hover: '#86efac', pinned: '#16a34a' },
  MULTI: { fill: '#d8b4fe', hover: '#c084fc', pinned: '#9333ea' },
  NO_MARKET: { fill: '#e5e7eb', hover: '#d1d5db', pinned: '#9ca3af' },
};

const COLOR_SCHEME_LABELS = {
  contention: 'Contention colors districts by how competitive the current race is.',
  incumbents: "Incumbents colors districts by the incumbent's party, falling back to Contention when a seat has no incumbent.",
  market_odds: 'Market Odds colors districts by the Kalshi favorite, using grey for no market coverage, green for primary-only coverage, and yellow when a general-election favorite cannot be resolved.',
  primary: 'Primary colors districts by which party has a Kalshi primary market, and uses purple when multiple parties have primary markets in the same district.',
};

const PARTY_NAME_BY_CODE = {
  AIP: 'American Independent',
  DEM: 'Democratic',
  DFL: 'Democratic-Farmer-Labor',
  GRE: 'Green',
  GRN: 'Green',
  IND: 'Independent',
  LIB: 'Libertarian',
  NPA: 'No Party Affiliation',
  OTH: 'Other',
  OWN: 'Other',
  REP: 'Republican',
};

let activeColorScheme = 'contention';
let activeElectionView = 'general';

function createSvgElement(tagName) {
  return document.createElementNS('http://www.w3.org/2000/svg', tagName);
}

function setStatus(message, { error = false } = {}) {
  statusEl.textContent = message;
  statusEl.classList.toggle('status-message--neutral', !error);
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
        isRemote: source.startsWith('http'),
      };
    } catch (error) {
      // Try the next source.
    }
  }

  throw new Error(`Unable to load any GIS source from: ${sources.join(', ')}`);
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

function normalizeDistrictFeature(feature) {
  const stateCode = getFeatureProperty(feature, ['STATE_ABBR', 'STUSPS', 'stateCode']);
  const districtRaw = getFeatureProperty(feature, ['DISTRICT', 'CDFP', 'districtCode']) || '';

  if (!stateCode || EXCLUDED_STATES.has(stateCode)) {
    return null;
  }

  const districtCode = districtRaw.toUpperCase() === 'AL'
    ? 'AL'
    : String(Number.parseInt(districtRaw, 10)).padStart(2, '0');

  return {
    ...feature,
    properties: {
      ...feature.properties,
      stateCode,
      districtCode,
      districtName:
        getFeatureProperty(feature, ['NAME', 'NAMELSAD', 'districtName']) ||
        `${stateCode}-${districtCode}`,
      districtLabel: districtCode === 'AL' ? `${stateCode} At-Large` : `${stateCode}-${districtCode}`,
      geoid: getFeatureProperty(feature, ['GEOID', 'geoid']),
    },
  };
}

function normalizeStateFeature(feature) {
  const stateCode = getFeatureProperty(feature, ['STATE_ABBR', 'STUSPS', 'stateCode']);
  if (!stateCode || EXCLUDED_STATES.has(stateCode)) {
    return null;
  }

  return {
    ...feature,
    properties: {
      ...feature.properties,
      stateCode,
      stateName: getFeatureProperty(feature, ['STATE_NAME', 'NAME', 'stateName']) || stateCode,
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

function formatOddsPercent(oddsPercent) {
  if (oddsPercent === null || oddsPercent === undefined || Number.isNaN(Number(oddsPercent))) {
    return 'N/A';
  }

  return `${Number(oddsPercent).toFixed(2)}%`;
}

function normalizeKalshiPartyCode(partyCode = '') {
  const normalized = normalizeSharedPartyCode(partyCode);
  if (normalized === 'GRE') return 'GRN';
  return normalized || '';
}

function normalizePartyCode(value = '') {
  const normalized = normalizeSharedPartyCode(value);
  if (normalized === 'GRE') return 'GRN';
  return normalized || '';
}

function formatKalshiMarketMeta(oddsPercent, marketTicker, status) {
  const parts = [];
  if (oddsPercent !== null && oddsPercent !== undefined && !Number.isNaN(Number(oddsPercent))) {
    parts.push(formatOddsPercent(oddsPercent));
  }

  const detailBits = [marketTicker, status].filter(Boolean);
  if (detailBits.length) {
    parts.push(`(${detailBits.join(' · ')})`);
  }

  return parts.join(' ');
}

function formatDistrictMarketType(marketType = '') {
  const normalized = String(marketType || '').trim();
  if (!normalized) {
    return '';
  }

  if (normalized === 'party_winner' || normalized === 'district_winner') {
    return 'District Winner';
  }

  return normalized
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function getSeriesElectionLabel(series) {
  const representativeMarket = series.markets.find(Boolean) || null;
  const electionCycle = series.markets.find((market) => market.electionCycle)?.electionCycle;
  const electionType = String(representativeMarket?.electionType || '').toLowerCase() === 'primary' ? 'Primary' : 'General';
  const partyCode = normalizeKalshiPartyCode(series.party);
  const partySuffix = electionType === 'Primary' && partyCode ? ` (${partyCode})` : '';
  return electionCycle ? `${electionCycle} ${electionType}${partySuffix}` : `${electionType}${partySuffix}`;
}

function formatDistrictSeriesTitle(series, districtMarketRecord) {
  return `${getSeriesElectionLabel(series)} - US-REP - ${districtMarketRecord.seatId}`;
}

function getDistrictElectionGroupKey(market) {
  const normalizedContestKey = String(market?.normalizedContestKey || '').trim();
  if (normalizedContestKey) {
    return normalizedContestKey;
  }

  const eventTicker = String(market?.eventTicker || market?.childElection?.ticker || '').trim();
  if (eventTicker) {
    return eventTicker;
  }

  const fallbackBits = [
    market?.seriesTicker,
    market?.electionType,
    market?.party,
    market?.seatId,
  ]
    .map((value) => String(value || '').trim())
    .filter(Boolean);

  return fallbackBits.join(':') || String(market?.marketTicker || '').trim();
}

function getElectionViewLabel(electionView = getActiveElectionView()) {
  return electionView === 'primary' ? 'primary' : 'general election';
}

function getElectionViewTitle(electionView = getActiveElectionView()) {
  return electionView === 'primary' ? 'Primary' : 'General Election';
}

function getCandidateMarketLabel(electionView = getActiveElectionView()) {
  return electionView === 'primary' ? 'Primary market' : 'General market';
}

function getPartyMarketLabel(electionView = getActiveElectionView()) {
  return electionView === 'primary' ? 'Primary party market' : 'General party market';
}

function getActiveDetailView() {
  return detailViewSelectEl?.value === 'party' ? 'party' : 'candidate';
}

function buildDistrictLookupKey({ stateCode, districtCode }) {
  if (!stateCode || !districtCode) {
    return '';
  }

  const normalizedDistrictCode = String(districtCode).trim().toUpperCase() === 'AL'
    ? 'AL'
    : String(Number.parseInt(districtCode, 10)).padStart(2, '0');

  return `${String(stateCode).trim().toUpperCase()}-${normalizedDistrictCode}`;
}

function getDistrictSeatKey(feature) {
  return buildDistrictLookupKey(feature.properties);
}

function buildElectionViewSeatLookupKey(seat = {}) {
  const key = buildDistrictLookupKey(seat);
  const rawSeatId = String(seat?.seatId || '').trim();

  if (rawSeatId && key && rawSeatId !== key) {
    throw new Error(`Election view seat ${rawSeatId} does not match derived district lookup key ${key}.`);
  }

  return key || rawSeatId;
}

function clearElectionDisplay() {
  electionSummaryEl.textContent = 'Official 2026 filing data will appear here for the selected district.';
  candidateGroupsEl.innerHTML = '';
}

function clearMarketDisplay() {
  marketSummaryEl.textContent = 'Kalshi data will appear here for the selected district.';
  marketListEl.innerHTML = '';
}

function clearDistrictSelection(pathLookup, message = 'Hover over or click the map to inspect a congressional district.') {
  pathLookup.forEach((path) => {
    path.classList.remove('is-active', 'is-pinned');
    path.setAttribute('aria-pressed', 'false');
  });

  selectedEl.textContent = 'None yet';
  metaEl.textContent = message;
  selectionHintEl.textContent = 'Hover previews a district. Click to pin it for full viewing; click the same district again to release it.';
  clearElectionDisplay();
  clearMarketDisplay();
}

function isIncumbentCandidate(candidate) {
  return candidate?.incumbentStatus === 'INCUMBENT';
}

function getPartyName(partyCode = '', fallbackName = '') {
  const normalized = normalizePartyCode(partyCode);
  return PARTY_NAME_BY_CODE[normalized] || fallbackName || normalized || 'Other';
}

function parseBallotpediaCandidateLine(line = '') {
  const raw = String(line || '').trim();
  if (!raw || raw.startsWith('[')) {
    return null;
  }

  const partyMatch = raw.match(/\(([^()]+)\)\s*$/);
  const partyLabel = partyMatch ? partyMatch[1] : '';
  const normalizedPartyLabel = partyLabel.toLowerCase();
  const partyCode = normalizedPartyLabel.includes('dem')
    ? 'DEM'
    : normalizedPartyLabel.includes('rep')
      ? 'REP'
      : normalizedPartyLabel.includes('lib')
        ? 'LIB'
        : normalizedPartyLabel.includes('green')
          ? 'GRN'
          : normalizedPartyLabel.includes('independent')
            ? 'IND'
            : normalizedPartyLabel.includes('no party')
              ? 'NPA'
              : 'OTH';

  return {
    partyCode,
    partyName: getPartyName(partyCode, partyLabel || 'Other'),
  };
}

function buildBallotpediaPartyCounts(ballotpediaRecord) {
  const counts = new Map();
  const ballotpedia = ballotpediaRecord?.election?.ballotpedia || {};
  const primarySections = ballotpedia.primaryCandidateSections || {};

  Object.entries(primarySections).forEach(([partyLabel, candidates]) => {
    const partyCandidate = parseBallotpediaCandidateLine(`Placeholder (${partyLabel})`) || {
      partyCode: 'OTH',
      partyName: partyLabel,
    };
    const partyCode = normalizePartyCode(partyCandidate.partyCode);
    const filteredCandidates = Array.isArray(candidates)
      ? candidates.filter((candidate) => parseBallotpediaCandidateLine(candidate))
      : [];
    counts.set(partyCode, {
      partyCode,
      partyName: getPartyName(partyCode, partyLabel),
      count: filteredCandidates.length,
    });
  });

  const lines = ballotpedia.generalElectionCandidateLines || [];
  lines.forEach((line) => {
    const candidate = parseBallotpediaCandidateLine(line);
    if (!candidate) {
      return;
    }
    const partyCode = normalizePartyCode(candidate.partyCode);
    const current = counts.get(partyCode) || { partyCode, partyName: candidate.partyName, count: 0 };
    current.count = Math.max(current.count, 1);
    counts.set(partyCode, current);
  });
  return counts;
}

const KALSHI_FIRST_NAME_VARIANT_GROUPS = [
  ['alex', 'alexander', 'alexandra'],
  ['andy', 'andrew'],
  ['ben', 'benjamin'],
  ['beth', 'elizabeth', 'liz', 'lizzie', 'lizzy'],
  ['bob', 'bobby', 'robert', 'rob', 'robbie'],
  ['brad', 'bradley'],
  ['cal', 'calvin'],
  ['chris', 'christian', 'christopher'],
  ['dan', 'daniel', 'danny'],
  ['dave', 'david'],
  ['ed', 'eddie', 'edward'],
  ['jeff', 'jeffery', 'jeffrey'],
  ['jim', 'jimmy', 'james'],
  ['joe', 'joey', 'joseph'],
  ['jon', 'jonathan', 'john'],
  ['kate', 'katherine', 'kathryn', 'katie', 'kat'],
  ['maggie', 'margaret', 'meg', 'megan'],
  ['matt', 'matthew'],
  ['mike', 'michael'],
  ['pat', 'patrick', 'patricia'],
  ['rick', 'richard', 'ricky'],
  ['sam', 'sammy', 'samuel', 'samantha'],
  ['steve', 'steven', 'stephen'],
  ['sue', 'susan', 'susanna', 'susanne'],
  ['tom', 'thomas', 'tommy'],
  ['tony', 'anthony'],
  ['will', 'william', 'willy', 'bill', 'billy'],
];

const KALSHI_FIRST_NAME_VARIANTS = KALSHI_FIRST_NAME_VARIANT_GROUPS.reduce((lookup, group) => {
  group.forEach((name) => {
    lookup.set(name, new Set(group));
  });
  return lookup;
}, new Map());

function tokenizeKalshiName(value = '') {
  return normalizeKalshiName(value)
    .split(' ')
    .filter(Boolean);
}

function firstNameMatches(candidateFirst, marketFirst) {
  const left = normalizeKalshiName(candidateFirst);
  const right = normalizeKalshiName(marketFirst);
  if (!left || !right) {
    return false;
  }

  if (left === right) {
    return true;
  }

  if (left[0] === right[0] && (left.length === 1 || right.length === 1)) {
    return true;
  }

  if (left.length >= 3 && right.length >= 3) {
    if (left.startsWith(right) || right.startsWith(left)) {
      return true;
    }
  }

  return KALSHI_FIRST_NAME_VARIANTS.get(left)?.has(right) || KALSHI_FIRST_NAME_VARIANTS.get(right)?.has(left) || false;
}

function stripMiddleNameTokens(tokens = []) {
  if (tokens.length <= 2) {
    return [...tokens];
  }

  return [tokens[0], tokens[tokens.length - 1]];
}

function buildCandidateKalshiLookupKey(candidate = {}) {
  const candidateId = String(candidate?.candidateId || '').trim();
  if (candidateId) {
    return `id:${candidateId}`;
  }

  const normalizedName = normalizeKalshiName(candidate?.kalshiName || candidate?.name || '');
  if (!normalizedName) {
    return '';
  }

  const partyCode = normalizeKalshiPartyCode(candidate?.partyCode || '');
  return `${partyCode || 'UNK'}:${normalizedName}`;
}

function scoreCandidateNameMatch(candidateName, marketName) {
  const candidateTokens = tokenizeKalshiName(candidateName);
  const marketTokens = tokenizeKalshiName(marketName);
  if (!candidateTokens.length || !marketTokens.length) {
    return 0;
  }

  const candidateNormalized = candidateTokens.join(' ');
  const marketNormalized = marketTokens.join(' ');
  if (candidateNormalized === marketNormalized) {
    return 100;
  }

  const candidateLast = candidateTokens[candidateTokens.length - 1];
  const marketLast = marketTokens[marketTokens.length - 1];
  const candidateFirst = candidateTokens[0];
  const marketFirst = marketTokens[0];
  const sharedTokens = marketTokens.filter((token) => candidateTokens.includes(token));

  let score = 0;
  if (candidateLast && marketLast && candidateLast === marketLast) {
    score += 50;
  }
  if (firstNameMatches(candidateFirst, marketFirst)) {
    score += 25;
  }
  score += sharedTokens.length * 10;

  if (
    candidateLast
    && marketLast
    && candidateLast === marketLast
    && (
      firstNameMatches(candidateFirst, marketFirst)
      || candidateFirst?.startsWith(marketFirst || '')
      || marketFirst?.startsWith(candidateFirst || '')
    )
  ) {
    score += 20;
  }

  const candidateCore = stripMiddleNameTokens(candidateTokens).join(' ');
  const marketCore = stripMiddleNameTokens(marketTokens).join(' ');
  if (
    candidateNormalized.includes(marketNormalized)
    || marketNormalized.includes(candidateNormalized)
    || (candidateCore && marketCore && candidateCore === marketCore)
  ) {
    score += 15;
  }

  return score;
}

function inferMarketElectionType(market) {
  const declaredType = String(market?.electionType || '').trim().toLowerCase();
  if (declaredType === 'primary' || declaredType === 'general') {
    return declaredType;
  }

  const combined = [market?.title, market?.seriesTitle, market?.rulesPrimary, market?.entityName]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (/(nominee|nomination|primary)/i.test(combined) || market?.marketType === 'candidate_nominee') {
    return 'primary';
  }

  return 'general';
}

function isPrimaryElectionMarket(market) {
  const declaredType = String(market?.electionType || '').trim().toLowerCase();
  if (declaredType === 'primary') {
    return true;
  }

  if (market?.marketType === 'candidate_nominee') {
    return true;
  }

  const combined = [
    market?.title,
    market?.seriesTitle,
    market?.seriesTicker,
    market?.marketTicker,
    market?.rulesPrimary,
    market?.entityName,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return /\b(primary|nominee|nomination)\b/i.test(combined);
}

function isGeneralElectionMarket(market) {
  if (inferMarketElectionType(market) !== 'general') {
    return false;
  }

  const title = String(market?.title || '');
  const seriesTitle = String(market?.seriesTitle || '');
  const combined = `${title} ${seriesTitle}`.toLowerCase();

  if (market?.marketType === 'party_winner') {
    return !/(nominee|nomination|primary)/i.test(combined);
  }

  if (market?.marketType !== 'district_winner') {
    return false;
  }

  if (/(finish|place|rank|round|runoff|margin)/i.test(combined)) {
    return false;
  }

  return /\bwin\b/i.test(combined);
}

function determinePrimaryMarketPalette(districtMarketRecord) {
  const primaryMarkets = (districtMarketRecord?.markets || []).filter(isPrimaryElectionMarket);
  if (!primaryMarkets.length) {
    return PRIMARY_STYLES.NO_MARKET;
  }

  const primaryParties = [...new Set(primaryMarkets.map((market) => normalizeKalshiPartyCode(market.party)).filter(Boolean))];
  if (primaryParties.length > 1) {
    return PRIMARY_STYLES.MULTI;
  }

  const [partyCode] = primaryParties;
  if (!partyCode) {
    return PRIMARY_STYLES.OTH;
  }

  return PRIMARY_STYLES[partyCode] || PRIMARY_STYLES.OTH;
}

function getActiveElectionView() {
  return activeElectionView === 'primary' ? 'primary' : 'general';
}

function getElectionMarkets(districtMarketRecord, electionView = getActiveElectionView()) {
  const allMarkets = districtMarketRecord?.markets || [];
  if (electionView === 'primary') {
    return allMarkets.filter(isPrimaryElectionMarket);
  }

  return allMarkets.filter(isGeneralElectionMarket);
}

function getCandidateMarketsForElection(markets = [], electionView = getActiveElectionView()) {
  if (electionView === 'primary') {
    return markets.filter((market) => market.marketType === 'candidate_nominee');
  }

  return markets.filter((market) => market.marketType === 'district_winner');
}

function getPartyMarketsForElection(markets = [], electionView = getActiveElectionView()) {
  if (electionView === 'primary') {
    return [];
  }

  return markets.filter((market) => market.marketType === 'party_winner');
}

function buildKalshiElectionContext(seatRecord, districtMarketRecord, electionView = getActiveElectionView()) {
  const officialCandidates = seatRecord?.election?.candidates || [];
  const electionMarkets = getElectionMarkets(districtMarketRecord, electionView);
  const candidateMarkets = getCandidateMarketsForElection(electionMarkets, electionView);
  const partyMarkets = getPartyMarketsForElection(electionMarkets, electionView);

  const candidateLookup = buildKalshiCandidateLookup(candidateMarkets);
  const partyOddsByCode = new Map();

  partyMarkets.forEach((market) => {
    if (!market.party) {
      return;
    }

    const partyCode = normalizeKalshiPartyCode(market.party);
    const existing = partyOddsByCode.get(partyCode);
    if (!existing || (Number(market.oddsPercent) || 0) > (Number(existing.oddsPercent) || 0)) {
      partyOddsByCode.set(partyCode, {
        oddsPercent: market.oddsPercent,
        marketTicker: market.marketTicker,
        status: market.status,
      });
    }
  });

  const candidateKalshiByKey = new Map();

  officialCandidates.forEach((candidate) => {
    const lookupKey = buildCandidateKalshiLookupKey(candidate);
    const kalshiMatch = matchCandidateToKalshi(candidate, candidateLookup, {
      fuzzyScorer: scoreCandidateNameMatch,
      fuzzyThreshold: 60,
    });

    if (lookupKey && kalshiMatch.matched) {
      candidateKalshiByKey.set(lookupKey, kalshiMatch);
    }
  });

  return {
    electionView,
    electionMarkets,
    candidateMarkets,
    partyMarkets,
    hasCandidateOdds: candidateKalshiByKey.size > 0,
    partyOddsByCode,
    candidateForDisplay(candidate) {
      const kalshiMatch = candidateKalshiByKey.get(buildCandidateKalshiLookupKey(candidate));
      return {
        ...candidate,
        ...(kalshiMatch || {
          matched: false,
          matchType: null,
          kalshiName: candidate?.kalshiName || null,
          kalshiOddsPercent: null,
          kalshiMarketTicker: null,
          kalshiStatus: null,
          kalshiMarketTitle: null,
          kalshiYesSubtitle: null,
        }),
      };
    },
    partyForDisplay(partyGroup) {
      const odds = partyOddsByCode.get(normalizeKalshiPartyCode(partyGroup?.partyCode));
      return {
        ...partyGroup,
        kalshiOddsPercent: odds?.oddsPercent ?? null,
        kalshiMarketTicker: odds?.marketTicker || null,
        kalshiStatus: odds?.status || null,
      };
    },
  };
}

function getPrimaryContestKeyForParty(market = {}) {
  const normalizedContestKey = String(market?.normalizedContestKey || '').trim();
  if (normalizedContestKey) {
    return normalizedContestKey;
  }

  const seatId = String(market?.seatId || '').trim();
  const electionCycle = String(market?.electionCycle || '').trim();
  const partyCode = normalizeKalshiPartyCode(market?.party);
  return [seatId, electionCycle, partyCode].filter(Boolean).join(':');
}

function buildPrimaryElectionView(primaryElection, index = 0) {
  if (!primaryElection || typeof primaryElection !== 'object') {
    return null;
  }

  const partyCode = normalizeKalshiPartyCode(primaryElection.partyCode)
    || normalizeKalshiPartyCode(primaryElection.partyName)
    || 'OTH';

  return {
    partyCode,
    partyName: getPartyName(partyCode, primaryElection.partyName),
    contestKey: primaryElection.electionId || null,
    label: primaryElection.label || null,
    seriesTitle: primaryElection.label || null,
    electionStatus: primaryElection.status || null,
    candidates: Array.isArray(primaryElection.displayCandidates)
      ? primaryElection.displayCandidates
      : [],
    nominationStatus: primaryElection.nomineeCandidateId || primaryElection.nomineeDisplayName
      ? {
        nomineeKnown: true,
        nomineeCandidateId: primaryElection.nomineeCandidateId || null,
        nomineeDisplayName: primaryElection.nomineeDisplayName || null,
      }
      : null,
    sourceIndex: index,
  };
}

function getPrimaryElectionViews(seatRecord) {
  const primaryElections = seatRecord?.election?.primaryElections;
  if (!Array.isArray(primaryElections) || !primaryElections.length) {
    return [];
  }

  return primaryElections
    .map((primaryElection, index) => buildPrimaryElectionView(primaryElection, index))
    .filter(Boolean);
}

function groupCandidatesForDisplay(candidates = []) {
  const partyGroups = new Map();

  candidates.forEach((candidate) => {
    const partyCode = normalizePartyCode(candidate?.partyCode || candidate?.partyName) || 'OTH';
    if (!partyGroups.has(partyCode)) {
      partyGroups.set(partyCode, {
        partyCode,
        partyName: getPartyName(partyCode, candidate?.partyName || ''),
        candidates: [],
      });
    }

    const group = partyGroups.get(partyCode);
    group.candidates.push(candidate);
    if (!group.partyName && candidate?.partyName) {
      group.partyName = getPartyName(partyCode, candidate.partyName);
    }
  });

  return [...partyGroups.values()];
}

function getGeneralPartyGroupsForRendering(seatRecord) {
  const displayCandidates = seatRecord?.election?.displayCandidates;
  if (!Array.isArray(displayCandidates)) {
    return [];
  }

  return groupCandidatesForDisplay(displayCandidates);
}

function getPrimaryPartyGroupsForRendering(seatRecord) {
  return getPrimaryElectionViews(seatRecord);
}

function buildPrimaryContestRows(seatRecord, districtMarketRecord, primaryContext = null) {
  const election = seatRecord?.election;
  if (!election) {
    return [];
  }

  const resolvedPrimaryContext = primaryContext || buildKalshiElectionContext(seatRecord, districtMarketRecord, 'primary');
  const primaryContests = getPrimaryPartyGroupsForRendering(seatRecord);
  const marketGroups = new Map();
  const marketGroupsByParty = new Map();

  (resolvedPrimaryContext.candidateMarkets || []).forEach((market) => {
    const partyCode = normalizeKalshiPartyCode(market.party) || 'OTH';
    const contestKey = getPrimaryContestKeyForParty(market);
    const groupKey = contestKey || `${partyCode}:${market.marketTicker || market.title || market.seriesTitle || 'primary-market'}`;
    if (!marketGroups.has(groupKey)) {
      marketGroups.set(groupKey, {
        groupKey,
        contestKey,
        partyCode,
        partyName: getPartyName(partyCode, ''),
        label: market.seriesTitle || market.title || market.marketTicker || 'Primary market',
        seriesTitle: market.seriesTitle || market.title || market.marketTicker || 'Primary market',
        markets: [],
      });
    }

    const marketGroup = marketGroups.get(groupKey);
    marketGroup.markets.push(market);

    if (!marketGroupsByParty.has(partyCode)) {
      marketGroupsByParty.set(partyCode, []);
    }
    marketGroupsByParty.get(partyCode).push(marketGroup);
  });

  const dedupeMarketGroups = (groups = []) => [...new Set(groups)];

  return primaryContests
    .map((partyGroup) => {
      const partyCode = normalizeKalshiPartyCode(partyGroup.partyCode) || 'OTH';
      const contestKey = partyGroup.contestKey || null;
      const partyMarketGroups = dedupeMarketGroups(marketGroupsByParty.get(partyCode));
      const matchingMarketGroup = (contestKey && marketGroups.get(contestKey))
        || partyMarketGroups.find((group) => group.contestKey === contestKey)
        || (partyMarketGroups.length === 1 ? partyMarketGroups[0] : null)
        || null;
      const candidates = (partyGroup.candidates || [])
        .map((candidate) => resolvedPrimaryContext.candidateForDisplay(candidate));
      const matchedCandidates = candidates.filter((candidate) => candidate.kalshiMarketTicker);
      const unmatchedMarkets = (matchingMarketGroup?.markets || [])
        .filter((market) => !matchedCandidates.some((candidate) => candidate.kalshiMarketTicker === market.marketTicker))
        .sort((left, right) => (Number(right?.oddsPercent) || 0) - (Number(left?.oddsPercent) || 0));
      const sortedCandidates = sortCandidates(candidates);

      return {
        partyCode,
        partyName: getPartyName(partyCode, partyGroup.partyName),
        contestKey: matchingMarketGroup?.contestKey || contestKey,
        label: partyGroup.label || matchingMarketGroup?.label || null,
        electionStatus: partyGroup.electionStatus || null,
        seriesTitle: matchingMarketGroup?.seriesTitle || partyGroup.seriesTitle || partyGroup.label || null,
        marketCount: matchingMarketGroup?.markets?.length || 0,
        candidates: sortedCandidates,
        matchedCandidateCount: matchedCandidates.length,
        unmatchedMarkets,
        nominationStatus: partyGroup.nominationStatus || null,
        favorite: sortedCandidates.find((candidate) => candidate.kalshiOddsPercent !== null && candidate.kalshiOddsPercent !== undefined)
          || null,
      };
    })
    .filter((partyGroup) => partyGroup.candidates.length || partyGroup.marketCount)
    .sort((left, right) => {
      const leftTopOdds = Number(left.favorite?.kalshiOddsPercent) || 0;
      const rightTopOdds = Number(right.favorite?.kalshiOddsPercent) || 0;
      if (rightTopOdds !== leftTopOdds) {
        return rightTopOdds - leftTopOdds;
      }

      return left.partyName.localeCompare(right.partyName);
    });
}

function buildPartyViewRows(seatRecord, ballotpediaRecord, districtMarketRecord, electionView = getActiveElectionView()) {
  if (electionView === 'primary') {
    const kalshiContext = buildKalshiElectionContext(seatRecord, districtMarketRecord, electionView);
    return buildPrimaryContestRows(seatRecord, districtMarketRecord, kalshiContext)
      .map((contest) => ({
        partyCode: contest.partyCode,
        partyName: contest.partyName,
        filingCount: contest.candidates.length,
        ballotpediaCount: 0,
        kalshiOddsPercent: null,
        kalshiMarketTicker: null,
        kalshiStatus: null,
        primaryMarketCount: contest.marketCount || 0,
        primaryFavoriteName: contest.favorite?.name || null,
        primaryFavoriteOddsPercent: contest.favorite?.kalshiOddsPercent ?? null,
        primaryFavoriteMarketTicker: contest.favorite?.kalshiMarketTicker || null,
        primaryFavoriteStatus: contest.favorite?.kalshiStatus || null,
        primaryContestKey: contest.contestKey || null,
        primarySeriesTitle: contest.seriesTitle || null,
        primaryLabel: contest.label || null,
        primaryStatus: contest.electionStatus || null,
      }))
      .sort((left, right) => {
        const oddsDelta = (Number(right.primaryFavoriteOddsPercent) || 0) - (Number(left.primaryFavoriteOddsPercent) || 0);
        if (oddsDelta !== 0) {
          return oddsDelta;
        }
        const filingDelta = (right.filingCount || 0) - (left.filingCount || 0);
        if (filingDelta !== 0) {
          return filingDelta;
        }
        return left.partyName.localeCompare(right.partyName);
      });
  }

  const officialPartyGroups = getGeneralPartyGroupsForRendering(seatRecord);
  const officialByParty = new Map(
    officialPartyGroups.map((partyGroup) => [
      normalizePartyCode(partyGroup.partyCode),
      {
        partyCode: normalizePartyCode(partyGroup.partyCode),
        partyName: getPartyName(partyGroup.partyCode, partyGroup.partyName),
        filingCount: (partyGroup.candidates || []).length,
      },
    ]),
  );
  const ballotpediaByParty = buildBallotpediaPartyCounts(ballotpediaRecord);
  const kalshiContext = buildKalshiElectionContext(seatRecord, districtMarketRecord, electionView);

  const partyCodes = new Set([
    ...officialByParty.keys(),
    ...ballotpediaByParty.keys(),
    ...kalshiContext.partyOddsByCode.keys(),
  ]);

  return [...partyCodes]
    .map((partyCode) => {
      const official = officialByParty.get(partyCode);
      const ballotpedia = ballotpediaByParty.get(partyCode);
      const kalshi = kalshiContext.partyOddsByCode.get(partyCode);
      return {
        partyCode,
        partyName: getPartyName(partyCode, official?.partyName || ballotpedia?.partyName),
        filingCount: official?.filingCount || 0,
        ballotpediaCount: ballotpedia?.count || 0,
        kalshiOddsPercent: kalshi?.oddsPercent ?? null,
        kalshiMarketTicker: kalshi?.marketTicker || null,
        kalshiStatus: kalshi?.status || null,
        primaryMarketCount: 0,
        primaryFavoriteName: null,
        primaryFavoriteOddsPercent: null,
        primaryFavoriteMarketTicker: null,
        primaryFavoriteStatus: null,
        primaryContestKey: null,
        primarySeriesTitle: null,
        primaryLabel: null,
        primaryStatus: null,
      };
    })
    .sort((left, right) => {
      const oddsDelta = (Number(right.kalshiOddsPercent) || 0) - (Number(left.kalshiOddsPercent) || 0);
      if (oddsDelta !== 0) {
        return oddsDelta;
      }
      const filingDelta = (right.filingCount || 0) - (left.filingCount || 0);
      if (filingDelta !== 0) {
        return filingDelta;
      }
      return left.partyName.localeCompare(right.partyName);
    });
}


function getTopMarketEntries(markets = []) {
  const sortableMarkets = markets.filter((market) => market && market.oddsPercent !== null && market.oddsPercent !== undefined);
  if (!sortableMarkets.length) {
    return { topOddsPercent: null, leaders: [] };
  }

  const sortedMarkets = [...sortableMarkets].sort((left, right) => (Number(right?.oddsPercent) || 0) - (Number(left?.oddsPercent) || 0));
  const topOddsPercent = Number(sortedMarkets[0]?.oddsPercent);
  const leaders = sortedMarkets.filter((market) => Number(market?.oddsPercent) === topOddsPercent);
  return { topOddsPercent, leaders };
}

function determineMarketOddsFavorite(seatRecord, districtMarketRecord) {
  if (!districtMarketRecord || !districtMarketRecord.markets?.length) {
    return { status: 'no_market', issue: null, palette: MARKET_ODDS_STYLES.NO_MARKET };
  }

  const kalshiContext = buildKalshiElectionContext(seatRecord, districtMarketRecord, 'general');
  const generalMarkets = kalshiContext.electionMarkets || [];
  if (!generalMarkets.length) {
    const primaryMarkets = getElectionMarkets(districtMarketRecord, 'primary');
    if (primaryMarkets.length) {
      return {
        status: 'primary_only',
        issue: 'Kalshi has primary markets here, but no indexed general-election markets yet.',
        palette: MARKET_ODDS_STYLES.PRIMARY_ONLY,
      };
    }

    return {
      status: 'issue',
      issue: 'Kalshi has district markets here, but none identify a general-election favorite.',
      palette: MARKET_ODDS_STYLES.ISSUE,
    };
  }

  const partyMarkets = kalshiContext.partyMarkets || [];
  if (partyMarkets.length) {
    const { leaders } = getTopMarketEntries(partyMarkets);
    if (!leaders.length) {
      return {
        status: 'issue',
        issue: 'Kalshi party markets are present, but none currently report usable odds.',
        palette: MARKET_ODDS_STYLES.ISSUE,
      };
    }

    const partyLeaders = [...new Set(leaders.map((market) => normalizeKalshiPartyCode(market.party)).filter(Boolean))];
    if (partyLeaders.length !== 1) {
      return {
        status: 'issue',
        issue: 'Kalshi party markets are tied or inconsistent, so no single favorite can be determined.',
        palette: MARKET_ODDS_STYLES.ISSUE,
      };
    }

    return {
      status: 'favorite',
      partyCode: partyLeaders[0],
      issue: null,
      palette: MARKET_ODDS_STYLES[partyLeaders[0]] || MARKET_ODDS_STYLES.OTH,
    };
  }

  const candidateMarkets = kalshiContext.candidateMarkets || [];
  if (!candidateMarkets.length) {
    return {
      status: 'issue',
      issue: 'Kalshi has a general-election series here, but it does not identify a party or candidate winner market.',
      palette: MARKET_ODDS_STYLES.ISSUE,
    };
  }

  const { leaders } = getTopMarketEntries(candidateMarkets);
  if (!leaders.length) {
    return {
      status: 'issue',
      issue: 'Kalshi candidate markets are present, but none currently report usable odds.',
      palette: MARKET_ODDS_STYLES.ISSUE,
    };
  }

  if (leaders.length !== 1) {
    return {
      status: 'issue',
      issue: 'Kalshi candidate markets are tied, so no single favorite can be determined.',
      palette: MARKET_ODDS_STYLES.ISSUE,
    };
  }

  const leader = leaders[0];
  const matchedCandidate = (seatRecord?.election?.displayCandidates || [])
    .map((candidate) => kalshiContext.candidateForDisplay(candidate))
    .find((candidate) => candidate.kalshiMarketTicker === leader.marketTicker);
  const partyCode = matchedCandidate?.partyCode ? normalizeKalshiPartyCode(matchedCandidate.partyCode) : null;

  if (!partyCode) {
    return {
      status: 'issue',
      issue: `Kalshi's favorite (${leader.entityName || 'unknown candidate'}) could not be matched to an affiliated party.`,
      palette: MARKET_ODDS_STYLES.ISSUE,
    };
  }

  return {
    status: 'favorite',
    partyCode,
    issue: null,
    palette: MARKET_ODDS_STYLES[partyCode] || MARKET_ODDS_STYLES.OTH,
  };
}

function sortCandidates(candidates = []) {
  return [...candidates].sort((left, right) => {
    const incumbentDelta = Number(isIncumbentCandidate(right)) - Number(isIncumbentCandidate(left));
    if (incumbentDelta !== 0) {
      return incumbentDelta;
    }

    const oddsDelta = (Number(right?.kalshiOddsPercent) || 0) - (Number(left?.kalshiOddsPercent) || 0);
    if (oddsDelta !== 0) {
      return oddsDelta;
    }

    return String(left?.name || '').localeCompare(String(right?.name || ''));
  });
}

function sortPartyGroups(candidatesByParty = []) {
  return [...candidatesByParty].sort((left, right) => {
    const leftHasIncumbent = left.candidates?.some(isIncumbentCandidate) || false;
    const rightHasIncumbent = right.candidates?.some(isIncumbentCandidate) || false;
    const incumbentDelta = Number(rightHasIncumbent) - Number(leftHasIncumbent);
    if (incumbentDelta !== 0) {
      return incumbentDelta;
    }

    const oddsDelta = (Number(right?.kalshiOddsPercent) || 0) - (Number(left?.kalshiOddsPercent) || 0);
    if (oddsDelta !== 0) {
      return oddsDelta;
    }

    return String(left?.partyName || left?.partyCode || '').localeCompare(
      String(right?.partyName || right?.partyCode || ''),
    );
  });
}

function candidateMatchesNominee(candidate, partyNominationStatus) {
  if (!candidate || !partyNominationStatus?.nomineeKnown) {
    return false;
  }

  const nomineeCandidateId = partyNominationStatus.nomineeCandidateId;
  if (nomineeCandidateId && candidate.candidateId) {
    return candidate.candidateId === nomineeCandidateId;
  }

  const nomineeDisplayName = String(partyNominationStatus.nomineeDisplayName || '').trim().toUpperCase();
  const candidateName = String(candidate.name || '').trim().toUpperCase();
  return Boolean(nomineeDisplayName) && candidateName === nomineeDisplayName;
}

function renderElectionDetails(seatRecord, ballotpediaRecord, districtMarketRecord, electionView = getActiveElectionView(), primaryContestRows = null) {
  const election = seatRecord?.election;
  if (!election) {
    clearElectionDisplay();
    return;
  }

  const electionViewTitle = getElectionViewTitle(electionView);
  const candidateMarketLabel = getCandidateMarketLabel(electionView);
  const partyMarketLabel = getPartyMarketLabel(electionView);
  const detailView = getActiveDetailView();
  const summaryPartyGroups = electionView === 'primary'
    ? getPrimaryPartyGroupsForRendering(seatRecord)
    : getGeneralPartyGroupsForRendering(seatRecord);
  const summaryCandidateCount = summaryPartyGroups.reduce((total, partyGroup) => total + (partyGroup.candidates?.length || 0), 0);
  const summaryPartyCount = summaryPartyGroups.length;
  electionSummaryEl.textContent = `${detailView === 'party' ? 'Party View' : `${electionViewTitle} view`} · ${election.contentionLabel} · ${summaryCandidateCount} candidate${summaryCandidateCount === 1 ? '' : 's'} shown across ${summaryPartyCount} part${summaryPartyCount === 1 ? 'y' : 'ies'}.`;
  candidateGroupsEl.innerHTML = '';

  if (detailView === 'party') {
    const partyRows = buildPartyViewRows(seatRecord, ballotpediaRecord, districtMarketRecord, electionView);
    if (!partyRows.length) {
      return;
    }
    const list = document.createElement('ul');
    list.className = 'district-party-view-list';

    partyRows.forEach((partyRow) => {
      const item = document.createElement('li');
      item.className = 'district-party-view-card';
      const kalshiText = electionView === 'primary'
        ? (() => {
          const favoriteText = partyRow.primaryFavoriteOddsPercent !== null && partyRow.primaryFavoriteOddsPercent !== undefined
            ? `${partyRow.primaryFavoriteName || 'Favorite'} ${formatKalshiMarketMeta(
              partyRow.primaryFavoriteOddsPercent,
              partyRow.primaryFavoriteMarketTicker,
              partyRow.primaryFavoriteStatus,
            )}`
            : null;
          if (favoriteText) {
            return favoriteText;
          }
          if (partyRow.primaryMarketCount) {
            return `${partyRow.primaryMarketCount} indexed primary candidate market${partyRow.primaryMarketCount === 1 ? '' : 's'}`;
          }
          return 'No indexed primary candidate markets';
        })()
        : (partyRow.kalshiOddsPercent !== null && partyRow.kalshiOddsPercent !== undefined
          ? formatKalshiMarketMeta(partyRow.kalshiOddsPercent, partyRow.kalshiMarketTicker, partyRow.kalshiStatus)
          : 'No indexed party market');
      const primaryDetailItems = electionView === 'primary'
        ? [
          partyRow.primaryLabel ? `<li><strong>Label:</strong> ${partyRow.primaryLabel}</li>` : '',
          partyRow.primaryStatus ? `<li><strong>Status:</strong> ${partyRow.primaryStatus}</li>` : '',
          `<li><strong>Indexed markets:</strong> ${partyRow.primaryMarketCount}</li>`,
          partyRow.primaryContestKey ? `<li><strong>Contest:</strong> ${partyRow.primaryContestKey}</li>` : '',
          partyRow.primarySeriesTitle ? `<li><strong>Series:</strong> ${partyRow.primarySeriesTitle}</li>` : '',
        ].filter(Boolean).join('')
        : '';
      item.innerHTML = `
        <p class="district-party-view-card__title">${partyRow.partyName} (${partyRow.partyCode})</p>
        <ul class="district-party-view-metrics">
          <li><strong>Shown:</strong> ${partyRow.filingCount}</li>
          <li><strong>Ballotpedia:</strong> ${partyRow.ballotpediaCount}</li>
          <li><strong>Kalshi:</strong> ${kalshiText}</li>
          ${primaryDetailItems}
        </ul>
      `;
      list.appendChild(item);
    });

    candidateGroupsEl.appendChild(list);
    return;
  }

  const primaryPartyGroups = electionView === 'primary'
    ? getPrimaryPartyGroupsForRendering(seatRecord)
    : [];
  const generalPartyGroups = electionView === 'primary'
    ? []
    : getGeneralPartyGroupsForRendering(seatRecord);
  if (electionView === 'primary' ? !primaryPartyGroups.length : !generalPartyGroups.length) {
    return;
  }

  const kalshiContext = electionView === 'primary'
    ? null
    : buildKalshiElectionContext(seatRecord, districtMarketRecord, electionView);

  const partyGroupsForDisplay = electionView === 'primary'
    ? (primaryContestRows || buildPrimaryContestRows(seatRecord, districtMarketRecord)).map((contest) => ({
      partyCode: contest.partyCode,
      partyName: contest.partyName,
      contestKey: contest.contestKey,
      label: contest.label,
      electionStatus: contest.electionStatus,
      seriesTitle: contest.seriesTitle,
      marketCount: contest.marketCount,
      favorite: contest.favorite,
      nominationStatus: contest.nominationStatus || election.nominationStatus?.parties?.[contest.partyCode] || null,
      candidates: contest.candidates,
      unmatchedMarkets: contest.unmatchedMarkets,
    }))
    : generalPartyGroups.map((partyGroup) => {
      const decoratedParty = kalshiContext.partyForDisplay(partyGroup);
      return {
        ...decoratedParty,
        nominationStatus: election.nominationStatus?.parties?.[partyGroup.partyCode] || null,
        candidates: (partyGroup.candidates || []).map((candidate) => kalshiContext.candidateForDisplay(candidate)),
      };
    });

  const orderedPartyGroups = electionView === 'primary'
    ? partyGroupsForDisplay
    : sortPartyGroups(partyGroupsForDisplay);

  orderedPartyGroups.forEach((partyGroup) => {
    const item = document.createElement('li');
    item.className = 'district-candidate-group';
    const orderedCandidates = electionView === 'primary'
      ? partyGroup.candidates
      : sortCandidates(partyGroup.candidates);

    const candidatesMarkup = orderedCandidates.map((candidate) => {
      const kalshiBits = [];
      const hasMatchedKalshiMarket = Boolean(candidate.kalshiMarketTicker || candidate.kalshiName);
      if (candidate.kalshiOddsPercent !== null && candidate.kalshiOddsPercent !== undefined) {
        kalshiBits.push(`${candidateMarketLabel}: ${formatKalshiMarketMeta(
          candidate.kalshiOddsPercent,
          candidate.kalshiMarketTicker,
          candidate.kalshiStatus,
        )}`);
      } else if (hasMatchedKalshiMarket) {
        kalshiBits.push(`${candidateMarketLabel}: Kalshi market matched (odds unavailable)`);
      } else {
        kalshiBits.push(`${candidateMarketLabel}: none indexed`);
      }
      if (candidate.kalshiName && candidate.kalshiName !== candidate.name) {
        kalshiBits.push(`Kalshi name: ${candidate.kalshiName}`);
      }
      if (electionView === 'primary' && candidateMatchesNominee(candidate, partyGroup.nominationStatus)) {
        kalshiBits.push('Primary winner');
      }

      return `
        <li>
          <strong>${candidate.name}</strong>
          ${electionView === 'primary' ? `<span class="district-candidate-odds">— ${formatOddsPercent(candidate.kalshiOddsPercent)}</span>` : ''}
          <span class="district-candidate-meta">(${kalshiBits.join(' · ')})</span>
          ${isIncumbentCandidate(candidate) ? '<span class="district-candidate-meta">(Incumbent)</span>' : ''}
        </li>
      `;
    }).join('');

    const partyOddsMeta = partyGroup.kalshiOddsPercent !== null && partyGroup.kalshiOddsPercent !== undefined
      ? ` (${partyMarketLabel}: ${formatKalshiMarketMeta(partyGroup.kalshiOddsPercent, partyGroup.kalshiMarketTicker, partyGroup.kalshiStatus)})`
      : '';
    const primaryContestMeta = electionView === 'primary'
      ? [partyGroup.label, partyGroup.electionStatus].filter(Boolean).join(' · ')
      : '';

    item.innerHTML = `
      <p class="district-candidate-group__title">${partyGroup.partyName} (${partyGroup.partyCode})${partyOddsMeta}</p>
      ${primaryContestMeta ? `<p class="district-candidate-group__meta">${primaryContestMeta}</p>` : ''}
      <ul class="district-candidate-group__list">${candidatesMarkup}</ul>
    `;
    candidateGroupsEl.appendChild(item);
  });
}

function getContentionKey(seatRecord) {
  const bucket = seatRecord?.election?.contentionBucket || 'no_election';
  if (bucket !== 'contested_primary_only') {
    return bucket;
  }

  const partyCode = getGeneralPartyGroupsForRendering(seatRecord)[0]?.partyCode;
  if (partyCode === 'DEM') return 'contested_primary_only_dem';
  if (partyCode === 'REP') return 'contested_primary_only_rep';
  return 'contested_primary_only_other';
}

function applyPalette(path, palette) {
  path.style.setProperty('--district-fill', palette.fill);
  path.style.setProperty('--district-fill-hover', palette.hover);
  path.style.setProperty('--district-fill-pinned', palette.pinned);
}

function findIncumbentCandidate(seatRecord) {
  return (seatRecord?.election?.candidates || []).find((candidate) => candidate?.incumbentStatus === 'INCUMBENT') || null;
}

const INCUMBENT_PARTY_ALIASES = {
  D: 'DEM',
  DEM: 'DEM',
  DFL: 'DEM',
  R: 'REP',
  REP: 'REP',
  I: 'IND',
  IND: 'IND',
  L: 'LIB',
  LIB: 'LIB',
  G: 'GRN',
  GRN: 'GRN',
};

function getIncumbentPartyCode(seatRecord, rawSeatRecord = seatRecord) {
  const incumbentCandidate = findIncumbentCandidate(seatRecord);
  if (incumbentCandidate?.partyCode) {
    return incumbentCandidate.partyCode;
  }

  const rawMetadata = rawSeatRecord?.rawMetadata || {};
  const isVacant = String(rawMetadata.VACANT || '').toUpperCase() === 'Y';
  if (isVacant) {
    return null;
  }

  const partyCode = String(rawMetadata.PARTY || '').trim().toUpperCase();
  if (!partyCode) {
    return null;
  }

  return INCUMBENT_PARTY_ALIASES[partyCode] || partyCode;
}

function getDistrictPalette(seatRecord, districtMarketRecord, colorScheme = activeColorScheme, rawSeatRecord = seatRecord) {
  if (colorScheme === 'incumbents') {
    const incumbentPartyCode = getIncumbentPartyCode(seatRecord, rawSeatRecord);
    if (incumbentPartyCode) {
      return INCUMBENT_STYLES[incumbentPartyCode] || INCUMBENT_STYLES.OTH;
    }
  }

  if (colorScheme === 'market_odds') {
    return determineMarketOddsFavorite(seatRecord, districtMarketRecord).palette;
  }

  if (colorScheme === 'primary') {
    return determinePrimaryMarketPalette(districtMarketRecord);
  }

  return CONTENTION_STYLES[getContentionKey(seatRecord)] || CONTENTION_STYLES.no_election;
}

function applyDistrictStyle(path, seatRecord, districtMarketRecord, colorScheme = activeColorScheme, rawSeatRecord = seatRecord) {
  applyPalette(path, getDistrictPalette(seatRecord, districtMarketRecord, colorScheme, rawSeatRecord));
}

function renderMarketDetails(seatRecord, districtMarketRecord, electionView = getActiveElectionView(), primaryContestRows = null) {
  const marketOddsFavorite = determineMarketOddsFavorite(seatRecord, districtMarketRecord);
  if (!districtMarketRecord || !districtMarketRecord.markets?.length) {
    marketSummaryEl.textContent = `No Kalshi US-REP ${getElectionViewLabel(electionView)} markets are currently indexed for this district.`;
    marketListEl.innerHTML = '';
    return;
  }

  const electionMarkets = getElectionMarkets(districtMarketRecord, electionView);
  if (!electionMarkets.length) {
    marketSummaryEl.textContent = electionView === 'primary'
      ? 'No Kalshi primary markets are currently indexed for this district.'
      : 'No Kalshi general-election markets are currently indexed for this district.';
    marketListEl.innerHTML = '';
    return;
  }

  if (electionView === 'primary') {
    const resolvedPrimaryContestRows = primaryContestRows || (() => {
      const primaryContext = buildKalshiElectionContext(seatRecord, districtMarketRecord, 'primary');
      return buildPrimaryContestRows(seatRecord, districtMarketRecord, primaryContext);
    })();
    const coveredContests = resolvedPrimaryContestRows.filter((row) => row.marketCount > 0);
    const coveredCandidates = resolvedPrimaryContestRows.reduce((count, row) => count + row.matchedCandidateCount, 0);
    const unmatchedMarketCount = resolvedPrimaryContestRows.reduce((count, row) => count + row.unmatchedMarkets.length, 0);
    const summaryBits = [
      `Primary view: ${coveredContests.length} party contest${coveredContests.length === 1 ? '' : 's'} and ${electionMarkets.length} indexed market${electionMarkets.length === 1 ? '' : 's'} are available for ${districtMarketRecord.seatId}.`,
    ];
    if (coveredCandidates > 0) {
      summaryBits.push(`${coveredCandidates} official candidate${coveredCandidates === 1 ? '' : 's'} matched to indexed primary odds.`);
    }
    if (unmatchedMarketCount > 0) {
      summaryBits.push(`${unmatchedMarketCount} indexed market${unmatchedMarketCount === 1 ? '' : 's'} could not be matched to an official filing name and remain listed below.`);
    }

    marketSummaryEl.textContent = summaryBits.join(' ');
    marketListEl.innerHTML = '';

    resolvedPrimaryContestRows.forEach((contest) => {
      if (!contest.marketCount) {
        return;
      }

      const item = document.createElement('li');
      item.className = 'market-item district-market-card';

      const candidateMarkup = contest.candidates.map((candidate) => {
        const metaBits = [];
        if (candidate.kalshiMarketTicker) {
          metaBits.push(candidate.kalshiMarketTicker);
        }
        if (candidate.kalshiStatus) {
          metaBits.push(candidate.kalshiStatus);
        }
        if (candidate.kalshiName && candidate.kalshiName !== candidate.name) {
          metaBits.push(`Kalshi: ${candidate.kalshiName}`);
        }
        return `
          <li>
            <strong>${candidate.name}</strong>: ${formatOddsPercent(candidate.kalshiOddsPercent)}
            <span class="candidate-market-meta">(${metaBits.join(' · ') || 'No indexed primary market'})</span>
          </li>
        `;
      }).join('');

      const unmatchedMarkup = contest.unmatchedMarkets.map((market) => `
        <li>
          <strong>${market.entityName || market.yesSubtitle || 'Unknown'}</strong>: ${formatOddsPercent(market.oddsPercent)}
          <span class="candidate-market-meta">(${[market.marketTicker, market.status].filter(Boolean).join(' · ') || 'No market metadata'})</span>
        </li>
      `).join('');

      const metaBits = [
        `<span><strong>Party:</strong> ${contest.partyName} (${contest.partyCode})</span>`,
        `<span><strong>Seat ID:</strong> ${districtMarketRecord.seatId}</span>`,
      ];
      if (contest.label) {
        metaBits.push(`<span><strong>Label:</strong> ${contest.label}</span>`);
      }
      if (contest.electionStatus) {
        metaBits.push(`<span><strong>Status:</strong> ${contest.electionStatus}</span>`);
      }
      if (contest.contestKey) {
        metaBits.push(`<span><strong>Contest:</strong> ${contest.contestKey}</span>`);
      }
      if (contest.favorite) {
        metaBits.push(`<span><strong>Favorite:</strong> ${contest.favorite.name} ${formatOddsPercent(contest.favorite.kalshiOddsPercent)}</span>`);
      }

      item.innerHTML = `
        <p class="market-title">${contest.label || contest.seriesTitle || `${contest.partyName} primary`} — ${districtMarketRecord.seatId}</p>
        <p class="market-meta">${metaBits.join('')}</p>
        <ul class="candidate-list">${candidateMarkup}${unmatchedMarkup}</ul>
      `;

      marketListEl.appendChild(item);
    });
    return;
  }

  const seriesGroups = new Map();

  electionMarkets.forEach((market) => {
    const seriesKey = getDistrictElectionGroupKey(market);
    if (!seriesGroups.has(seriesKey)) {
      seriesGroups.set(seriesKey, {
        seriesTicker: market.seriesTicker || 'N/A',
        seriesTitle: market.seriesTitle || market.title || market.marketTicker,
        normalizedContestKey: market.normalizedContestKey || null,
        eventTicker: market.eventTicker || market.childElection?.ticker || null,
        marketType: market.marketType,
        party: market.party,
        status: market.status,
        closeTime: market.closeTime,
        markets: [],
      });
    }

    seriesGroups.get(seriesKey).markets.push(market);
  });

  const marketSummaryParts = [`${getElectionViewTitle(electionView)} view: ${seriesGroups.size} ${getElectionViewLabel(electionView)} series and ${electionMarkets.length} indexed market${electionMarkets.length === 1 ? '' : 's'} are available for ${districtMarketRecord.seatId}.`];
  if (electionView === 'general' && marketOddsFavorite.issue) {
    marketSummaryParts.push(marketOddsFavorite.issue);
  }
  marketSummaryEl.textContent = marketSummaryParts.join(' ');
  marketListEl.innerHTML = '';

  [...seriesGroups.values()]
    .sort((a, b) => a.seriesTitle.localeCompare(b.seriesTitle))
    .forEach((series) => {
      const item = document.createElement('li');
      item.className = 'market-item district-market-card';

      const winners = [...series.markets].sort((a, b) => (Number(b.oddsPercent) || 0) - (Number(a.oddsPercent) || 0));
      const candidateMarkup = winners.map((market) => {
        const subtitle = [market.marketTicker, market.status].filter(Boolean).join(' · ');
        const entityLabel = market.marketType === 'party_winner'
          ? `${getPartyName(market.party, market.entityName || '')} party`
          : (market.entityName || 'Unknown');
        return `
          <li>
            <strong>${entityLabel}</strong>: ${formatOddsPercent(market.oddsPercent)}
            <span class="candidate-market-meta">(${subtitle || 'No market metadata'})</span>
          </li>
        `;
      }).join('');

      const metaBits = [
        `<span><strong>Seat Type:</strong> US-REP</span>`,
        `<span><strong>Election:</strong> ${getSeriesElectionLabel(series)}</span>`,
        `<span><strong>Seat ID:</strong> ${districtMarketRecord.seatId}</span>`,
      ];

      item.innerHTML = `
        <p class="market-title">${formatDistrictSeriesTitle(series, districtMarketRecord)}</p>
        <p class="market-meta">${metaBits.join('')}</p>
        <ul class="candidate-list">${candidateMarkup}</ul>
      `;

      marketListEl.appendChild(item);
    });
}

function clearSvg() {
  while (svg.firstChild) {
    svg.removeChild(svg.firstChild);
  }
}

function renderDistrictMap(districtFeatures, stateFeatures, districtSource, stateSource, districtMarketLookup, districtSeatLookup, districtElectionViewLookup, districtBallotpediaLookup) {
  clearSvg();

  const viewBox = svg.viewBox.baseVal;
  const project = buildProjector([...districtFeatures, ...stateFeatures], viewBox.width, viewBox.height);

  const districtLayer = createSvgElement('g');
  districtLayer.setAttribute('aria-label', 'Congressional districts');
  svg.appendChild(districtLayer);

  const labelLayer = createSvgElement('g');
  labelLayer.setAttribute('aria-label', 'State labels');
  svg.appendChild(labelLayer);

  let hoveredPath = null;
  let pinnedPath = null;
  let pinnedSeatKey = null;
  const pathLookup = new Map();
  const featureLookup = new Map();

  function updateDistrictPanel(feature, { pinned = false } = {}) {
    selectedEl.textContent = feature.properties.districtLabel;
    metaEl.textContent = `${feature.properties.districtName} · GEOID ${feature.properties.geoid || 'N/A'}`;
    selectionHintEl.textContent = pinned
      ? 'Pinned selection. Click the district again to release it, or click a different district to switch the pinned view.'
      : 'Previewing district on hover. Click to pin it for full viewing.';
    const seatKey = getDistrictSeatKey(feature);
    const electionView = getActiveElectionView();
    const rawSeatRecord = districtSeatLookup.get(seatKey) || null;
    const seatRecord = districtElectionViewLookup.get(seatKey) || rawSeatRecord;
    // Raw seat data remains canonical for filing totals and diagnostics, while the
    // derived election-view dataset is canonical for UI display filtering.
    const districtMarketRecord = districtMarketLookup.get(seatKey);
    const primaryContestRows = electionView === 'primary'
      ? buildPrimaryContestRows(
        seatRecord,
        districtMarketRecord,
        buildKalshiElectionContext(seatRecord, districtMarketRecord, 'primary'),
      )
      : null;
    renderElectionDetails(seatRecord, districtBallotpediaLookup.get(seatKey), districtMarketRecord, electionView, primaryContestRows);
    renderMarketDetails(seatRecord, districtMarketRecord, electionView, primaryContestRows);
  }

  function syncDistrictClasses() {
    pathLookup.forEach((path, seatKey) => {
      path.classList.toggle('is-active', seatKey === pinnedSeatKey || path === hoveredPath);
      path.classList.toggle('is-pinned', seatKey === pinnedSeatKey);
      path.setAttribute('aria-pressed', String(seatKey === pinnedSeatKey));
    });
  }

  districtFeatures.forEach((feature) => {
    const seatKey = getDistrictSeatKey(feature);
    const path = createSvgElement('path');
    path.setAttribute('class', 'district-fill');
    path.setAttribute('d', geometryToPath(feature.geometry, project));
    path.dataset.stateCode = feature.properties.stateCode;
    path.dataset.districtCode = feature.properties.districtCode;
    path.dataset.districtLabel = feature.properties.districtLabel;
    path.setAttribute('role', 'button');
    path.setAttribute('tabindex', '0');
    path.setAttribute('aria-label', `Congressional district ${feature.properties.districtLabel}`);
    path.setAttribute('aria-pressed', 'false');
    pathLookup.set(seatKey, path);
    featureLookup.set(seatKey, feature);
    const rawSeatRecord = districtSeatLookup.get(seatKey) || null;
    const seatRecord = districtElectionViewLookup.get(seatKey) || rawSeatRecord;
    applyDistrictStyle(path, seatRecord, districtMarketLookup.get(seatKey), activeColorScheme, rawSeatRecord);

    const previewDistrict = () => {
      if (pinnedSeatKey) {
        return;
      }

      hoveredPath = path;
      syncDistrictClasses();
      updateDistrictPanel(feature);
    };

    const handlePinToggle = () => {
      if (pinnedSeatKey === seatKey) {
        pinnedSeatKey = null;
        pinnedPath = null;
        hoveredPath = path.matches(':hover') ? path : null;
        if (hoveredPath) {
          updateDistrictPanel(feature);
        } else {
          clearDistrictSelection(pathLookup);
        }
        syncDistrictClasses();
        return;
      }

      pinnedSeatKey = seatKey;
      pinnedPath = path;
      hoveredPath = path;
      syncDistrictClasses();
      updateDistrictPanel(feature, { pinned: true });
    };

    path.addEventListener('mouseenter', previewDistrict);

    path.addEventListener('mouseleave', () => {
      if (pinnedSeatKey) {
        hoveredPath = pinnedPath;
        syncDistrictClasses();
        return;
      }

      hoveredPath = null;
      clearDistrictSelection(pathLookup);
    });

    path.addEventListener('click', handlePinToggle);

    path.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        handlePinToggle();
      }
    });

    districtLayer.appendChild(path);
  });

  stateFeatures.forEach((feature) => {
    const centroid = computeVisualCentroid(feature, project);
    if (!centroid) return;

    const label = createSvgElement('text');
    label.setAttribute('class', 'district-label');
    label.setAttribute('x', centroid.x.toFixed(2));
    label.setAttribute('y', centroid.y.toFixed(2));
    label.textContent = feature.properties.stateCode;
    labelLayer.appendChild(label);
  });

  svg.addEventListener('click', (event) => {
    if (event.target !== svg) {
      return;
    }

    pinnedSeatKey = null;
    pinnedPath = null;
    hoveredPath = null;
    clearDistrictSelection(pathLookup);
    syncDistrictClasses();
  });

  const getActiveSeatKey = () => pinnedSeatKey || [...pathLookup.entries()].find(([, path]) => path === hoveredPath)?.[0] || null;

  const refreshActiveDistrictPanel = () => {
    const activeSeatKey = getActiveSeatKey();
    if (activeSeatKey) {
      updateDistrictPanel(featureLookup.get(activeSeatKey), { pinned: activeSeatKey === pinnedSeatKey });
    }
  };

  if (colorSchemeSelectEl) {
    const refreshDistrictStyles = () => {
      activeColorScheme = ['contention', 'incumbents', 'market_odds', 'primary'].includes(colorSchemeSelectEl.value)
        ? colorSchemeSelectEl.value
        : 'contention';
      if (colorSchemeDescriptionEl) {
        colorSchemeDescriptionEl.textContent = COLOR_SCHEME_LABELS[activeColorScheme];
      }

      pathLookup.forEach((path, seatKey) => {
        const rawSeatRecord = districtSeatLookup.get(seatKey) || null;
        const seatRecord = districtElectionViewLookup.get(seatKey) || rawSeatRecord;
        applyDistrictStyle(path, seatRecord, districtMarketLookup.get(seatKey), activeColorScheme, rawSeatRecord);
      });

      refreshActiveDistrictPanel();
    };

    colorSchemeSelectEl.value = activeColorScheme;
    colorSchemeDescriptionEl.textContent = COLOR_SCHEME_LABELS[activeColorScheme];
    colorSchemeSelectEl.addEventListener('change', refreshDistrictStyles);
  }

  if (electionViewSelectEl) {
    const refreshElectionView = () => {
      activeElectionView = ['primary', 'general'].includes(electionViewSelectEl.value)
        ? electionViewSelectEl.value
        : 'general';
      refreshActiveDistrictPanel();
    };

    electionViewSelectEl.value = activeElectionView;
    electionViewSelectEl.addEventListener('change', refreshElectionView);
  }

  if (detailViewSelectEl) {
    detailViewSelectEl.addEventListener('change', refreshActiveDistrictPanel);
  }

  sourceEl.textContent = `District source: ${districtSource} · State source: ${stateSource}`;
}

async function loadMap() {
  try {
    setStatus('Loading congressional district geometry…');
    const districtsPayload = await fetchJsonWithFallback([...LOCAL_DISTRICT_SOURCES, REMOTE_DISTRICT_SOURCE]);
    setStatus('Loading state boundary geometry…');
    const statesPayload = await fetchJsonWithFallback([...LOCAL_STATE_SOURCES, REMOTE_STATE_SOURCE]);
    setStatus('Loading Kalshi district market index…');
    const districtMarketsPayload = await fetchJsonWithFallback(LOCAL_HOUSE_MARKET_INDEX_SOURCES);
    setStatus('Loading official 2026 candidate filings…');
    const districtSeatsPayload = await fetchJsonWithFallback(LOCAL_HOUSE_ELECTION_SOURCES);
    setStatus('Loading election-view district summaries…');
    const houseElectionViewPayload = await fetchJsonWithFallback(LOCAL_HOUSE_ELECTION_VIEW_SOURCES);
    const houseElectionViewData = Array.isArray(houseElectionViewPayload.data?.seats)
      ? houseElectionViewPayload.data
      : { ...houseElectionViewPayload.data, seats: [] };
    setStatus('Loading Ballotpedia district summaries…');
    const districtBallotpediaPayload = await fetchJsonWithFallback(LOCAL_HOUSE_BALLOTPEDIA_SOURCES);

    const districtFeatures = (districtsPayload.data.features || [])
      .map(normalizeDistrictFeature)
      .filter(Boolean);
    const stateFeatures = (statesPayload.data.features || [])
      .map(normalizeStateFeature)
      .filter(Boolean);

    if (!districtFeatures.length || !stateFeatures.length) {
      throw new Error('GIS sources loaded, but no contiguous U.S. features were available to render.');
    }

    const districtMarketLookup = new Map((districtMarketsPayload.data.districts || []).map((district) => [district.seatId, district]));
    const districtSeatLookup = new Map((districtSeatsPayload.data.seats || []).map((seat) => [seat.seatId, seat]));
    // This derived lookup is the canonical district-map presentation dataset.
    // Raw seat records remain available only for filing totals and diagnostics.
    const districtElectionViewLookup = new Map(houseElectionViewData.seats.map((seat) => [buildElectionViewSeatLookupKey(seat), seat]));
    if (districtElectionViewLookup.size !== houseElectionViewData.seats.length) {
      throw new Error('Election view data contains duplicate district lookup keys.');
    }
    const districtBallotpediaLookup = new Map(Object.entries(districtBallotpediaPayload.data.districtsBySeatId || {}));

    renderDistrictMap(
      districtFeatures,
      stateFeatures,
      districtsPayload.source,
      statesPayload.source,
      districtMarketLookup,
      districtSeatLookup,
      districtElectionViewLookup,
      districtBallotpediaLookup,
    );
    clearElectionDisplay();
    clearMarketDisplay();
    setStatus(`Rendered ${districtFeatures.length} congressional districts across ${stateFeatures.length} contiguous-state outlines with official 2026 filing classifications and ${districtMarketsPayload.data.matchedMarkets || 0} indexed Kalshi district markets.`);
  } catch (error) {
    setStatus(`Unable to load GIS map layers: ${error.message}`, { error: true });
    sourceEl.textContent =
      'Expected local GIS inputs under apps/web/data or reachable official ArcGIS-backed services. To refresh local layers, run: python scripts/build_congressional_map_layers.py';
  }
}

loadMap();
