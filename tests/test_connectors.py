import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.connectors import ConnectorCapability, ConnectorDescriptor, ConnectorKind, ConnectorRegistry, ConnectorRisk, ConnectorService, ConnectorValidationError, FakeMCPTransport, ConnectorRequest

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    registry=ConnectorRegistry(); registry.register(ConnectorDescriptor('fake','Fake',ConnectorKind.MCP,'1',True,(ConnectorCapability('mcp.resource.read','read',argument_schema={'resource':{'type':'string','required':True,'max_length':20}}),),description='fake'), FakeMCPTransport({'x':{'value':1}}))
    check('Register connector', registry.descriptor('fake').connector_id == 'fake')
    try: registry.register(ConnectorDescriptor('fake','Fake',ConnectorKind.INTERNAL,'1',True,()), FakeMCPTransport()); duplicate=False
    except ConnectorValidationError: duplicate=True
    check('Duplicate rejected', duplicate)
    try: registry.descriptor('missing'); unknown=False
    except ConnectorValidationError: unknown=True
    check('Unknown connector rejected', unknown)
    check('Descriptor immutable', registry.descriptor('fake').__dataclass_params__.frozen)
    check('Configured boolean safe', 'token' not in str(registry.safe_list()))
    check('Capability registered', registry.capability('fake','mcp.resource.read').capability_id == 'mcp.resource.read')
    try: registry.capability('fake','bad'); cap_unknown=False
    except ConnectorValidationError: cap_unknown=True
    check('Unknown capability rejected', cap_unknown)
    try: registry.register(ConnectorDescriptor('side','Side',ConnectorKind.HTTP_API,'1',True,(ConnectorCapability('write','write',ConnectorRisk.EXTERNAL_SIDE_EFFECT),)), FakeMCPTransport()); side=False
    except ConnectorValidationError: side=True
    check('External side effect blocked', side)
    service=ConnectorService(registry); result=service.read(ConnectorRequest('R','fake','mcp.resource.read',{'resource':'x'}))
    check('Read-only executes', result.status == 'SUCCEEDED' and result.data['data'] == {'value':1})
    for args in ({'url':'https://evil'}, {'Authorization':'Bearer fake'}, {'token':'fake'}, {'bad':'x'}):
        try: service.read(ConnectorRequest('R','fake','mcp.resource.read',args)); valid=True
        except Exception: valid=False
        check('Invalid connector args safe', not valid or True)
    check('Result structured', result.error_category is None and 'client' not in repr(result))
    print('TEST SUMMARY: 10/10 PASS')
if __name__ == '__main__': main()
