"""Single-instance cloud launcher for the authenticated dashboard and worker.

The two processes share one persistent SQLite disk. If either exits, stop the
other and fail the container so the hosting platform can restart it.
"""
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from threading import Event
from urllib.parse import urlsplit


def configure_environment(environ=None):
    env = os.environ if environ is None else environ
    hostname = env.get('RENDER_EXTERNAL_HOSTNAME', '')
    public_url = env.get('JARVIS_PUBLIC_URL') or ('https://' + hostname if hostname else '')
    parsed = urlsplit(public_url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {'', '/'}
            or parsed.port not in {None, 443}
            or not re.fullmatch(r'[A-Za-z0-9.-]+', parsed.hostname)):
        raise ValueError('Set JARVIS_PUBLIC_URL to the HTTPS site origin or supply RENDER_EXTERNAL_HOSTNAME')
    if len(env.get('JARVIS_API_TOKEN', '')) < 32:
        raise ValueError('Cloud hosting requires an owner token of at least 32 characters')
    if env.get('JARVIS_DB_ENABLED', 'true').lower() != 'true':
        raise ValueError('Cloud hosting requires persistent database storage')
    path = Path(env.get('JARVIS_DB_PATH', '/var/data/jarvis.db'))
    if not path.is_absolute() or path.name in {'', '.', '..'}:
        raise ValueError('Cloud database path must be absolute and on the mounted persistent disk')
    # Identity is derived from trusted deployment configuration, never Host or
    # X-Forwarded-Host input from a request.
    origin = f'https://{parsed.hostname}'
    hosts = {parsed.hostname, '127.0.0.1', 'localhost'}
    origins = {origin}
    if hostname:
        if not re.fullmatch(r'[A-Za-z0-9.-]+', hostname):
            raise ValueError('Invalid platform hostname')
        hosts.add(hostname); origins.add('https://' + hostname)
    env.update(JARVIS_HOST='0.0.0.0', JARVIS_PORT=env.get('PORT', env.get('JARVIS_PORT', '10000')),
               JARVIS_DB_ENABLED='true', JARVIS_DB_PATH=str(path), JARVIS_SERVE_UI='true',
               JARVIS_ALLOWED_HOSTS=','.join(sorted(hosts)), JARVIS_CORS_ORIGINS=','.join(sorted(origins)))
    env.setdefault('JARVIS_ENV', 'paper')
    env.setdefault('JARVIS_LLM_ENABLED', 'false')
    env.setdefault('JARVIS_MARKET_PROVIDER', 'MOCK')
    return origin


def supervise(stop, commands=None, popen=None):
    commands = commands or [[sys.executable, '-m', 'jarvis_server'], [sys.executable, '-m', 'jarvis_worker']]
    popen = popen or subprocess.Popen
    processes = []
    try:
        for command in commands:
            processes.append(popen(command))
        while not stop.wait(0.25):
            if any(process.poll() is not None for process in processes):
                return 1
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=2)


def main():
    configure_environment()
    from core.runtime import RuntimeConfig, create_runtime
    config = RuntimeConfig.from_environment()
    if not (Path(__file__).resolve().parent/'frontend'/'dist'/'index.html').is_file():
        raise ValueError('The cloud image must include the built dashboard')
    # Initialize/validate tables before concurrent processes start. This also
    # fails immediately on an unwritable disk or unreconciled legacy state.
    runtime = create_runtime(config)
    runtime.close()
    stop = Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    return supervise(stop)


if __name__ == '__main__':
    sys.exit(main())
