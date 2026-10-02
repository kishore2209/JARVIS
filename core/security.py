"""Single-owner API boundary. Connector tokens are never browser credentials."""
from hmac import compare_digest
from ipaddress import ip_address
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware


def install_api_security(app, config):
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.allowed_hosts))

    @app.middleware('http')
    async def boundary(request, call_next):
        supplied_id = request.headers.get('X-Correlation-ID', '')
        correlation = supplied_id if 0 < len(supplied_id) <= 128 and all(c.isalnum() or c in '-_.' for c in supplied_id) else uuid4().hex
        request.state.correlation_id = correlation

        def reject(code, status):
            return JSONResponse({'status': 'ERROR', 'code': code, 'correlation_id': correlation}, status_code=status, headers={'X-Correlation-ID': correlation})

        public_ui = getattr(config, 'serve_ui', False) and request.method in {'GET', 'HEAD'} and (request.url.path == '/' or request.url.path.startswith('/assets/'))
        if request.url.path != '/health' and not public_ui and request.method != 'OPTIONS':
            if config.api_token:
                supplied = request.headers.get('Authorization', '')
                if not compare_digest(supplied.encode(), ('Bearer ' + config.api_token).encode()):
                    return reject('AUTHENTICATION_REQUIRED', 401)
            else:
                host = request.client.host if request.client else ''
                try:
                    local = ip_address(host).is_loopback
                except ValueError:
                    local = host == 'testclient'  # ASGI in-process tests only; never an IP peer.
                if not local:
                    return reject('LOCAL_ACCESS_ONLY', 403)
            origin = request.headers.get('Origin')
            if origin and origin not in config.cors_origins:
                return reject('ORIGIN_DENIED', 403)
            size = request.headers.get('Content-Length', '0')
            if not size.isdigit() or int(size) > 2_000_000:
                return reject('REQUEST_TOO_LARGE', 413)
            # Bound chunked bodies too; Starlette caches this for downstream parsing.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 2_000_000:
                    return reject('REQUEST_TOO_LARGE', 413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = correlation
        response.headers['Cache-Control'] = 'no-store'
        return response
