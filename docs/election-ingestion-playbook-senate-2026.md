# Election Ingestion Playbook: Senate 2026

## Summary
This document is the compact context for how Senate 2026 was added end-to-end:
- parse Ballotpedia Senate raw pages
- link FEC data
- classify/map Kalshi markets
- publish rollups and QA artifacts
- surface Senate data in map and PowerVote UI

Use this as the template for future Ballotpedia election onboarding.

## What We Built
- Ballotpedia Senate parsing from raw source, including national overlays:
  - `ballotpedia_senate_raw/*.txt`
  - incumbency/departures from `National.txt` (pre-election incumbent + departures sections)
- Senate seat canon:
  - regular: `XX-SEN-C1|C2|C3`
  - class-bound special: `XX-SEN-C{N}-SPL`
  - unbound special fallback: `XX-SEN-SP1`
- FEC linkage for Senate candidates with conflict surfacing (no silent overwrite).
- Kalshi Senate framework that ingests all relevant files and classifies:
  - `candidate_nominee`
  - `candidate_winner`
  - `party_winner`
- Strict Kalshi mapping policy with fail-closed publication behavior.
- Candidate matching policy with confidence tiers, scoped overrides, and high-impact gating (`oddsPercent > 2`).
- UI/API integration:
  - statewide Senate map mode with split/special seat handling
  - PowerVote cross-office endpoint: `GET /api/v1/powervote/all`
  - grouped House + Senate election rendering in PowerVote UI.

## Canonical Artifacts and Contracts
- Ballotpedia Senate rollups:
  - `apps/web/data/ballotpedia-senate-general-election-rollup.csv`
  - `apps/web/data/ballotpedia-senate-primary-election-rollup.csv`
  - `apps/web/data/ballotpedia-senate-runoff-election-rollup.csv`
  - `apps/web/data/ballotpedia-senate-incumbent-departures.csv`
- Senate candidate rollups:
  - `apps/web/data/candidate-rollup-senate-2026.csv`
  - `apps/web/data/candidate-rollup-senate-2026-fec.csv`
- Kalshi Senate outputs:
  - `apps/web/data/kalshi-senate-candidate-nominee.csv`
  - `apps/web/data/kalshi-senate-candidate-winner.csv`
  - `apps/web/data/kalshi-senate-party-winner.csv`
  - `apps/web/data/kalshi-us-senate-contest-index.csv`
  - `apps/web/data/kalshi-senate-candidate-match-report.json`
- Public API addition:
  - `GET /api/v1/powervote/all` (additive; legacy `/powervote` and `/powervote/compare` remain stable)

## Lessons Learned
- Parse national pages as first-class sources, not fallback scraps.
  - Senate incumbency quality materially improved only after using `National.txt` overlays.
- Keep office behavior adapter-based.
  - Reusing House pipeline via office parameterization prevented logic drift.
- Enforce fail-closed mapping for Kalshi.
  - Allowed immediate detection of inference gaps instead of silent market drops.
- General market inference must not depend on explicit `GENERAL` labels.
  - Winner-election language in titles/rules is required for coverage.
- Matching must be deterministic and auditable.
  - Confidence tiers + reason codes + scoped overrides are necessary for trust.
- High-impact unresolved thresholds are practical.
  - Blocking only `oddsPercent > 2` rows kept quality strict without freezing low-impact tails.
- Transparency artifacts are mandatory.
  - Unmapped/ambiguous/conflict reports accelerated debugging and reviewer confidence.

## Repeatable Checklist for New Elections
1. Source parse and seat canon
- Build office-specific seat-id scheme and parser tests first.
- Parse raw Ballotpedia files including national overlays.
- Emit general/primary/runoff/departure rollups with schema parity to existing office where intended.

2. External linkage
- Link FEC with deterministic keys + controlled fallback.
- Emit linkage audit/conflict outputs; never silently replace conflicting fields.

3. Kalshi ingestion and mapping
- Ingest all candidate/party outcome market files.
- Classify round and market type deterministically.
- Map to canonical `office + cycle + seat + round + party`.
- Fail closed on unresolved included rows.

4. Candidate matching and gating
- Apply tiered matching policy and scoped override registry.
- Block on unresolved high-impact rows (`oddsPercent > threshold`).
- Publish match reports with reason codes and review status.

5. Rollup publish and UI integration
- Refresh rollups and contest index artifacts.
- Add/extend API contracts additively.
- Wire UI mode changes with keyboard/accessibility parity.

6. Validation and closeout
- Run unit + integration + contract tests.
- Produce closeout summary with before/after counts and unresolved inventory.

## Bot Handoff Protocol (Use This Every Time)
1. Read these first:
- `docs/election-ingestion-playbook-senate-2026.md`
- `README.md` sections on PowerVote and pipeline scripts

2. Run these baseline commands:
```bash
python scripts/parse_ballotpedia_senate_raw.py
python scripts/build_kalshi_us_senate_contest_index.py
python scripts/build_candidate_rollup_senate.py
python -m unittest -v tests/test_ballotpedia_senate_rollup_parser.py tests/test_kalshi_senate_contest_index.py tests/test_kalshi_candidate_name_mapping_reports.py
```

3. Mandatory outputs to inspect:
- Senate rollups in `apps/web/data/ballotpedia-senate-*.csv`
- Kalshi Senate reports (`unmapped`, `ambiguous`, `coverage`, `match-report`)
- Candidate rollup integrity signals

4. Do not proceed if any gate fails:
- unresolved included Kalshi mappings
- unresolved high-impact candidate matches above threshold
- schema contract regression vs existing consumer contracts

5. Final report format:
- what changed
- blocking vs non-blocking gaps
- exact commands run
- artifact paths for reviewer verification

## Open Gaps / Deferred Work
- Local-first storage completion:
  - MinIO immutable object upload/write path
  - restore-from-manifest flow and restore test
- House strict contest integrity cleanup remains separate from Senate completion.
