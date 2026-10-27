import csv

f='PowerVote/apps/web/data/candidate-rollup-2026-ballotpedia-only.csv'
with open(f, encoding='utf-8') as fh:
    r=list(csv.DictReader(fh))

bad=[x for x in r if (not (x.get('Primary ID') or '').strip()) and (not (x.get('RunoffID') or '').strip()) and (x.get('Status')!='general (nominated)')]
print('bad_count:',len(bad))
for x in bad[:50]:
    print(f"{x.get('Candidate')} | {x.get('2026 Seat')} | {x.get('Status')} | {x.get('statusReason')} | identityMatchStrategy={x.get('identityMatchStrategy')}")
