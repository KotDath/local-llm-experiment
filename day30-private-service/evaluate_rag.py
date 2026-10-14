"""Local M0/M1/M2 and explicit opt-in cloud comparison, actual traces retained."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from chat import Chat
from common import ServiceError, append_jsonl, utc_now

ROOT = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cloud', action='store_true')
    parser.add_argument('--set', choices=['dev', 'golden'], default='golden')
    parser.add_argument('--modes', default='M0,M1,M2')
    args = parser.parse_args()
    questions = [json.loads(line) for line in (ROOT / ('eval/' + args.set + '_questions.jsonl')).read_text().splitlines()]
    for mode in args.modes.split(','):
        for question in questions:
            service = Chat(rag=mode != 'M0', rerank=mode == 'M2')
            start = time.monotonic()
            record = {'source_sha256': hashlib.sha256(b''.join((ROOT / name).read_bytes() for name in ['agent.py','rag.py','model.py','grounding.py','index.py'])).hexdigest(), 'mode': mode, 'id': question['id'], 'question': question['question'], 'utc': utc_now()}
            try:
                record.update(service.ask(question['question']))
                record['ok'] = True
            except ServiceError as exc:
                if isinstance(exc.detail, dict) and 'failure_trace' in exc.detail:
                    record.update(exc.detail['failure_trace'])
                record.update({'ok': False, 'error': exc.code, 'detail': exc.detail})
            record['total_ms'] = (time.monotonic() - start) * 1000
            append_jsonl(ROOT / ('results/' + args.set + '_rag_answers.jsonl'), record)
            print(mode, question['id'], record.get('status', record.get('error')), round(record['total_ms']), flush=True)
    if args.cloud:
        if args.set != 'golden':
            raise SystemExit('--cloud uses the frozen golden set; run compare_cloud.py separately')
        from compare_cloud import main as compare
        compare()


if __name__ == '__main__':
    main()
