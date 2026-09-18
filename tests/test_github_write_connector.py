import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRegistry, ConnectorRequest, ConnectorService
from core.github_connector import FakeGitHubTransport, build_github_connector

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    fake=FakeGitHubTransport(); descriptor, adapter=build_github_connector(enabled=True, token='secret', transport=fake, write_enabled=True); registry=ConnectorRegistry(); registry.register(descriptor, adapter); service=ConnectorService(registry)
    check('Write enabled config', descriptor.write_enabled)
    check('Token status boolean only', 'secret' not in str(descriptor))
    result=service.write(ConnectorRequest('1','github','github.issue.create',{'owner':'o','repo':'r','title':'Title','body':'Body'}))
    check('Issue create valid request', result.status == 'SUCCEEDED' and result.data['title']=='Title')
    comment=service.write(ConnectorRequest('2','github','github.issue.comment',{'owner':'o','repo':'r','issue_number':'1','body':'Comment'}))
    check('Issue comment valid', comment.status == 'SUCCEEDED')
    pr=service.write(ConnectorRequest('3','github','github.pull_request.comment',{'owner':'o','repo':'r','pull_number':'2','body':'Comment'}))
    check('PR comment valid', pr.status == 'SUCCEEDED')
    check('Only internal POST endpoints', all(call[0]=='POST' and call[1].startswith('/repos/') for call in fake.calls))
    for cap in ('github.issue.update','github.pull_request.merge','github.workflow.dispatch'):
        failed=service.write(ConnectorRequest('x','github',cap,{})); check(f'{cap} blocked', failed.status == 'FAILED')
    check('Token not exposed', 'secret' not in repr(result))
    print('TEST SUMMARY: 8/8 PASS')
if __name__ == '__main__': main()
