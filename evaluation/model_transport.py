"""Responses transport; credentials stay in memory, never in run artifacts."""
import json
import os
from pathlib import Path
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request

def settings():
    if all(os.environ.get(k) for k in ('CA_MODEL', 'CA_BASE_URL', 'CA_API_KEY')):
        endpoint = os.environ['CA_BASE_URL'].rstrip('/') + '/responses'
        if not endpoint.startswith('https://'):
            raise ValueError('Configured endpoint must use HTTPS')
        return {'model': os.environ['CA_MODEL'], 'model_reasoning_effort': 'high'}, endpoint, os.environ['CA_API_KEY']
    config = tomllib.loads((Path.home() / '.codex' / 'config.toml').read_text(encoding='utf-8'))
    provider = config.get('model_providers', {}).get(config.get('model_provider'), {})
    endpoint = provider.get('base_url', 'https://api.openai.com/v1').rstrip('/') + '/responses'
    if not endpoint.startswith('https://'):
        raise ValueError('Configured endpoint must use HTTPS')
    credential = os.environ.get(provider.get('env_key') or 'OPENAI_API_KEY')
    if provider.get('requires_openai_auth') and not provider.get('env_key'):
        auth_path = Path.home() / '.codex' / 'auth.json'
        current_auth = json.loads(auth_path.read_text(encoding='utf-8')) if auth_path.exists() else {}
        credential = current_auth.get('OPENAI_API_KEY') or credential
    if not credential:
        raise ValueError('No API credential found in configured environment; no credentials read from backups')
    return config, endpoint, credential

def request_once(payload, timeout):
    _, endpoint, credential = settings()
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
                                     headers={'Authorization': 'Bearer ' + credential,
                                              'Content-Type': 'application/json'}, method='POST')
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
            status = response.status
        return {'http_status': status, 'elapsed_seconds': time.perf_counter() - started,
                'raw': raw, 'error': None}
    except urllib.error.HTTPError as error:
        # Avoid printing or saving echoed keys in arbitrary upstream error bodies.
        return {'http_status': error.code, 'elapsed_seconds': time.perf_counter() - started,
                'raw': None, 'error': 'HTTP ' + str(error.code)}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        safe = str(error).replace(credential, '[redacted]')
        return {'http_status': None, 'elapsed_seconds': time.perf_counter() - started,
                'raw': None, 'error': safe}

def parse_response(raw):
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        response = None
        for frame in raw.split('\n\n'):
            for line in frame.splitlines():
                if line.startswith('data: '):
                    try:
                        event = json.loads(line[6:])
                    except ValueError:
                        continue
                    if event.get('type') in ('response.completed', 'response.incomplete'):
                        response = event['response']
        if response is None:
            raise ValueError('Neither a JSON response nor a completed SSE response')
    if not isinstance(response, dict):
        raise ValueError('Provider response must be a JSON object')
    parts = [part.get('text', '') for item in response.get('output', [])
             if item.get('type') == 'message' for part in item.get('content', [])
             if part.get('type') == 'output_text']
    return response, '\n'.join(parts)
