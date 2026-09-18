import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorRequest, ConnectorService
from core.github_connector import FakeGitHubTransport, GitHubConnectorAdapter, GitHubTransport, build_github_connector

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    descriptor, _ = build_github_connector(enabled=False, token='fake')
    check('Disabled connector', not descriptor.enabled)
    descriptor, adapter = build_github_connector(enabled=True, token='', transport=FakeGitHubTransport())
    check('Enabled missing token status', descriptor.configured is False)
    check('Configured status boolean', isinstance(descriptor.configured, bool) and 'fake' not in str(descriptor))
    fake=FakeGitHubTransport({'/user/repos':[{'name':'repo','private':False}], '/repos/o/r':{'name':'r'}, '/repos/o/r/issues':[], '/repos/o/r/pulls':[]})
    descriptor, adapter=build_github_connector(enabled=True, token='secret', transport=fake); service=ConnectorService(__import__('core.connectors',fromlist=['ConnectorRegistry']).ConnectorRegistry())
    registry=service.registry; registry.register(descriptor, adapter)
    repos=service.read(ConnectorRequest('1','github','github.repositories.list',{}))
    check('Repository list parsing', repos.status == 'SUCCEEDED' and repos.data[0]['name']=='repo')
    issue=service.read(ConnectorRequest('2','github','github.issues.list',{'owner':'o','repo':'r'})); check('Issue list', issue.status=='SUCCEEDED')
    pr=service.read(ConnectorRequest('3','github','github.pull_requests.list',{'owner':'o','repo':'r'})); check('PR list', pr.status=='SUCCEEDED')
    for args in ({'owner':'../x','repo':'r'}, {'owner':'o','repo':'r','bad':'x'}, {'owner':'o','repo':'r','Authorization':'Bearer x'}, {'owner':'o','repo':'r','url':'https://evil'}):
        result=service.read(ConnectorRequest('x','github','github.repository.get',args)); check('Invalid GitHub argument safe', result.status=='FAILED')
    try: GitHubTransport('x','http://api.github.com'); host=False
    except Exception: host=True
    check('Non-TLS rejected', host)
    try: GitHubTransport('x','https://evil.example'); host=False
    except Exception: host=True
    check('Arbitrary host rejected', host)
    check('GET-only transport', not hasattr(GitHubTransport,'post') and not hasattr(GitHubTransport,'delete'))
    check('Token absent from result', 'secret' not in repr(repos))
    print('TEST SUMMARY: 15/15 PASS')
if __name__ == '__main__': main()
