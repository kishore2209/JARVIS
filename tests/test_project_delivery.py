import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.project_delivery import ProjectDeliveryConfig, ProjectDeliveryService
from core.project_intelligence import ProjectSnapshot, ProjectEvidenceLink

def check(name,condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def snap(partial=False):
    now=datetime(2026,1,31,tzinfo=timezone.utc)
    return ProjectSnapshot('s','w',now,True,True,partial,({'key':'JAR-1','fields':{'status':{'name':'Open'},'updated':'2026-01-01T00:00:00Z'}},),({'number':2,'state':'open','updated_at':'2026-01-01T00:00:00Z','title':'JAR-1 work'},),(),(ProjectEvidenceLink('JAR-1','PR_TITLE_BODY','PR#2','o/r','JAR-1 work','DIRECT_REFERENCE','2026-01-01T00:00:00Z',now),),(),(),())

def main():
    config=ProjectDeliveryConfig();check('Valid config',config.jira_stale_days==14)
    for key in ('jira_stale_days','pr_stale_days','max_attention_items'):
        try: ProjectDeliveryConfig(**{key:0});valid=True
        except ValueError:valid=False
        check('Invalid config rejected',not valid)
    service=ProjectDeliveryService(type('P',(),{'snapshots':{'w':snap()}})(),config)
    analysis=service.analyze('w',now=datetime(2026,1,31,tzinfo=timezone.utc));check('Current analysis',analysis.metrics['jira_issue_count']==1)
    check('Stale signals',any(item.signal_type=='STALE_JIRA_ISSUE' for item in analysis.signals) and any(item.signal_type=='STALE_PULL_REQUEST' for item in analysis.signals))
    check('Deterministic brief', 'SNAPSHOT SUMMARY' in service.brief(analysis))
    partial=service.analyze('w',snap(True),snap(),now=datetime(2026,1,31,tzinfo=timezone.utc));check('Partial data warning',partial.completeness is False and 'PARTIAL_COMPARISON' in partial.warnings)
    check('No prediction',all(word not in service.brief(analysis).lower() for word in ('probability','completion date','health score')))
    print('TEST SUMMARY: 6/6 PASS')
if __name__=='__main__':main()
