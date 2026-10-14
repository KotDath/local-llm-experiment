"""Actual Agent JSONL session verification, no Telegram or mocks."""
import json
from pathlib import Path
import subprocess
import sys
from common import append_jsonl, utc_now

ROOT = Path(__file__).parent


def main():
    process = subprocess.Popen([sys.executable, str(ROOT / 'protocol.py')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    count = 0

    def call(method, params=None):
        nonlocal count
        count += 1
        process.stdin.write(json.dumps({'id': count, 'method': method, 'params': params or {}}, ensure_ascii=False) + '\n')
        process.stdin.flush()
        result = json.loads(process.stdout.readline())
        append_jsonl(ROOT / 'results/cli_dialogues.jsonl', {'utc': utc_now(), 'method': method, 'response': result})
        if 'error' in result:
            raise RuntimeError(result['error']['code'])
        return result['result']
    try:
        a, b = call('session.create'), call('session.create')
        assert a['agent_id'] != b['agent_id']
        sid = a['session_id']
        call('agent.message', {'session_id': sid, 'message': 'В этом разговоре мой любимый фрукт — манго.'})
        recalled = call('agent.message', {'session_id': sid, 'message': 'Какой мой любимый фрукт?'})
        other = call('agent.message', {'session_id': b['session_id'], 'message': 'Какой мой любимый фрукт?'})
        call('session.reset', {'session_id': sid})
        reset = call('agent.message', {'session_id': sid, 'message': 'Какой мой любимый фрукт?'})
        for result in [recalled, other, reset]:
            for model_call in result['llm_calls']:
                assert model_call['counted_prompt_tokens'] == model_call['usage']['prompt_tokens']
        print(json.dumps({'recalled': recalled['text'], 'other_session': other['text'], 'after_reset': reset['text']}, ensure_ascii=False))
        assert 'манго' in recalled['text'].lower(), 'model_failed_recall; raw response retained'
        assert 'манго' not in other['text'].lower(), 'cross_session_leak_or_guess'
        assert 'манго' not in reset['text'].lower(), 'reset_leak_or_guess'
    finally:
        process.stdin.close()
        process.wait(timeout=5)


if __name__ == '__main__':
    main()
