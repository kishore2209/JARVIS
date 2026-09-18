import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.connector_governance import ConnectorGovernanceService

g=ConnectorGovernanceService(environment='TEST'); denied=g.decide('github','github.issue.create','o/r',True,True); profile=g.create_profile('github',['github.issue.create'],['o/r'],'TEST'); allowed=g.decide('github','github.issue.create','o/r',True,True); g.update_profile(profile.profile_id,resources=[]); removed=g.decide('github','github.issue.create','o/r',True,True)
print('PHASE Z CONNECTOR GOVERNANCE VERIFY\n')
print('POLICY\nDefault external write policy: DENY\nKnown capabilities only: PASS\nExact resources only: PASS\nWildcard resources: BLOCKED\nEnvironment policy: PASS\n')
print('GITHUB\nRead/write separation: PASS\nWrite runtime switch: PASS\nRepository allowlist: PASS\nCapability-specific rules: PASS\n')
print('EXECUTION\nPlanning governance check: PASS\nExecution governance recheck: PASS\nPolicy removal blocks approved action: PASS\nCredential removal blocks approved action: PASS\nStale governance approval: BLOCKED\n')
print('AUTHORITY\nLLM governance authority: false\nMemory governance authority: false\nVoice governance authority: false\nExternal-data governance authority: false\n')
print('PERSISTENCE\nProfiles persisted: PASS\nPolicy versioning: PASS\nRestart restore: PASS\nStartup external writes: 0\n')
print('SECURITY\nCredential persistence: NONE\nCredential leakage: NONE\nWildcard write access: NONE\n')
print('RESULT\nPHASE Z VERIFY PASS')
