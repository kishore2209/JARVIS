"""Run every backend test script; preserve failures and machine-readable evidence."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='validation/backend.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    reports=[]
    for path in sorted((root/'tests').glob('test_*.py')):
        started=time.monotonic()
        try:
            result=subprocess.run([sys.executable,str(path)],cwd=root,capture_output=True,text=True,timeout=120,env={**os.environ,'PYTHONOPTIMIZE':'0'})
            code,output=result.returncode,result.stdout+result.stderr
        except subprocess.TimeoutExpired:
            code,output=124,'Test script exceeded 120 seconds'
        reports.append({'file':str(path.relative_to(root)),'exit_code':code,'seconds':round(time.monotonic()-started,3),'output':output})
        print(('PASS' if code==0 else 'FAIL')+' '+str(path.relative_to(root)),flush=True)
    destination=Path(args.output)
    if not destination.is_absolute():destination=root/destination
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps({'total':len(reports),'passed':sum(r['exit_code']==0 for r in reports),'scripts':reports},indent=2)+'\n')
    return int(any(r['exit_code'] for r in reports))

if __name__=='__main__':sys.exit(main())
