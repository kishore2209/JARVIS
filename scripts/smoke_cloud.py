"""Exercise the real cloud supervisor with temporary data and mock providers."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent

def main():
    with tempfile.TemporaryDirectory() as directory:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        token = secrets.token_urlsafe(32)
        env = {**os.environ, 'RENDER_EXTERNAL_HOSTNAME': 'jarvis-smoke.onrender.com',
               'JARVIS_PUBLIC_URL': 'https://jarvis-smoke.onrender.com',
               'JARVIS_API_TOKEN': token, 'PORT': str(port),
               'JARVIS_DB_PATH': str(Path(directory)/'cloud.db'),
               'JARVIS_DB_ENABLED': 'true', 'JARVIS_LLM_ENABLED': 'false',
               'JARVIS_MARKET_PROVIDER': 'MOCK', 'JARVIS_ENV': 'paper'}
        def request(path, data=None, authenticated=True):
            headers = {'Host': 'jarvis-smoke.onrender.com'}
            if authenticated: headers['Authorization'] = 'Bearer ' + token
            if data is not None: headers['Content-Type'] = 'application/json'
            req = Request(f'http://127.0.0.1:{port}'+path,
                          data=None if data is None else json.dumps(data).encode(), headers=headers)
            with urlopen(req, timeout=5) as response:
                body = response.read()
                return json.loads(body) if 'application/json' in response.headers.get('Content-Type','') else body
        for iteration in range(2):
            with open(Path(directory)/f'run-{iteration}.log', 'w+') as log:
                process = subprocess.Popen([sys.executable, '-m', 'jarvis_cloud'], cwd=ROOT, env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic()+30
                    while True:
                        if process.poll() is not None:
                            log.flush(); log.seek(0)
                            raise AssertionError('Supervisor exited before readiness: ' + log.read().replace(token, '[REDACTED]'))
                        try:
                            request('/health', authenticated=False)
                            break
                        except OSError:
                            if time.monotonic()>deadline: raise AssertionError('Startup timeout')
                            time.sleep(.2)
                    assert b'<html' in request('/', authenticated=False).lower()
                    try:
                        request('/api/v1/status', authenticated=False)
                        raise AssertionError('API accepted anonymous access')
                    except HTTPError as error:
                        assert error.code == 401
                    request('/api/v1/status')
                    if iteration == 0:
                        request('/api/v1/knowledge', {'title':'Cloud smoke', 'source':'local:cloud-smoke', 'text':'Persistence sentinel survives restart.'})
                        task=request('/api/v1/tasks', {'kind':'DAILY_PLAN','payload':{},'idempotency_key':'cloud-smoke','tool_budget':1})['task']
                        deadline=time.monotonic()+20
                        while request('/api/v1/tasks/'+task['id'])['task']['state'] != 'COMPLETED':
                            if time.monotonic()>deadline: raise AssertionError('Worker task timeout')
                            time.sleep(.3)
                    result=request('/api/v1/knowledge/search', {'query':'Persistence sentinel'})['result']
                    assert not result['empty'], 'Knowledge missing after restart'
                finally:
                    process.terminate()
                    try: process.wait(timeout=25)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(); raise
                assert process.returncode == 0, 'Supervisor did not shut down cleanly'
    print('PASS: dashboard, owner authentication, real worker task, restart persistence, graceful shutdown')

if __name__ == '__main__': main()
