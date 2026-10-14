"""Pinned, resumable range download; final SHA-256 is authoritative."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import socket

NAME = 'Tiel-Coder-35B-A3B-MTP-UD-Q4_K_XL.gguf'
SIZE = 23259486752
SHA = '10960d1d6477b08ed36a0e542e571b473022023c25b8315b0cf8c33c57e98ccd'
URL = 'https://huggingface.co/peculiar-ragdoll/Tiel-Coder-35B-A3B-GGUF-MTP/resolve/3afc5222473fc08c6130b2771ebd819fa0c4b484/' + NAME


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    if os.getenv('DOWNLOAD_SOCKS_PORT'):
        import socks
        socks.set_default_proxy(socks.SOCKS5, '127.0.0.1', int(os.environ['DOWNLOAD_SOCKS_PORT']), rdns=True)
        socket.socket = socks.socksocket
    directory = Path(os.getenv('MODEL_DIR', '/home/kotdath/omp/personal/amd-strix-halo-toolboxes/models/tiel-coder'))
    directory.mkdir(parents=True, exist_ok=True)
    target, partial, checkpoint = directory / NAME, directory / (NAME + '.part'), directory / (NAME + '.download.json')
    if target.exists():
        assert digest(target) == SHA, 'existing_model_checksum_mismatch'
        print('Q4 checksum verified')
        return
    if os.getenv('DOWNLOAD_BACKEND') == 'xet':
        # Mirror metadata declares the exact same immutable LFS SHA/bytes.
        # hf_xet transfers artifacts only; it is not an AI-agent SDK.
        os.environ.pop('HF_DEBUG', None)
        os.environ.setdefault('HF_XET_HIGH_PERFORMANCE', '1')
        os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        from huggingface_hub import hf_hub_download
        downloaded = Path(hf_hub_download(
            repo_id='dotnfc/Tiel-Coder-35B-A3B-GGUF-MTP',
            revision='3fb96f5d7b9fd73d93a62ddfd181055acd0bc870',
            filename=NAME, local_dir=directory,
        ))
        assert downloaded.stat().st_size == SIZE and digest(downloaded) == SHA
        print('Q4 Xet mirror complete; identical pinned SHA-256 verified', flush=True)
        return
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        assert state['sha256'] == SHA and partial.exists(), 'invalid_checkpoint'
    else:
        prefix = partial.stat().st_size if partial.exists() else 0
        assert prefix <= SIZE
        state = {'sha256': SHA, 'size': SIZE, 'prefix': prefix, 'segments': []}
        for start in range(prefix, SIZE, 512 << 20):
            state['segments'].append({'start': start, 'end': min(start + (512 << 20), SIZE), 'written': 0})
    if os.getenv('DOWNLOAD_SMALL_RANGES'):
        segments = []
        for segment in state['segments']:
            completed = segment['start'] + segment['written']
            if segment['written']:
                segments.append({'start': segment['start'], 'end': completed, 'written': segment['written']})
            for start in range(completed, segment['end'], 8 << 20):
                segments.append({'start': start, 'end': min(start + (8 << 20), segment['end']), 'written': 0})
        state['segments'] = segments
    download_url = URL
    if os.getenv('DOWNLOAD_SIGNED_URL'):
        from huggingface_hub import get_hf_file_metadata, hf_hub_url
        # Resolve a fresh URL on every resume; intermediary caches may otherwise
        # return the same expired signed CDN URL after an HTTP 403.
        resolver_url = hf_hub_url(
            'peculiar-ragdoll/Tiel-Coder-35B-A3B-GGUF-MTP', NAME,
            revision='3afc5222473fc08c6130b2771ebd819fa0c4b484')
        resolver_url += '?download=true&cache_bust=' + str(time.time_ns())
        metadata = get_hf_file_metadata(resolver_url, token=os.getenv('HF_TOKEN'))
        assert metadata.size == SIZE and metadata.etag == SHA
        download_url = metadata.location  # temporary signed URL kept in memory only
    fd = os.open(partial, os.O_RDWR | os.O_CREAT, 0o600)
    os.ftruncate(fd, SIZE)
    lock = threading.Lock()

    def save():
        temporary = checkpoint.with_suffix('.tmp')
        temporary.write_text(json.dumps(state))
        temporary.replace(checkpoint)

    with lock:
        save()

    def fetch(segment):
        for attempt in range(5):
            start = segment['start'] + segment['written']
            if start == segment['end']:
                return
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                request = urllib.request.Request(download_url, headers={'Range': f"bytes={start}-{segment['end']-1}"})
                with opener.open(request, timeout=60) as response:
                    assert response.status == 206
                    assert response.headers['Content-Range'] == f"bytes {start}-{segment['end']-1}/{SIZE}"
                    saved_at = segment['written']
                    while segment['start'] + segment['written'] < segment['end']:
                        block = response.read(min(1 << 20, segment['end'] - segment['start'] - segment['written']))
                        if not block:
                            raise OSError('incomplete_range')
                        offset = segment['start'] + segment['written']
                        wrote = os.pwrite(fd, block, offset)
                        assert wrote == len(block)
                        segment['written'] += wrote
                        if segment['written'] - saved_at >= 32 << 20:
                            with lock:
                                save()
                            saved_at = segment['written']
                with lock:
                    save()
                    total = state['prefix'] + sum(s['written'] for s in state['segments'])
                    print(f'Q4 downloaded {total}/{SIZE} bytes', flush=True)
                return
            except Exception as exc:
                with lock:
                    save()
                if os.getenv('DOWNLOAD_LOG_RETRIES'):
                    print('range retry', attempt + 1, type(exc).__name__, getattr(exc, 'code', None), flush=True)
                if attempt == 4:
                    raise
                time.sleep(min(2 ** attempt, 16))
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.getenv('DOWNLOAD_WORKERS', '6'))) as pool:
            list(pool.map(fetch, state['segments']))
        os.fsync(fd)
    finally:
        os.close(fd)
    assert digest(partial) == SHA, 'download_checksum_mismatch'
    partial.replace(target)
    checkpoint.unlink()
    print('Q4 complete, pinned SHA-256 verified', flush=True)


if __name__ == '__main__':
    main()
