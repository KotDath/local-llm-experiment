"""Portable actual HTTP concurrency tester; runs on the VPS with stdlib only."""
import argparse
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request


def request(url, token, data):
    start = time.monotonic()
    req = urllib.request.Request(url.rstrip('/') + '/chat', data=json.dumps(data).encode(),
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            body, status = json.load(r), r.status
    except urllib.error.HTTPError as e:
        body, status = json.load(e), e.code
    except Exception as e:
        body, status = {'error': type(e).__name__}, 0
    return {'status': status, 'elapsed_ms': (time.monotonic() - start) * 1000,
            'request_id': body.get('request_id'), 'text': body.get('text'), 'usage': body.get('usage'),
            'llm_calls': len(body.get('llm_calls', [])), 'error': body.get('error')}


def load(url, token, count):
    questions = ['Назови столицу Франции одним предложением.', 'Назови столицу Японии одним предложением.',
                 'Назови столицу Италии одним предложением.', 'Как называется планета, на которой мы живём?']
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(lambda i: request(url, token, {'message': questions[i % len(questions)]}), range(count)))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--url', default='http://127.0.0.1:8781')
    p.add_argument('--count', type=int, default=10)
    args = p.parse_args()
    print(json.dumps({'client': 'remote', 'count': args.count, 'results': load(args.url, os.environ['API_TOKEN'], args.count)}, ensure_ascii=False))
