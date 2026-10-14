"""Transport, configuration and evidence helpers. No agent framework."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


class ServiceError(Exception):
    def __init__(self, code, status=502, detail=None):
        super().__init__(code)
        self.code, self.status, self.detail = code, status, detail


def load_env(path=None):
    path = Path(path or os.getenv('ENV_FILE', '.env'))
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def http_json(url, data=None, token=None, timeout=1800):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(
        url, data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
        headers=headers,
    )
    # Deliberately ignore ambient HTTP proxies for local/private traffic.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except (ValueError, OSError):
            body = None
        raise ServiceError('upstream_http_error', exc.code, body) from None
    except (TimeoutError, __import__('socket').timeout):
        raise ServiceError('upstream_timeout', 504) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise ServiceError('upstream_timeout', 504) from None
        raise ServiceError('upstream_unavailable', 503) from None
    except (ValueError, OSError):
        raise ServiceError('invalid_upstream_response', 502) from None


def append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')


def utc_now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
