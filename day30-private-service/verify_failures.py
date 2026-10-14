"""Real isolated HTTP error-path probes; synthetic upstream, never quality evidence."""
import http.server
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import threading
import tempfile
import time
from common import ServiceError, http_json

ROOT = Path(__file__).parent


class FaultUpstream(http.server.BaseHTTPRequestHandler):
    mode = 'timeout'
    hold_started = threading.Event()
    hold_release = threading.Event()

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/health':
            self.reply({'status': 'ok', 'fingerprint': 'df2af910c83efd01d39f7ba4012e24bdc1ba98281ad65efff841fd025148279d'})
            return
        self.reply({'default_generation_settings': {'n_ctx': 32768}, 'total_slots': 1,
                    'model_alias': 'fault-injection-only'})

    def do_POST(self):
        self.rfile.read(int(self.headers.get('content-length', 0)))
        if self.path == '/apply-template':
            self.reply({'prompt': 'test prompt'})
        elif self.path == '/tokenize':
            self.reply({'tokens': [1, 2, 3]})
        else:
            mode = self.mode
            if mode == 'timeout':
                time.sleep(2.5)
                self.reply({'choices': []})
            elif mode == 'hold':
                self.hold_started.set()
                self.hold_release.wait(timeout=5)
                self.valid_reply()
            elif mode == 'valid':
                self.valid_reply()
            else:
                self.reply({'choices': []})

    def valid_reply(self):
        self.reply({'choices': [{'message': {'content': 'Synthetic controller recovery response.'},
                                'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                    'timings': {}})

    def reply(self, value):
        body = json.dumps(value).encode()
        try:
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def run_probe(workspace):
    stub = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FaultUpstream)
    thread = threading.Thread(target=stub.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        api_port = reservation.getsockname()[1]
    upstream = 'http://127.0.0.1:' + str(stub.server_port)
    endpoint = 'http://127.0.0.1:' + str(api_port)
    # Copy only API/public configs; private .env and production request journal are
    # never loaded by this isolated process. Shared Agent modules use fake URLs.
    shutil.copyfile(ROOT / 'api.py', workspace / 'api.py')
    (workspace / 'configs').mkdir()
    (workspace / 'runtime').mkdir()
    for profile in ['baseline', 'optimized']:
        shutil.copyfile(ROOT / 'configs' / (profile + '.json'), workspace / 'configs' / (profile + '.json'))
    env = os.environ.copy()
    env.update(MODEL_URL=upstream, EMBED_URL=upstream, MODEL_TIMEOUT='2',
               API_TOKEN='failure-probe-only', API_TEST_TOKENS='', RATE_LIMIT='100',
               API_SLOTS='1', API_QUEUE='3', API_QUEUE_WAIT_TIMEOUT='.08',
               PYTHONPATH=str(ROOT.resolve()))
    log = (workspace / 'api.log').open('w')
    api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'api:app', '--host', '127.0.0.1',
                            '--port', str(api_port), '--no-access-log'],
                           cwd=workspace, env=env, stdout=log, stderr=log)
    def call(path, body=None):
        return http_json(endpoint + path, body, token='failure-probe-only', timeout=8)
    try:
        for _ in range(50):
            try:
                if api.poll() is not None:
                    raise RuntimeError('Isolated API failed to start')
                with socket.create_connection(('127.0.0.1', api_port), timeout=.1):
                    break
            except OSError:
                time.sleep(.1)
        records = []
        for mode, expected in [('timeout', 504), ('malformed', 502)]:
            FaultUpstream.mode = mode
            try:
                call('/chat', {'message': 'test'})
                raise AssertionError('Expected upstream error')
            except ServiceError as exc:
                assert exc.status == expected, (mode, exc.status)
                records.append({'mode': mode, 'status': exc.status, 'body': exc.detail, 'synthetic_upstream': True})
        # Malformed session IDs must be 422 rather than process exceptions / 500.
        for path, body in [('/sessions/reset', {'session_id': []}), ('/chat', {'message': 'test', 'session_id': {}})]:
            try:
                call(path, body)
                raise AssertionError('Expected validation error')
            except ServiceError as exc:
                assert exc.status == 422
                records.append({'path': path, 'status': exc.status, 'body': exc.detail})
        result = call('/health')
        assert result['pending'] == 0
        records.append({'pending_after_errors': result['pending']})
        # Hold the single active slot. A second session acquires its session lock,
        # times out waiting for admission, then must release that lock and pending.
        held_sid = call('/sessions', {})['session_id']
        queued_sid = call('/sessions', {})['session_id']
        FaultUpstream.hold_started.clear()
        FaultUpstream.hold_release.clear()
        FaultUpstream.mode = 'hold'
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            active = pool.submit(call, '/chat', {'session_id': held_sid, 'message': 'Synthetic hold'})
            assert FaultUpstream.hold_started.wait(timeout=3), 'Synthetic upstream was not entered'
            queue_errors = []
            for attempt in range(2):
                started = time.monotonic()
                try:
                    call('/chat', {'session_id': queued_sid, 'message': 'Synthetic queued request'})
                    raise AssertionError('Expected queue wait timeout')
                except ServiceError as exc:
                    assert exc.status == 503 and exc.detail['error'] == 'queue_wait_timeout', exc.detail
                    queue_errors.append({'status': exc.status, 'body': exc.detail,
                                         'elapsed_ms': (time.monotonic() - started) * 1000})
                # Must be200 even while another session holds the model slot.
                assert call('/sessions/reset', {'session_id': queued_sid}) == {'reset': True}
            pending_held = call('/health')['pending']
            assert pending_held == 1, pending_held
            FaultUpstream.hold_release.set()
            active_result = active.result(timeout=5)
        FaultUpstream.mode = 'valid'
        recovered = call('/chat', {'session_id': queued_sid, 'message': 'Synthetic recovery'})
        final_pending = call('/health')['pending']
        assert final_pending == 0
        records.append({'mode': 'queue_wait_timeout', 'synthetic_upstream': True,
                        'api_slots': 1, 'queue_wait_timeout_s': .08,
                        'queue_errors': queue_errors, 'session_reset_after_timeout_status': 200,
                        'pending_while_slot_held': pending_held, 'semaphore_not_overreleased': len(queue_errors) == 2,
                        'held_request_recovered': active_result['text'],
                        'timed_out_session_reused': recovered['text'], 'pending_after_recovery': final_pending,
                        'private_env_loaded': False, 'production_journal_modified': False})
        (ROOT / 'results/failure_injection.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print('Synthetic isolated HTTP: 504/502/422 and503 queue timeout; pending/session lock recovery verified')
    finally:
        api.terminate()
        api.wait(timeout=10)
        log.close()
        stub.shutdown()
        stub.server_close()


def main():
    with tempfile.TemporaryDirectory(prefix='local-llm-fault-api-') as directory:
        run_probe(Path(directory))


if __name__ == '__main__':
    main()
