"""Optional arXiv pinned-PDF integrity and latest-version check; no web fallback."""
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from common import utc_now

ROOT = Path(__file__).parent
MAX_PDF_BYTES = 32 * 1024 * 1024


def check_sources(sources):
    allowed = {entry['source']: entry for entry in json.loads((ROOT/'data/corpus/manifest.json').read_text())}
    checks = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for source in dict.fromkeys(s['source'] for s in sources):
        if source not in allowed:
            continue
        entry = allowed[source]
        identifier = entry['revision']
        if not re.fullmatch(r'\d{4}\.\d{4,5}v\d+', identifier):
            continue
        url = 'https://arxiv.org/pdf/' + identifier
        record = {'utc': utc_now(), 'source': source, 'url': url,
                  'frozen_version': identifier, 'frozen_pdf_sha256': entry['pdf_sha256']}
        try:
            with opener.open(url, timeout=60) as response:
                final = response.geturl()
                if not final.startswith('https://arxiv.org/pdf/'):
                    raise ValueError('unexpected_pdf_redirect')
                data = response.read(MAX_PDF_BYTES + 1)
            if len(data) > MAX_PDF_BYTES or not data.startswith(b'%PDF-'):
                raise ValueError('invalid_pdf')
            digest = hashlib.sha256(data).hexdigest()
            record.update(status='checked', downloaded_bytes=len(data), current_pinned_pdf_sha256=digest,
                          pinned_pdf_changed=digest != entry['pdf_sha256'])
        except Exception as exc:
            record.update(status='unavailable', error=type(exc).__name__)
        base, version = identifier.rsplit('v', 1)
        try:
            with opener.open('https://arxiv.org/abs/' + base, timeout=30) as response:
                html = response.read(1_000_000).decode('utf-8')
            versions = [int(v) for v in re.findall(r'\[v(\d+)\]', html)]
            if not versions:
                raise ValueError('version_history_unavailable')
            latest = max(versions)
            record.update(latest_version=base+'v'+str(latest), newer_version_available=latest>int(version))
        except Exception as exc:
            record.update(version_check='unavailable', version_error=type(exc).__name__)
        record['scope'] = 'PDF bytes and published revision only; not a proof of scientific truth. A rebuilt PDF can differ without a text revision.'
        checks.append(record)
    return checks


if __name__ == '__main__':
    entries = json.loads((ROOT/'data/corpus/manifest.json').read_text())
    print(json.dumps(check_sources([{'source': e['source']} for e in entries]), ensure_ascii=False, indent=2))
