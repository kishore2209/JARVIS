import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core.runtime import create_runtime

def check(name,condition):
    if not condition: raise AssertionError(name)
    print(f'[PASS] {name}')

def main():
    runtime=create_runtime(); check('Project snapshot tool registered','project.snapshot' in [item['tool_id'] for item in runtime.tools.registry.safe_list()]); check('Tool is read-only',runtime.tools.registry.descriptor('project.snapshot').risk_class.value=='READ_ONLY'); runtime.close(); print('TEST SUMMARY: 2/2 PASS')
if __name__=='__main__': main()
