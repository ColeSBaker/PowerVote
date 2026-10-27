import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_CSV = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-2026.csv"

rows = []
with CANDIDATE_CSV.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

total = len(rows)
canonical = [r for r in rows if (r.get("identityMatchStrategy") or "").strip() == "canonical_candidate"]

missing_ballotpedia = []
for r in rows:
    primary_id = (r.get("Primary ID") or "").strip()
    runoff_id = (r.get("RunoffID") or "").strip()
    status_reason = (r.get("statusReason") or "").strip()
    try:
        flags = json.loads(r.get("sourceFlags") or "{}")
    except Exception:
        flags = {}
    has_primary = bool(flags.get("hasPrimaryResults"))
    has_runoff = bool(flags.get("hasRunoffResults"))

    # Candidate not linked to Ballotpedia if it has no primary/runoff id and
    # no primary/runoff results and statusReason indicates not present OR
    # it was produced from canonical candidate data.
    if (not primary_id and not runoff_id and not has_primary and not has_runoff and status_reason == "not_present_in_ballotpedia_election_sets") or ((r.get("identityMatchStrategy") or "").strip() == "canonical_candidate" and not primary_id and not runoff_id):
        missing_ballotpedia.append(r)

print("Total candidate rows:", total)
print("Canonical-candidate rows:", len(canonical))
print("Rows missing ballotpedia linkage (as defined):", len(missing_ballotpedia))

from collections import Counter
by_state = Counter()
by_seat = Counter()
for r in missing_ballotpedia:
    seat = (r.get("2026 Seat") or "").strip()
    state = seat.split("-")[0] if "-" in seat else seat
    by_state[state] += 1
    by_seat[seat] += 1

print("\nTop states with missing linkage:")
for state,count in by_state.most_common(10):
    print(f"- {state}: {count}")

print("\nTop seats with missing linkage (top 30):")
for seat,count in by_seat.most_common(30):
    print(f"- {seat}: {count}")

print("\nSample missing rows (up to 50):")
for r in missing_ballotpedia[:50]:
    print(f"{r.get('Candidate')} | {r.get('2026 Seat')} | {r.get('Party')} | statusReason={r.get('statusReason')} | identityMatchStrategy={r.get('identityMatchStrategy')} | PrimaryID={r.get('Primary ID')} | RunoffID={r.get('RunoffID')}")
