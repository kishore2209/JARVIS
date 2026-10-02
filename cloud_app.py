"""Single-origin cloud entrypoint. All routes except health require owner login."""
import base64
import binascii
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

password = os.environ.get('JARVIS_WEB_PASSWORD', '')
if len(password) < 24:
    raise RuntimeError('Set JARVIS_WEB_PASSWORD to a strong value of at least 24 characters.')
username = os.environ.get('JARVIS_WEB_USER', 'jarvis')
# Bridge authenticated browser requests to the internal bearer boundary.
# The internal credential is never returned to the browser.
os.environ.setdefault('JARVIS_API_TOKEN', secrets.token_urlsafe(48))
hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
if hostname:
    import re
    if not re.fullmatch(r'[A-Za-z0-9.-]+', hostname):
        raise RuntimeError('Invalid platform hostname')
    os.environ.setdefault('JARVIS_ALLOWED_HOSTS', hostname + ',127.0.0.1,localhost')
    os.environ.setdefault('JARVIS_CORS_ORIGINS', 'https://' + hostname)
from api import app

@app.middleware('http')
async def owner_access(request, call_next):
    if request.url.path == '/health' and request.method in ('GET', 'HEAD'):
        return await call_next(request)
    authenticated = False
    try:
        scheme, token = request.headers.get('authorization', '').split(' ', 1)
        user, supplied = base64.b64decode(token, validate=True).decode('utf-8').split(':', 1)
        authenticated = (scheme.lower() == 'basic' and
                         secrets.compare_digest(user.encode(), username.encode()) and
                         secrets.compare_digest(supplied.encode(), password.encode()))
    except (ValueError, UnicodeError, binascii.Error):
        pass
    if not authenticated:
        return JSONResponse({'message': 'Owner login required'}, status_code=401,
                            headers={'WWW-Authenticate': 'Basic realm="JARVIS", charset="UTF-8"', 'Cache-Control': 'no-store'})
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and urlsplit(origin).netloc != request.headers.get('host')):
            return JSONResponse({'message': 'Cross-origin write blocked'}, status_code=403)
    request.scope['headers'] = [(key, value) for key, value in request.scope['headers']
                                if key.lower() != b'authorization'] + [
        (b'authorization', ('Bearer ' + os.environ['JARVIS_API_TOKEN']).encode())]
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response

app.mount('/', StaticFiles(directory=os.environ.get('JARVIS_FRONTEND_DIR', str(Path(__file__).parent / 'frontend' / 'dist')), html=True), name='frontend')
