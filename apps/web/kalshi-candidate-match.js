export function normalizeName(value) {
  return String(value || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\(.*?\)/g, ' ')
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function normalizePartyCode(value) {
  const normalized = String(value || '').trim().toUpperCase();
  if (!normalized) return null;
  if (['DEM', 'D'].includes(normalized)) return 'DEM';
  if (['REP', 'R', 'GOP'].includes(normalized)) return 'REP';
  if (['IND', 'I'].includes(normalized)) return 'IND';
  if (['LIB', 'L'].includes(normalized)) return 'LIB';
  if (['GRE', 'GRN', 'G'].includes(normalized)) return 'GRE';
  if (['OTH', 'O'].includes(normalized)) return 'OTH';

  const lowered = String(value || '').trim().toLowerCase();
  if (lowered === 'democratic') return 'DEM';
  if (lowered === 'republican') return 'REP';
  if (lowered === 'independent') return 'IND';
  if (lowered === 'libertarian') return 'LIB';
  if (lowered === 'green') return 'GRE';
  if (lowered === 'other') return 'OTH';
  return normalized;
}

export function buildCandidateMatchKeys(name, partyCode, aliases = []) {
  const normalizedParty = normalizePartyCode(partyCode);
  const names = [name, ...aliases]
    .map((value) => normalizeName(value))
    .filter(Boolean);
  const keys = new Set();

  names.forEach((normalizedName) => {
    keys.add(`${normalizedName}|${normalizedParty || ''}`);
    keys.add(`${normalizedName}|`);
    const tokens = normalizedName.split(' ').filter(Boolean);
    if (tokens.length >= 2) {
      const compressed = `${tokens[0]} ${tokens[tokens.length - 1]}`;
      keys.add(`${compressed}|${normalizedParty || ''}`);
      keys.add(`${compressed}|`);
    }
  });

  return keys;
}

function getMarketCandidateNames(market = {}) {
  return [market.entityName, market.yesSubtitle]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
}

function buildKalshiCandidateMatchResult(match = null, matchType = null) {
  return {
    matched: Boolean(match),
    matchType: match ? matchType : null,
    kalshiName: match?.kalshiName || null,
    kalshiOddsPercent: match?.oddsPercent ?? null,
    kalshiMarketTicker: match?.marketTicker || null,
    kalshiStatus: match?.status || null,
    kalshiMarketTitle: match?.title || null,
    kalshiYesSubtitle: match?.yesSubtitle || null,
  };
}

export function buildKalshiCandidateLookup(markets = []) {
  const candidateOddsByKey = new Map();
  const normalizedCandidates = [];

  markets.forEach((market) => {
    const names = getMarketCandidateNames(market);
    if (!names.length) {
      return;
    }

    const matchCandidate = {
      kalshiName: String(market.entityName || market.yesSubtitle || '').trim() || null,
      oddsPercent: market.oddsPercent,
      marketTicker: market.marketTicker,
      status: market.status,
      title: market.title || null,
      yesSubtitle: market.yesSubtitle || null,
      entityName: market.entityName || null,
      partyCode: normalizePartyCode(market.party),
      market,
    };

    if (!normalizedCandidates.some((candidate) => candidate.marketTicker === matchCandidate.marketTicker)) {
      normalizedCandidates.push(matchCandidate);
    }

    buildCandidateMatchKeys(names[0], market.party, names.slice(1)).forEach((key) => {
      const existing = candidateOddsByKey.get(key);
      if (!existing || (Number(matchCandidate.oddsPercent) || 0) > (Number(existing.oddsPercent) || 0)) {
        candidateOddsByKey.set(key, matchCandidate);
      }
    });
  });

  return {
    candidateOddsByKey,
    normalizedCandidates,
  };
}

export function matchCandidateToKalshi(candidate = {}, lookup = { candidateOddsByKey: new Map(), normalizedCandidates: [] }, options = {}) {
  const { fuzzyScorer = null, fuzzyThreshold = 60 } = options;
  const candidateNames = [candidate?.name, candidate?.kalshiName, ...(candidate?.aliases || [])].filter(Boolean);
  const candidateKeys = buildCandidateMatchKeys(candidateNames[0], candidate?.partyCode, candidateNames.slice(1));

  for (const key of candidateKeys) {
    const exactMatch = lookup.candidateOddsByKey.get(key);
    if (exactMatch) {
      return buildKalshiCandidateMatchResult(exactMatch, 'exact');
    }
  }

  if (typeof fuzzyScorer !== 'function') {
    return buildKalshiCandidateMatchResult();
  }

  let bestMatch = null;
  let bestScore = 0;
  lookup.normalizedCandidates.forEach((marketCandidate) => {
    candidateNames.forEach((candidateName) => {
      [marketCandidate.entityName, marketCandidate.yesSubtitle].filter(Boolean).forEach((marketName) => {
        const score = fuzzyScorer(candidateName, marketName);
        if (score > bestScore) {
          bestScore = score;
          bestMatch = marketCandidate;
        }
      });
    });
  });

  if (bestMatch && bestScore >= fuzzyThreshold) {
    return buildKalshiCandidateMatchResult(bestMatch, 'fuzzy');
  }

  return buildKalshiCandidateMatchResult();
}
