"""VPS loopback-only HTTP relay. Python stdlib; no model/index/inference code."""
import http.server
import json
import os
import socket
import time
import urllib.error
import urllib.request

UPSTREAM = 'http://127.0.0.1:18780'
TIMEOUT = float(os.getenv('GATEWAY_TIMEOUT', '1800'))
ROUTES = {'/health', '/chat', '/sessions', '/sessions/reset'}


class Gateway(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.relay()

    def do_POST(self):
        self.relay()

    def fail(self, status, code):
        payload = json.dumps({'error': code}).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def relay(self):
        if self.path not in ROUTES:
            self.fail(404, 'unknown_route')
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.fail(400, 'invalid_length')
            return
        if size < 0 or size > 524288:
            self.fail(413, 'body_limit')
            return
        if self.headers.get('Transfer-Encoding'):
            self.fail(400, 'chunked_transfer_not_supported')
            return
        headers = {key: self.headers[key] for key in ('Authorization', 'Content-Type') if key in self.headers}
        request = urllib.request.Request(UPSTREAM + self.path, self.rfile.read(size) if self.command == 'POST' else None,
                                         headers=headers, method=self.command)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            try:
                response = opener.open(request, timeout=TIMEOUT)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                payload = response.read(8_000_000)
                self.send_response(response.code)
                self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                self.send_header('Content-Length', str(len(payload)))
                if response.headers.get('Retry-After'):
                    self.send_header('Retry-After', response.headers['Retry-After'])
                self.end_headers()
                self.wfile.write(payload)
        except (TimeoutError, socket.timeout):
            self.fail(504, 'gateway_timeout')
        except (urllib.error.URLError, OSError):
            self.fail(503, 'pc_tunnel_unavailable')

    def log_message(self, format, *args):
        print(json.dumps({'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                          'method': self.command, 'path': self.path, 'status': args[1] if len(args) > 1 else None}), flush=True)


if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('127.0.0.1', 8781), Gateway).serve_forever()
