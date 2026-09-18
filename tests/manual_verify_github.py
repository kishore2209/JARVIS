import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRequest, ConnectorService, ConnectorRegistry
from core.github_connector import build_github_connector

if not os.getenv('GITHUB_TOKEN'):
    print('GITHUB MANUAL SMOKE: SKIPPED - NOT CONFIGURED')
    raise SystemExit(0)
if os.getenv('JARVIS_RUN_GITHUB_SMOKE','false').lower() != 'true':
    print('GITHUB MANUAL SMOKE: SKIPPED - NOT ENABLED')
    raise SystemExit(0)
descriptor, adapter = build_github_connector(enabled=True)
registry=ConnectorRegistry(); registry.register(descriptor, adapter)
result=ConnectorService(registry).read(ConnectorRequest('MANUAL','github','github.repositories.list',{'per_page':'10'}))
print(f'GITHUB MANUAL SMOKE: status={result.status} connector={result.connector_id} capability={result.capability_id} items={len(result.data) if isinstance(result.data,list) else 0}')
