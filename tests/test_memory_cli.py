import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    result = subprocess.run([sys.executable, "jarvis_cli.py", "memory-list"], cwd=ROOT, capture_output=True, text=True)
    check("Memory list CLI", result.returncode == 0 and "memories" in result.stdout)
    check("CLI secret-safe", "api_key" not in result.stdout.lower())
    print("TEST SUMMARY: 2/2 PASS")

if __name__ == "__main__": main()
