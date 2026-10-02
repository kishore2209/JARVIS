"""Render the audited inventory; does not infer requirement completion from files."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = json.loads((root/'docs/srd/traceability.json').read_text())
lines = ['# SRD v3 requirement audit', '', 'Conservative implementation inventory, not production certification. IMPLEMENTED_LOCAL_SCOPE covers only the explicitly described local scope. PARTIAL requirements have unmet criteria. Candidate references do not establish full acceptance.', '', '| ID | Requirement | Status | Implementation / test evidence | Remaining gap or scope |', '|---|---|---|---|---|']
for row in rows:
    evidence = '; '.join('`'+p+'`' for p in row['implementation']+row['tests']) or 'None'
    values = [row['id'],row['requirement'],row['status'],evidence,row['gap']]
    lines.append('| '+' | '.join(str(v).replace('|','\\|').replace('\n',' ') for v in values)+' |')
(root/'docs/srd/TRACEABILITY.md').write_text('\n'.join(lines)+'\n')
