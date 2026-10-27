import {
  buildCandidateMatchKeys,
  normalizeName,
  normalizePartyCode,
  matchCandidateToKalshi,
  buildKalshiCandidateLookup,
} from './kalshi-candidate-match.js';

const SEAT_SOURCES = ['./data/us-house-seats.json'];
const BALLOTPEDIA_SOURCES = ['./data/us-house-ballotpedia.json'];
const KALSHI_SOURCES = ['./data/us-house-market-index.json'];

const statusEl = document.getElementById('seat-debug-status');
const summaryEl = document.getElementById('seat-debug-summary');
const searchEl = document.getElementById('seat-debug-search');
const stateFilterEl = document.getElementById('seat-debug-state-filter');
const dataFilterEl = document.getElementById('seat-debug-data-filter');
const seatListEl = document.getElementById('seat-debug-list');
const titleEl = document.getElementById('seat-debug-title');
const metaEl = document.getElementById('seat-debug-meta');
const unifiedEl = document.getElementById('seat-debug-unified');
const filingsEl = document.getElementById('seat-debug-filings');
const ballotpediaEl = document.getElementById('seat-debug-ballotpedia');
const kalshiEl = document.getElementById('seat-debug-kalshi');

let allElectionEntries = [];
let visibleElectionEntries = [];
let selectedElectionId = null;

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

      return await response.json();
    } catch {
      // fall through
    }
  }

  throw new Error(`Unable to load JSON from: ${sources.join(', ')}`);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatPartyLabel(candidate = {}) {
  return candidate.partyName || candidate.partyCode || 'Unknown party';
}

function titleCaseName(value) {
  return String(value || '')
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatUnifiedParty(partyCode) {
  const normalized = normalizePartyCode(partyCode);
  if (normalized === 'DEM') return 'Democratic';
  if (normalized === 'REP') return 'Republican';
  if (normalized === 'IND') return 'Independent';
  if (normalized === 'LIB') return 'Libertarian';
  if (normalized === 'GRE') return 'Green';
  return normalized || 'Unknown party';
}

function parseBallotpediaCandidateLine(line, partyHint = null) {
  const raw = String(line || '').trim();
  if (!raw || raw.startsWith('[')) {
    return null;
  }

  const partyMatch = raw.match(/\(([^()]*?(?:Democratic|Republican|Independent|Libertarian|Green)[^()]*)\)/i);
  const cleanedName = raw
    .replace(/✔/g, ' ')
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleanedName) {
    return null;
  }

  return {
    name: cleanedName,
    partyCode: normalizePartyCode(partyHint || partyMatch?.[1] || null),
    sourceLine: raw,
  };
}

function collectBallotpediaCandidates(ballotpediaRecord) {
  const data = ballotpediaRecord?.election?.ballotpedia;
  if (!data) {
    return [];
  }

  const candidates = [];
  (data.generalElectionCandidateLines || []).forEach((line) => {
    const parsed = parseBallotpediaCandidateLine(line);
    if (parsed) {
      candidates.push({
        ...parsed,
        sourceSection: 'general',
      });
    }
  });

  Object.entries(data.primaryCandidateSections || {}).forEach(([party, lines]) => {
    (Array.isArray(lines) ? lines : []).forEach((line) => {
      const parsed = parseBallotpediaCandidateLine(line, party);
      if (parsed) {
        candidates.push({
          ...parsed,
          sourceSection: 'primary',
        });
      }
    });
  });

  (data.advancedFromPrimaryLines || []).forEach((line) => {
    const parsed = parseBallotpediaCandidateLine(line);
    if (parsed) {
      candidates.push({
        ...parsed,
        sourceSection: 'advanced',
      });
    }
  });

  return candidates;
}

function collectUnifiedCandidates(seat) {
  const unified = [];
  const candidateByKey = new Map();
  const kalshiLookup = buildKalshiCandidateLookup(seat.kalshi?.markets || []);

  function pickDisplayName(existingName, incomingName) {
    const existing = String(existingName || '').trim();
    const incoming = String(incomingName || '').trim();
    if (!existing) return incoming;
    if (!incoming) return existing;
    return incoming.length < existing.length ? incoming : existing;
  }

  function ensureCandidate({ name, partyCode = null, aliases = [], sourceType, payload }) {
    const keys = [...buildCandidateMatchKeys(name, partyCode, aliases)];
    let candidate = keys.map((key) => candidateByKey.get(key)).find(Boolean);

    if (!candidate) {
      candidate = {
        id: `${normalizeName(name)}|${normalizePartyCode(partyCode) || ''}`,
        displayName: titleCaseName(name),
        sortName: normalizeName(name),
        partyCode: normalizePartyCode(partyCode),
        kalshiMatch: null,
        sourceEntries: {
          filings: [],
          ballotpedia: [],
          kalshi: [],
        },
      };
      unified.push(candidate);
    }

    candidate.displayName = titleCaseName(pickDisplayName(candidate.displayName, name));
    candidate.sortName = candidate.sortName || normalizeName(name);
    if (!candidate.partyCode && partyCode) {
      candidate.partyCode = normalizePartyCode(partyCode);
    }

    if (payload) {
      candidate.sourceEntries[sourceType].push(payload);
    }

    keys.forEach((key) => candidateByKey.set(key, candidate));
    return candidate;
  }

  (seat.filings?.candidates || []).forEach((candidate) => {
    ensureCandidate({
      name: candidate.name,
      partyCode: candidate.partyCode,
      aliases: [candidate.kalshiName, ...(candidate.aliases || [])].filter(Boolean),
      sourceType: 'filings',
      payload: candidate,
    });
  });

  collectBallotpediaCandidates(seat.ballotpedia).forEach((candidate) => {
    ensureCandidate({
      name: candidate.name,
      partyCode: candidate.partyCode,
      sourceType: 'ballotpedia',
      payload: candidate,
    });
  });

  (seat.kalshi?.markets || []).forEach((market) => {
    const name = market.entityName || market.yesSubtitle || market.title;
    ensureCandidate({
      name,
      partyCode: market.party,
      aliases: [market.yesSubtitle, market.entityName].filter(Boolean),
      sourceType: 'kalshi',
      payload: market,
    });
  });

  unified.forEach((candidate) => {
    const filing = candidate.sourceEntries.filings[0] || {};
    const matchCandidate = {
      name: filing.name || candidate.displayName,
      kalshiName: filing.kalshiName || null,
      aliases: filing.aliases || [],
      partyCode: filing.partyCode || candidate.partyCode,
    };
    candidate.kalshiMatch = matchCandidateToKalshi(matchCandidate, kalshiLookup);
  });

  return unified
    .filter((candidate) => candidate.sortName)
    .sort((left, right) => left.sortName.localeCompare(right.sortName));
}

function normalizeBallotpediaMap(payload) {
  if (payload?.districtsBySeatId && typeof payload.districtsBySeatId === 'object') {
    return payload.districtsBySeatId;
  }

  const records = Array.isArray(payload?.districts)
    ? payload.districts
    : Array.isArray(payload?.seats)
      ? payload.seats
      : [];

  return records.reduce((accumulator, record) => {
    if (record?.seatId) {
      accumulator[record.seatId] = record;
    }
    return accumulator;
  }, {});
}

function normalizeKalshiMap(payload) {
  const districts = Array.isArray(payload?.districts) ? payload.districts : [];
  return districts.reduce((accumulator, district) => {
    if (district?.seatId) {
      accumulator[district.seatId] = district;
    }
    return accumulator;
  }, {});
}

function buildSearchBlob(seat) {
  const filingsCandidates = (seat.filings?.candidates || []).map((candidate) => candidate.name);
  const ballotpediaData = seat.ballotpedia?.election?.ballotpedia || {};
  const ballotpediaCandidates = [
    ...(ballotpediaData.generalElectionCandidateLines || []),
    ...Object.values(ballotpediaData.primaryCandidateSections || {}).flat(),
    ...(ballotpediaData.advancedFromPrimaryLines || []),
  ];
  const kalshiTitles = (seat.kalshi?.markets || []).map((market) => market.title || market.entityName || market.marketTicker);

  return [
    seat.seatId,
    seat.displayName,
    seat.stateCode,
    seat.stateName,
    seat.districtLabel,
    ...filingsCandidates,
    ...ballotpediaCandidates,
    ...kalshiTitles,
  ].join(' ').toLowerCase();
}

function candidateSortKey(candidate) {
  return [
    normalizePartyCode(candidate?.partyCode) !== 'DEM' && normalizePartyCode(candidate?.partyCode) !== 'REP' ? '1' : '0',
    normalizePartyCode(candidate?.partyCode) || '',
    normalizeName(candidate?.name || ''),
  ].join('|');
}

function buildGeneralElectionCandidates(filings) {
  const candidates = Array.isArray(filings?.candidates) ? filings.candidates : [];
  const hasStatuses = candidates.some((candidate) => candidate?.currentElectionStatus && typeof candidate.currentElectionStatus === 'object');
  const filtered = hasStatuses
    ? candidates.filter((candidate) => ['general-nominated', 'general-other'].includes(candidate?.currentElectionStatus?.code))
    : candidates;
  return [...filtered].sort((left, right) => candidateSortKey(left).localeCompare(candidateSortKey(right)));
}

function buildPrimaryElectionCandidates(primaryElection) {
  const candidates = Array.isArray(primaryElection?.candidates) ? [...primaryElection.candidates] : [];
  const nomineeCandidateId = String(primaryElection?.nomineeCandidateId || '');
  return candidates.sort((left, right) => {
    const leftNomineeRank = String(left?.candidateId || '') === nomineeCandidateId ? 0 : 1;
    const rightNomineeRank = String(right?.candidateId || '') === nomineeCandidateId ? 0 : 1;
    if (leftNomineeRank !== rightNomineeRank) {
      return leftNomineeRank - rightNomineeRank;
    }
    return candidateSortKey(left).localeCompare(candidateSortKey(right));
  });
}

function buildElectionEntriesForSeat(seat) {
  const filings = seat.filings || {};
  const entries = [];
  const generalCandidates = buildGeneralElectionCandidates(filings);
  entries.push({
    electionEntryId: `${seat.seatId}::general`,
    seatId: seat.seatId,
    displayName: seat.displayName,
    districtLabel: seat.districtLabel,
    stateCode: seat.stateCode,
    stateName: seat.stateName,
    hasFilings: seat.hasFilings,
    hasBallotpedia: seat.hasBallotpedia,
    hasKalshi: seat.hasKalshi,
    hasAnyData: seat.hasAnyData,
    searchBlob: seat.searchBlob,
    unifiedCandidates: seat.unifiedCandidates,
    ballotpedia: seat.ballotpedia,
    kalshi: seat.kalshi,
    filings,
    selectedElection: {
      electionId: filings.electionId || `${seat.seatId}-general`,
      electionKind: filings.electionKind || 'general',
      label: 'General',
      status: filings.status || 'active',
      candidates: generalCandidates,
      sourceElection: filings,
    },
  });

  const primaryChildren = Array.isArray(filings?.children) ? filings.children : [];
  primaryChildren
    .filter((child) => child?.electionKind === 'primary')
    .sort((left, right) => String(left?.label || '').localeCompare(String(right?.label || '')))
    .forEach((primaryElection, index) => {
      entries.push({
        electionEntryId: primaryElection.electionId || `${seat.seatId}::primary-${index}`,
        seatId: seat.seatId,
        displayName: seat.displayName,
        districtLabel: seat.districtLabel,
        stateCode: seat.stateCode,
        stateName: seat.stateName,
        hasFilings: seat.hasFilings,
        hasBallotpedia: seat.hasBallotpedia,
        hasKalshi: seat.hasKalshi,
        hasAnyData: seat.hasAnyData,
        searchBlob: seat.searchBlob,
        unifiedCandidates: seat.unifiedCandidates,
        ballotpedia: seat.ballotpedia,
        kalshi: seat.kalshi,
        filings,
        selectedElection: {
          electionId: primaryElection.electionId || `${seat.seatId}::primary-${index}`,
          electionKind: 'primary',
          label: primaryElection.label || `Primary ${index + 1}`,
          status: primaryElection.status || 'active',
          partyCode: primaryElection.partyCode || null,
          nomineeCandidateId: primaryElection.nomineeCandidateId || null,
          nomineeDisplayName: primaryElection.nomineeDisplayName || null,
          candidates: buildPrimaryElectionCandidates(primaryElection),
          sourceElection: primaryElection,
        },
      });
    });

  return entries;
}

function joinSeatSources(seatPayload, ballotpediaPayload, kalshiPayload) {
  const ballotpediaBySeat = normalizeBallotpediaMap(ballotpediaPayload);
  const kalshiBySeat = normalizeKalshiMap(kalshiPayload);
  const canonicalSeats = Array.isArray(seatPayload?.seats) ? seatPayload.seats : [];

  return canonicalSeats.map((seat) => {
    const filings = seat.election || null;
    const ballotpedia = ballotpediaBySeat[seat.seatId] || null;
    const kalshi = kalshiBySeat[seat.seatId] || null;
    const hasFilings = Boolean(filings?.candidateCount);
    const hasBallotpedia = Boolean(ballotpedia?.election?.ballotpedia);
    const hasKalshi = Boolean(kalshi?.marketCount);

    return {
      seatId: seat.seatId,
      displayName: seat.displayName,
      districtLabel: seat.districtLabel,
      stateCode: seat.stateCode,
      stateName: seat.stateName,
      districtNumber: seat.districtNumber,
      filings,
      ballotpedia,
      kalshi,
      hasFilings,
      hasBallotpedia,
      hasKalshi,
      hasAnyData: hasFilings || hasBallotpedia || hasKalshi,
      searchBlob: '',
      unifiedCandidates: [],
    };
  }).map((seat) => ({
    ...seat,
    unifiedCandidates: collectUnifiedCandidates(seat),
    searchBlob: buildSearchBlob(seat),
  })).flatMap((seat) => buildElectionEntriesForSeat(seat));
}

function renderSummary(electionEntries) {
  const uniqueSeatCount = new Set(electionEntries.map((entry) => entry.seatId)).size;
  const withAnyData = electionEntries.filter((entry) => entry.hasAnyData).length;
  const withBallotpedia = electionEntries.filter((entry) => entry.hasBallotpedia).length;
  const withKalshi = electionEntries.filter((entry) => entry.hasKalshi).length;
  const withFilings = electionEntries.filter((entry) => entry.hasFilings).length;

  summaryEl.textContent = `${electionEntries.length} election entries across ${uniqueSeatCount} seats • ${withAnyData} with any source data • ${withFilings} with filings • ${withBallotpedia} with Ballotpedia • ${withKalshi} with Kalshi`;
}

function renderStateFilter(electionEntries) {
  const stateCodes = [...new Set(electionEntries.map((entry) => entry.stateCode))].sort();
  stateFilterEl.innerHTML = '<option value="">All states</option>';
  stateCodes.forEach((stateCode) => {
    const option = document.createElement('option');
    option.value = stateCode;
    option.textContent = stateCode;
    stateFilterEl.appendChild(option);
  });
}

function seatMatchesFilters(seat) {
  const query = searchEl.value.trim().toLowerCase();
  const stateCode = stateFilterEl.value;
  const coverage = dataFilterEl.value;

  if (stateCode && seat.stateCode !== stateCode) {
    return false;
  }

  if (query && !seat.searchBlob.includes(query)) {
    return false;
  }

  if (coverage === 'withAnyData' && !seat.hasAnyData) {
    return false;
  }

  if (coverage === 'withBallotpedia' && !seat.hasBallotpedia) {
    return false;
  }

  if (coverage === 'withKalshi' && !seat.hasKalshi) {
    return false;
  }

  return true;
}

function seatCoverageBadges(seat) {
  const badges = [
    { label: 'Filings', active: seat.hasFilings },
    { label: 'Ballotpedia', active: seat.hasBallotpedia },
    { label: 'Kalshi', active: seat.hasKalshi },
  ];

  return badges.map((badge) => `
    <span class="debug-badge ${badge.active ? 'debug-badge--active' : ''}">${escapeHtml(badge.label)}</span>
  `).join('');
}

function renderSeatList() {
  visibleElectionEntries = allElectionEntries.filter(seatMatchesFilters);
  seatListEl.innerHTML = '';

  if (!visibleElectionEntries.length) {
    seatListEl.innerHTML = '<li class="debug-seat-list__empty">No elections match the current filters.</li>';
    return;
  }

  if (!visibleElectionEntries.some((entry) => entry.electionEntryId === selectedElectionId)) {
    selectedElectionId = visibleElectionEntries[0].electionEntryId;
  }

  visibleElectionEntries.forEach((seat) => {
    const item = document.createElement('li');
    item.className = 'debug-seat-list__item';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = `debug-seat-button ${seat.electionEntryId === selectedElectionId ? 'debug-seat-button--active' : ''}`;
    button.innerHTML = `
      <span class="debug-seat-button__title">${escapeHtml(seat.displayName)} — ${escapeHtml(seat.selectedElection.label)}</span>
      <span class="debug-seat-button__meta">${escapeHtml(seat.seatId)} • ${escapeHtml(seat.stateName)} • ${escapeHtml(seat.selectedElection.status || 'active')}</span>
      <span class="debug-seat-button__badges">${seatCoverageBadges(seat)}</span>
    `;
    button.addEventListener('click', () => {
      selectedElectionId = seat.electionEntryId;
      renderSeatList();
      renderSelectedSeat();
    });

    item.appendChild(button);
    seatListEl.appendChild(item);
  });
}

function renderCandidateList(candidates = []) {
  if (!candidates.length) {
    return '<p class="lookup-result">No filing candidates found for this seat.</p>';
  }

  return `
    <ul class="debug-candidate-list">
      ${candidates.map((candidate) => `
        <li class="debug-candidate-list__item">
          <strong>${escapeHtml(candidate.name || 'Unknown')}</strong>
          <div class="debug-inline-meta">
            ${escapeHtml(formatPartyLabel(candidate))} • ${escapeHtml(candidate.incumbentStatus || 'Status unknown')}
          </div>
          <div class="debug-inline-meta">
            Candidate ID: ${escapeHtml(candidate.candidateId || 'n/a')} • Source: ${escapeHtml(candidate.filingSource || 'n/a')}
          </div>
        </li>
      `).join('')}
    </ul>
  `;
}

function renderPartyGroups(groups = []) {
  if (!groups.length) {
    return '<p class="lookup-result">No filing party groups are available.</p>';
  }

  return groups.map((group) => `
    <section class="debug-subsection">
      <h3>${escapeHtml(group.partyName || group.partyCode || 'Unknown party')}</h3>
      ${renderCandidateList(group.candidates || [])}
    </section>
  `).join('');
}

function renderSourcePresenceBadge(label, active, count = null) {
  const suffix = count == null ? '' : ` (${count})`;
  return `<span class="debug-badge ${active ? 'debug-badge--active' : ''}">${escapeHtml(`${label}${suffix}`)}</span>`;
}

function summarizeFilingsInfo(candidate) {
  const filing = candidate.sourceEntries.filings[0] || null;
  const candidateId = filing?.candidateId || 'NO CANDIDATE ID FOUND';
  const partyCode = normalizePartyCode(filing?.partyCode || candidate.partyCode);
  return `Fed Filing Info (${candidateId}${partyCode ? `-${partyCode}` : ''})`;
}

function summarizeBallotpediaInfo(candidate) {
  const entries = candidate.sourceEntries.ballotpedia || [];
  const partyCode = entries.map((entry) => normalizePartyCode(entry?.partyCode)).find(Boolean) || 'NO PARTY ID FOUND';
  const isIncumbent = candidate.sourceEntries.filings.some((entry) => entry?.incumbentStatus === 'INCUMBENT');
  const isNominated = entries.some((entry) => entry?.sourceSection === 'general' || entry?.sourceSection === 'advanced');
  const details = [partyCode, isIncumbent ? 'Incumbent' : '', isNominated ? 'Nominated' : ''];
  return `Ballotpedia (${details.join(', ')})`;
}

function summarizeKalshiInfo(candidate) {
  const match = candidate.kalshiMatch;
  if (!match?.matched) {
    return 'Kalshi (NO KALSHI MARKET FOUND)';
  }

  const parts = [
    match.kalshiName || 'Unnamed market',
    match.kalshiOddsPercent != null ? `${Number(match.kalshiOddsPercent).toFixed(2)}%` : 'No odds',
    match.kalshiMarketTicker || 'NO TICKER FOUND',
    match.matchType ? `${match.matchType} match` : '',
  ].filter(Boolean);

  return `Kalshi (${parts.join(', ')})`;
}

function renderUnifiedCandidateLabels(candidate) {
  return [
    summarizeFilingsInfo(candidate),
    summarizeBallotpediaInfo(candidate),
    summarizeKalshiInfo(candidate),
  ].map((label) => `<div class="debug-inline-meta">${escapeHtml(label)}</div>`).join('');
}

function renderUnifiedCandidates(seat) {
  const electionCandidates = Array.isArray(seat.selectedElection?.candidates) ? seat.selectedElection.candidates : [];
  const electionCandidateIds = new Set(electionCandidates.map((candidate) => String(candidate?.candidateId || '')).filter(Boolean));
  const electionCandidateNames = new Set(electionCandidates.map((candidate) => normalizeName(candidate?.name || '')).filter(Boolean));
  const candidates = (seat.unifiedCandidates || []).filter((candidate) => {
    if (!electionCandidateIds.size && !electionCandidateNames.size) {
      return true;
    }
    const filingEntries = candidate.sourceEntries.filings || [];
    return filingEntries.some((entry) => (
      electionCandidateIds.has(String(entry?.candidateId || ''))
      || electionCandidateNames.has(normalizeName(entry?.name || ''))
    ));
  });
  if (!candidates.length) {
    unifiedEl.innerHTML = '<p class="lookup-result">No candidate data from any source is available for this election.</p>';
    return;
  }

  const fullyMatchedCount = candidates.filter((candidate) =>
    candidate.sourceEntries.filings.length
    && candidate.sourceEntries.ballotpedia.length
    && candidate.sourceEntries.kalshi.length,
  ).length;

  unifiedEl.innerHTML = `
    <p class="debug-source-summary">
      ${escapeHtml(String(candidates.length))} known candidates • ${escapeHtml(String(fullyMatchedCount))} matched across filings, Ballotpedia, and Kalshi
    </p>
    <ul class="debug-candidate-list debug-candidate-list--unified">
      ${candidates.map((candidate) => {
        const filingsEntries = candidate.sourceEntries.filings;
        const ballotpediaEntries = candidate.sourceEntries.ballotpedia;
        const kalshiEntries = candidate.sourceEntries.kalshi;

        return `
          <li class="debug-candidate-list__item debug-candidate-list__item--unified">
            <div class="debug-unified-header">
              <div>
                <strong>${escapeHtml(candidate.displayName || 'Unknown')}</strong>
                ${renderUnifiedCandidateLabels(candidate)}
              </div>
              <span class="debug-inline-meta">${escapeHtml(formatUnifiedParty(candidate.partyCode))}</span>
            </div>
            <div class="debug-unified-badges">
              ${renderSourcePresenceBadge('Filings', filingsEntries.length > 0, filingsEntries.length || null)}
              ${renderSourcePresenceBadge('Ballotpedia', ballotpediaEntries.length > 0, ballotpediaEntries.length || null)}
              ${renderSourcePresenceBadge('Kalshi', kalshiEntries.length > 0, kalshiEntries.length || null)}
            </div>
            <div class="debug-subsection">
              <h3>Fed Filing Info</h3>
              ${filingsEntries.length ? renderCandidateList(filingsEntries) : '<p class="lookup-result">No filing match.</p>'}
            </div>
            <div class="debug-subsection">
              <h3>Ballotpedia Info</h3>
              ${ballotpediaEntries.length ? `
                <ul class="debug-line-list">
                  ${ballotpediaEntries.map((entry) => `<li>${escapeHtml(entry.sourceLine || entry.name)}</li>`).join('')}
                </ul>
              ` : '<p class="lookup-result">No Ballotpedia match.</p>'}
            </div>
            <div class="debug-subsection">
              <h3>Kalshi Market Info</h3>
              ${kalshiEntries.length ? renderKalshiMarkets(kalshiEntries) : '<p class="lookup-result">No Kalshi market match.</p>'}
            </div>
          </li>
        `;
      }).join('')}
    </ul>
  `;
}

function renderFilings(seat) {
  const election = seat.selectedElection?.sourceElection || seat.filings;
  if (!election) {
    filingsEl.innerHTML = '<p class="lookup-result">No congressional filing payload exists for this election.</p>';
    return;
  }

  const selectedCandidates = Array.isArray(seat.selectedElection?.candidates) ? seat.selectedElection.candidates : (election.candidates || []);
  const isGeneralElection = seat.selectedElection?.electionKind === 'general';
  const candidateGroups = isGeneralElection
    ? (election.candidatesByParty || []).map((group) => ({
        ...group,
        candidates: (group.candidates || []).filter((candidate) =>
          selectedCandidates.some((selectedCandidate) => String(selectedCandidate?.candidateId || '') === String(candidate?.candidateId || '')),
        ),
      })).filter((group) => group.candidates.length)
    : [{
        partyCode: election.partyCode || seat.selectedElection?.partyCode || 'UNK',
        partyName: election.partyName || formatUnifiedParty(election.partyCode || seat.selectedElection?.partyCode),
        candidates: selectedCandidates,
      }];

  filingsEl.innerHTML = `
    <p class="debug-source-summary">
      ${escapeHtml(election.electionId || seat.seatId)} • ${escapeHtml(seat.selectedElection?.label || 'General')} • ${escapeHtml(seat.selectedElection?.status || election.status || 'active')} • ${escapeHtml(String(selectedCandidates.length || 0))} candidates
    </p>
    <dl class="debug-definition-list">
      <div><dt>Election cycle</dt><dd>${escapeHtml(election.electionCycle || 'n/a')}</dd></div>
      <div><dt>Election kind</dt><dd>${escapeHtml(seat.selectedElection?.electionKind || election.electionKind || 'n/a')}</dd></div>
      <div><dt>Nomination status</dt><dd>${escapeHtml(election.nominationStatus?.primaryStatus || 'n/a')}</dd></div>
      <div><dt>Primary system</dt><dd>${escapeHtml(election.nominationStatus?.primarySystem || 'n/a')}</dd></div>
    </dl>
    <section class="debug-subsection">
      <h3>${escapeHtml(seat.selectedElection?.label || 'General')} candidates</h3>
      ${renderCandidateList(selectedCandidates)}
    </section>
    <section class="debug-subsection">
      <h3>Candidates by party</h3>
      ${renderPartyGroups(candidateGroups)}
    </section>
  `;
}

function renderBallotpediaLines(lines = []) {
  if (!lines.length) {
    return '<p class="lookup-result">No lines captured for this section.</p>';
  }

  return `
    <ul class="debug-line-list">
      ${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}
    </ul>
  `;
}

function renderBallotpediaPrimarySections(sections = {}) {
  const entries = Object.entries(sections);
  if (!entries.length) {
    return '<p class="lookup-result">No Ballotpedia primary sections were parsed.</p>';
  }

  return entries.map(([party, lines]) => `
    <section class="debug-subsection">
      <h3>${escapeHtml(party)}</h3>
      ${renderBallotpediaLines(Array.isArray(lines) ? lines : [])}
    </section>
  `).join('');
}

function renderBallotpedia(seat) {
  const record = seat.ballotpedia;
  const data = record?.election?.ballotpedia;
  if (!record || !data) {
    ballotpediaEl.innerHTML = '<p class="lookup-result">No Ballotpedia payload exists for this seat.</p>';
    return;
  }

  ballotpediaEl.innerHTML = `
    <p class="debug-source-summary">
      Source file: ${escapeHtml(record.source?.sourceStateFile || 'n/a')} • ${escapeHtml(record.source?.statePageUrl || 'No page URL')}
    </p>
    <section class="debug-subsection">
      <h3>Notes</h3>
      ${renderBallotpediaLines(data.notes || [])}
    </section>
    <section class="debug-subsection">
      <h3>General election candidates</h3>
      ${renderBallotpediaLines(data.generalElectionCandidateLines || [])}
    </section>
    <section class="debug-subsection">
      <h3>Primary candidates by party</h3>
      ${renderBallotpediaPrimarySections(data.primaryCandidateSections || {})}
    </section>
    <section class="debug-subsection">
      <h3>Advanced from primary</h3>
      ${renderBallotpediaLines(data.advancedFromPrimaryLines || [])}
    </section>
    <section class="debug-subsection">
      <h3>Scrape quality flags</h3>
      ${renderBallotpediaLines(data.scrapeQualityFlags || [])}
    </section>
  `;
}

function renderKalshiMarkets(markets = []) {
  if (!markets.length) {
    return '<p class="lookup-result">No Kalshi markets are linked to this seat.</p>';
  }

  return `
    <ul class="debug-market-list">
      ${markets.map((market) => `
        <li class="debug-market-list__item">
          <strong>${escapeHtml(market.title || market.marketTicker || 'Untitled market')}</strong>
          <div class="debug-inline-meta">
            ${escapeHtml(market.marketType || 'unknown')} • ${escapeHtml(market.electionType || 'unknown')} • ${escapeHtml(market.party || 'n/a')}
          </div>
          <div class="debug-inline-meta">
            Ticker: ${escapeHtml(market.marketTicker || 'n/a')} • Contest key: ${escapeHtml(market.normalizedContestKey || 'n/a')}
          </div>
          <div class="debug-inline-meta">
            Entity: ${escapeHtml(market.entityName || market.yesSubtitle || 'n/a')} • Odds: ${escapeHtml(market.oddsPercent ?? 'n/a')}
          </div>
          <details class="debug-market-details">
            <summary>Show source metadata</summary>
            <div class="debug-market-details__content">
              <p><strong>Series:</strong> ${escapeHtml(market.seriesTitle || market.seriesTicker || 'n/a')}</p>
              <p><strong>Rules:</strong> ${escapeHtml(market.rulesPrimary || 'No rules text')}</p>
              <p><strong>Source file:</strong> ${escapeHtml(market.sourceFile || 'n/a')}</p>
            </div>
          </details>
        </li>
      `).join('')}
    </ul>
  `;
}

function renderKalshi(seat) {
  const record = seat.kalshi;
  if (!record) {
    kalshiEl.innerHTML = '<p class="lookup-result">No Kalshi payload exists for this seat.</p>';
    return;
  }

  kalshiEl.innerHTML = `
    <p class="debug-source-summary">
      ${escapeHtml(String(record.marketCount || 0))} linked markets for ${escapeHtml(record.districtLabel || seat.displayName)}
    </p>
    ${renderKalshiMarkets(record.markets || [])}
  `;
}

function renderSelectedSeat() {
  const seat = visibleElectionEntries.find((item) => item.electionEntryId === selectedElectionId) || visibleElectionEntries[0] || null;
  if (!seat) {
    titleEl.textContent = 'No election selected';
    metaEl.textContent = 'Adjust filters to show at least one election.';
    unifiedEl.innerHTML = '<p class="lookup-result">No data available.</p>';
    filingsEl.innerHTML = '<p class="lookup-result">No data available.</p>';
    ballotpediaEl.innerHTML = '<p class="lookup-result">No data available.</p>';
    kalshiEl.innerHTML = '<p class="lookup-result">No data available.</p>';
    return;
  }

  selectedElectionId = seat.electionEntryId;
  titleEl.textContent = `${seat.displayName} — ${seat.selectedElection.label}`;
  metaEl.textContent = `${seat.stateName} • ${seat.districtLabel} • ${seat.seatId} • Status: ${seat.selectedElection.status || 'active'} • Filings: ${seat.hasFilings ? 'yes' : 'no'} • Ballotpedia: ${seat.hasBallotpedia ? 'yes' : 'no'} • Kalshi: ${seat.hasKalshi ? 'yes' : 'no'}`;

  renderUnifiedCandidates(seat);
  renderFilings(seat);
  renderBallotpedia(seat);
  renderKalshi(seat);
}

function handleFiltersChanged() {
  renderSeatList();
  renderSelectedSeat();
}

async function initialize() {
  try {
    const [seatPayload, ballotpediaPayload, kalshiPayload] = await Promise.all([
      fetchJsonWithFallback(SEAT_SOURCES),
      fetchJsonWithFallback(BALLOTPEDIA_SOURCES),
      fetchJsonWithFallback(KALSHI_SOURCES),
    ]);

    allElectionEntries = joinSeatSources(seatPayload, ballotpediaPayload, kalshiPayload)
      .sort((left, right) => `${left.seatId} ${left.selectedElection.label}`.localeCompare(`${right.seatId} ${right.selectedElection.label}`));

    renderStateFilter(allElectionEntries);
    renderSummary(allElectionEntries);
    setStatus(`Loaded ${allElectionEntries.length} election entries across ${new Set(allElectionEntries.map((entry) => entry.seatId)).size} canonical seats.`);

    searchEl.addEventListener('input', handleFiltersChanged);
    stateFilterEl.addEventListener('change', handleFiltersChanged);
    dataFilterEl.addEventListener('change', handleFiltersChanged);

    handleFiltersChanged();
  } catch (error) {
    console.error(error);
    setStatus(error instanceof Error ? error.message : 'Unknown loading error', { error: true });
    summaryEl.textContent = 'Unable to load seat data for the debug view.';
    seatListEl.innerHTML = '<li class="debug-seat-list__empty">The debug view could not be initialized.</li>';
  }
}

initialize();
