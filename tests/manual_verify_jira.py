import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

required=('JARVIS_JIRA_ENABLED','JIRA_BASE_URL','JIRA_EMAIL','JIRA_API_TOKEN','JARVIS_RUN_JIRA_SMOKE')
if not all(os.getenv(name) for name in required) or os.getenv('JARVIS_JIRA_ENABLED')!='true' or os.getenv('JARVIS_RUN_JIRA_SMOKE')!='true':
    print('JIRA MANUAL SMOKE: SKIPPED - NOT CONFIGURED')
    raise SystemExit(0)
from core.connectors import ConnectorRegistry, ConnectorRequest, ConnectorService
from core.jira_connector import build_jira_connector
descriptor,adapter=build_jira_connector(enabled=True); registry=ConnectorRegistry(); registry.register(descriptor,adapter); result=ConnectorService(registry).read(ConnectorRequest('MANUAL','jira','jira.projects.list',{})); print(f'JIRA MANUAL SMOKE: status={result.status} connector=jira capability=jira.projects.list items={len(result.data) if isinstance(result.data,list) else 0}')
