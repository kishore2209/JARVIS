import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connector_governance import ConnectorGovernanceService, GovernanceValidationError
from market.persistence import SQLiteStore

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    governance=ConnectorGovernanceService(environment='TEST')
    denied=governance.decide('github','github.issue.create','o/r',True,True)
    check('Default deny', not denied.allowed and denied.reason_code=='PROFILE_NOT_FOUND')
    profile=governance.create_profile('github',['github.issue.create'],['o/r'],'TEST')
    check('Create profile', profile.version==1)
    check('Exact repo allow', governance.decide('github','github.issue.create','o/r',True,True).allowed)
    check('Unknown repo deny', not governance.decide('github','github.issue.create','o/x',True,True).allowed)
    for resource in ('*','o/*','*/r','https://github.com/o/r'):
        try: governance.create_profile('github',['github.issue.create'],[resource],'TEST'); valid=True
        except GovernanceValidationError: valid=False
        check('Wildcard/malformed rejected', not valid)
    check('Allowed capability', governance.decide('github','github.issue.create','o/r',True,True).allowed)
    check('Blocked capability', not governance.decide('github','github.issue.comment','o/r',True,True).allowed)
    check('Environment deny', not ConnectorGovernanceService(environment='PRODUCTION').decide('github','github.issue.create','o/r',True,True).allowed)
    governance.update_profile(profile.profile_id, enabled=False); check('Disabled profile', not governance.decide('github','github.issue.create','o/r',True,True).allowed)
    governance.update_profile(profile.profile_id, enabled=True, resources=['o/r']); check('Version increments', governance.profiles[profile.profile_id].version==3)
    check('Write disabled', governance.decide('github','github.issue.create','o/r',True,False).reason_code=='WRITE_DISABLED')
    check('Credential missing', governance.decide('github','github.issue.create','o/r',False,True).reason_code=='CREDENTIAL_NOT_CONFIGURED')
    check('Token not stored', 'TOKEN' not in str(governance.safe_list()))
    path=tempfile.mktemp(suffix='.db'); store=SQLiteStore(path); first=ConnectorGovernanceService(store,'TEST'); first.create_profile('github',['github.issue.create'],['o/r'],'TEST'); store.close(); store=SQLiteStore(path); second=ConnectorGovernanceService(store,'TEST'); check('Persistence restart restore', len(second.safe_list())==1); store.close(); os.remove(path)
    print('TEST SUMMARY: 15/15 PASS')
if __name__=='__main__': main()
