import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def main():
 commands=("status","market-context","underlying-analysis","full-analysis","portfolio","automation-status","automation-history","automation-tick","risk-validate","paper-execute","backtest","live")
 passed=0
 for command in commands:
  result=subprocess.run([sys.executable,"-m","jarvis_cli",command],cwd=ROOT,capture_output=True,text=True)
  if result.returncode:raise AssertionError(f"{command}: {result.stderr}")
  if command=="live" and "LIVE_EXECUTION_UNSUPPORTED" not in result.stdout:raise AssertionError("live rejection missing")
  passed+=1
 print(f"[PASS] CLI Commands: {passed}/{len(commands)}")
if __name__=="__main__":main()