"""Fixed-endpoint MCP Streamable HTTP resource reader.

Supports negotiated 2025-06-18/2025-03-26, JSON and bounded SSE responses.
No tools/call, sampling, elicitation, server-directed HTTP, or subprocesses.
Resource aliases and the HTTPS endpoint are administrator configuration only.
"""
import json
import os
import re
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4
import httpx

from core.connectors import ConnectorValidationError


class MCPHTTPTransport:
    def __init__(self, endpoint, resources, token='', client_factory=None):
        url = urlsplit(endpoint)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ConnectorValidationError('MCP endpoint must be an explicit HTTPS URL without credentials/query')
        if not isinstance(resources, dict) or not 1 <= len(resources) <= 50:
            raise ConnectorValidationError('Configure 1..50 MCP resource aliases')
        if any(not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', k) or not isinstance(v, str) or not 1 <= len(v) <= 500 for k, v in resources.items()):
            raise ConnectorValidationError('Invalid MCP resource alias mapping')
        if token and (len(token) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise ConnectorValidationError('Invalid MCP token')
        self.endpoint, self.resources, self._token = endpoint, dict(resources), token
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=10, follow_redirects=False, trust_env=False))

    def read(self, capability_id, arguments):
        return self.read_with_context(capability_id, arguments, uuid4().hex)

    def read_with_context(self, capability_id, arguments, correlation_id):
        if capability_id not in {'mcp.resources.list', 'mcp.resource.read'}:
            raise ConnectorValidationError('MCP_CAPABILITY_DENIED')
        if capability_id == 'mcp.resource.read' and arguments.get('resource') not in self.resources:
            raise ConnectorValidationError('MCP_RESOURCE_DENIED')
        headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json',
                   'X-Correlation-ID': re.sub(r'[^A-Za-z0-9_.-]', '', correlation_id)[:128] or uuid4().hex}
        if self._token:
            headers['Authorization'] = 'Bearer ' + self._token
        deadline = monotonic() + 25
        with self._client_factory() as client:
            try:
                initialized = self._rpc(client, headers, 'initialize', {
                    'protocolVersion': '2025-06-18', 'capabilities': {},
                    'clientInfo': {'name': 'jarvis-resource-reader', 'version': '1'}}, deadline)
                version = initialized.get('protocolVersion')
                if version not in {'2025-06-18','2025-03-26'} or 'resources' not in initialized.get('capabilities', {}):
                    raise ConnectorValidationError('MCP_NEGOTIATION_FAILED')
                headers['MCP-Protocol-Version'] = version
                self._rpc(client, headers, 'notifications/initialized', {}, deadline, notification=True)
                if capability_id == 'mcp.resources.list':
                    result = self._rpc(client, headers, 'resources/list', {}, deadline)
                    allowed = set(self.resources.values())
                    # Never let discovery register new capabilities or resources.
                    advertised = {r.get('uri') for r in result.get('resources', []) if isinstance(r, dict) and r.get('uri') in allowed}
                    return {'resources': [alias for alias, uri in self.resources.items() if uri in advertised],
                            'protocol_version': version, 'partial': bool(result.get('nextCursor'))}
                alias = arguments['resource']; uri = self.resources[alias]
                result = self._rpc(client, headers, 'resources/read', {'uri': uri}, deadline)
                contents = result.get('contents')
                if not isinstance(contents, list) or not 1 <= len(contents) <= 20:
                    raise ConnectorValidationError('MCP_INVALID_RESOURCE')
                output = []
                for item in contents:
                    if not isinstance(item, dict) or item.get('uri') != uri or not isinstance(item.get('text'), str) or len(item['text']) > 8000:
                        raise ConnectorValidationError('MCP_INVALID_RESOURCE')
                    output.append({'text': item['text'], 'mime_type': item.get('mimeType', 'text/plain')})
                return {'resource': alias, 'contents': output, 'trust': 'UNTRUSTED_EXTERNAL_DATA', 'protocol_version': version}
            except httpx.TimeoutException as error:
                raise TimeoutError('MCP request timed out') from error
            except httpx.HTTPError as error:
                raise ConnectorValidationError('MCP_TRANSPORT_FAILED') from error
            finally:
                if 'Mcp-Session-Id' in headers:
                    try:
                        with client.stream('DELETE', self.endpoint, headers=headers, timeout=2):
                            pass
                    except httpx.HTTPError:
                        pass

    def _rpc(self, client, headers, method, params, deadline, notification=False):
        if monotonic() >= deadline:
            raise TimeoutError('MCP overall deadline exceeded')
        identifier = uuid4().hex
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notification:
            payload['id'] = identifier
        with client.stream('POST', self.endpoint, headers=headers, json=payload, timeout=min(10, max(0.1, deadline-monotonic()))) as response:
            if notification:
                if response.status_code != 202:
                    raise ConnectorValidationError('MCP_NOTIFICATION_FAILED')
                return {}
            if response.status_code != 200:
                raise ConnectorValidationError('MCP_HTTP_FAILED')
            if method == 'initialize' and response.headers.get('Mcp-Session-Id'):
                session = response.headers['Mcp-Session-Id']
                if not 1 <= len(session) <= 512 or any(ord(c) < 33 or ord(c) > 126 for c in session):
                    raise ConnectorValidationError('MCP_INVALID_SESSION')
                headers['Mcp-Session-Id'] = session
            media = response.headers.get('Content-Type', '').split(';')[0].strip()
            if media not in {'application/json', 'text/event-stream'}:
                raise ConnectorValidationError('MCP_CONTENT_TYPE_UNSUPPORTED')
            buffer = b''; size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 64000:
                    raise ConnectorValidationError('MCP_OUTPUT_TOO_LARGE')
                if monotonic() >= deadline:
                    raise TimeoutError('MCP overall deadline exceeded')
                buffer += chunk
                if media == 'text/event-stream':
                    buffer = buffer.replace(b'\r\n', b'\n')
                    while b'\n\n' in buffer:
                        event, buffer = buffer.split(b'\n\n', 1)
                        data = b'\n'.join(line[5:].lstrip(b' ') for line in event.split(b'\n') if line.startswith(b'data:'))
                        if data:
                            result = self._decode(data, identifier)
                            if result is not None:
                                return result
            if media == 'application/json':
                result = self._decode(buffer, identifier)
                if result is not None:
                    return result
            raise ConnectorValidationError('MCP_RESPONSE_MISSING')

    @staticmethod
    def _decode(data, identifier):
        try:
            message = json.loads(data)
        except (ValueError, UnicodeDecodeError) as error:
            raise ConnectorValidationError('MCP_INVALID_JSON') from error
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
            raise ConnectorValidationError('MCP_INVALID_MESSAGE')
        if 'method' in message:
            if 'id' in message:
                raise ConnectorValidationError('MCP_SERVER_REQUEST_UNSUPPORTED')
            return None  # Notifications are untrusted and do not alter policy.
        if message.get('id') != identifier or 'error' in message or not isinstance(message.get('result'), dict):
            raise ConnectorValidationError('MCP_RPC_FAILED')
        return message['result']


def configured_mcp_transport():
    if os.getenv('JARVIS_MCP_HTTP_ENABLED', 'false').lower() != 'true':
        return None
    try:
        resources = json.loads(os.getenv('JARVIS_MCP_RESOURCES', '{}'))
    except ValueError as error:
        raise ConnectorValidationError('Invalid MCP resource configuration') from error
    return MCPHTTPTransport(os.getenv('JARVIS_MCP_ENDPOINT', ''), resources, os.getenv('JARVIS_MCP_TOKEN', ''))
