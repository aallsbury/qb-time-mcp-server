"""Readiness probe: initialize, ping and list tool schemas; never call a business tool."""

import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import requests


def gateway_probe_key(path):
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        key = line.strip()
        if key:
            if not key.isascii() or not key.isprintable():
                raise ValueError('Gateway key must contain printable ASCII characters')
            return key
    raise ValueError('Gateway key file is empty')


def probe(port, expected_tools=None, host='127.0.0.1', key_file=None):
    base = f'http://{host}:{port}'
    # A new SSE session starts a stdio child, including its bounded 5s/30s
    # token validation. Allow that startup without turning a slow API into churn.
    deadline = time.monotonic() + 45
    with requests.Session() as session:
        session.trust_env = False
        if key_file is not None:
            session.headers['Authorization'] = 'Bearer ' + gateway_probe_key(key_file)
        with session.get(base + '/sse', stream=True, timeout=(2, 40), allow_redirects=False) as stream:
            stream.raise_for_status()
            if stream.status_code != 200:
                raise ValueError('MCP endpoint did not open an SSE stream')
            lines = stream.iter_lines(chunk_size=1, decode_unicode=True)

            def event():
                kind, data = None, []
                for line in lines:
                    if time.monotonic() > deadline:
                        raise TimeoutError('MCP readiness deadline exceeded')
                    if not line and data:
                        return kind, '\n'.join(data)
                    if line.startswith('event:'):
                        kind = line[6:].strip()
                    elif line.startswith('data:'):
                        data.append(line[5:].lstrip())
                raise ConnectionError('MCP stream ended before readiness completed')

            kind, endpoint = event()
            if kind != 'endpoint':
                raise ValueError('MCP endpoint event missing')
            target = urljoin(base, endpoint)
            if (urlsplit(target).scheme, urlsplit(target).netloc) != (urlsplit(base).scheme, urlsplit(base).netloc):
                raise ValueError('MCP endpoint must remain on the probed host')

            def call(method, params=None):
                request_id = 'readiness-' + uuid4().hex
                body = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
                if params is not None:
                    body['params'] = params
                with session.post(target, json=body, timeout=(2, 3), allow_redirects=False) as reply:
                    reply.raise_for_status()
                while True:
                    _, payload = event()
                    result = json.loads(payload)
                    if result.get('id') == request_id:
                        if 'error' in result:
                            raise ValueError('MCP readiness RPC returned an error')
                        return result['result']

            call('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'qbtime-readiness', 'version': '1'}})
            with session.post(target, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'}, timeout=(2, 3), allow_redirects=False) as reply:
                reply.raise_for_status()
            call('ping')
            names = {tool['name'] for tool in call('tools/list')['tools']}
            if expected_tools is not None and names != set(expected_tools):
                raise ValueError('MCP tool contract differs from the deployed baseline')
            return {'ok': True, 'toolCount': len(names)}
