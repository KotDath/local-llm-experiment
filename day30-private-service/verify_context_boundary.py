"""Actual selected-profile token boundary. Run only after the benchmark stops.

Token counting calls use the protected PC loopback backend; accepted/overflow
requests use the authenticated API, including the public HTTPS gateway.
Credentials never enter argv, printed output or the saved evidence.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
from common import ServiceError, http_json, load_env, utc_now
from model import Model

ROOT = Path(__file__).resolve().parent


def plain_system_messages():
    # Extract the actual frozen controller envelope rather than estimate its
    # overhead or maintain a separately typed copy of the system prompt.
    tree = ast.parse((ROOT / 'agent.py').read_text())
    agent = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Agent')
    execute = next(node for node in agent.body if isinstance(node, ast.FunctionDef) and node.name == '_execute')
    branch = next(node for node in execute.body if isinstance(node, ast.If)
                  and isinstance(node.test, ast.Attribute) and node.test.attr == 'rag')
    assignment = next(node for node in branch.orelse if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'messages' for target in node.targets))
    result = ast.literal_eval(assignment.value)
    if not result or result[0]['role'] != 'system':
        raise RuntimeError('Unexpected current Agent message envelope')
    return result


def payload(repeats):
    return ('Проверка контекстного предела. Следующий наполнитель — служебные данные, '
            'не анализируй и не повторяй его.\n' + 'x ' * repeats +
            '\nКонец наполнителя. Ответь только одним словом: готово.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='http://127.0.0.1:8780')
    parser.add_argument('--model-url', default='http://127.0.0.1:8772')
    parser.add_argument('--env-file')
    parser.add_argument('--output', default=str(ROOT / 'results/articles_context_boundary.json'))
    args = parser.parse_args()
    load_env(args.env_file)
    token = os.environ.get('API_TOKEN')
    if not token:
        parser.error('Set API_TOKEN in private env; never pass the value in argv')
    base = args.api_url.rstrip('/')
    health = http_json(base + '/health', token=token)
    model = Model(args.model_url)
    props = model.info()
    context = health['configured_context']
    reserve = health['configured_max_tokens']
    if not health['context_matches'] or props['default_generation_settings']['n_ctx'] != context:
        raise RuntimeError('Selected profile and running model context do not match')
    if not health['slots_match'] or not health['ready']:
        raise RuntimeError('Restore the final matching API/model slots before this test')
    if (context, reserve) not in [(32768, 6144), (65536, 8192)]:
        raise RuntimeError('Unexpected selected fourfold context/output configuration')
    target = context - reserve
    system = plain_system_messages()
    counter_calls = 0

    def count(repeats):
        nonlocal counter_calls
        counter_calls += 1
        return model.count_prompt(system + [{'role': 'user', 'content': payload(repeats)}])[0]

    low, high = 0, context * 2
    if count(0) > target or count(high) <= target:
        raise RuntimeError('Tokenizer filler does not bracket the actual prompt budget')
    while low + 1 < high:
        middle = (low + high) // 2
        if count(middle) <= target:
            low = middle
        else:
            high = middle
    accepted_count, overflow_count = count(low), count(high)
    if accepted_count != target or overflow_count != target + 1:
        raise RuntimeError('Could not reach the exact token boundary; do not report an estimated result')
    accepted_question, overflow_question = payload(low), payload(high)
    api_tree = ast.parse((ROOT / 'api.py').read_text())
    body_assignment = next(node for node in api_tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'BODY_LIMIT' for t in node.targets))
    body_limit = ast.literal_eval(body_assignment.value)
    accepted_bytes = len(json.dumps({'message': accepted_question}, ensure_ascii=False).encode())
    overflow_bytes = len(json.dumps({'message': overflow_question}, ensure_ascii=False).encode())
    if max(accepted_bytes, overflow_bytes) > body_limit:
        raise RuntimeError('Body quota would hide the token boundary; choose a smaller-byte filler')
    result = http_json(base + '/chat', {'message': accepted_question}, token=token)
    calls = result['llm_calls']
    if len(calls) != 1 or calls[0]['counted_prompt_tokens'] != target or calls[0]['usage']['prompt_tokens'] != target:
        raise RuntimeError('Actual generated prompt usage does not equal the measured boundary')
    if result['profile']['max_tokens'] != reserve or result['profile']['context'] != context:
        raise RuntimeError('Selected API profile changed during the check')
    try:
        http_json(base + '/chat', {'message': overflow_question}, token=token)
        raise AssertionError('One-token overflow was accepted')
    except ServiceError as exc:
        if exc.status != 422 or not isinstance(exc.detail, dict) or exc.detail.get('error') != 'context_limit':
            raise
        detail = exc.detail.get('detail') or {}
        if detail.get('prompt_tokens') != target + 1 or detail.get('output_reserve') != reserve:
            raise RuntimeError('Overflow did not come from the exact full rendered prompt/output budget')
        failure = detail.get('failure_trace', {})
        if failure.get('llm_calls'):
            raise RuntimeError('Overflow unexpectedly performed generation')
        rejected = {'status': exc.status, 'error': exc.detail['error'],
                    'prompt_tokens': detail['prompt_tokens'], 'output_reserve': detail['output_reserve'],
                    'effective_context': detail.get('context'), 'generation_calls': 0}
    source = hashlib.sha256(b''.join((ROOT / name).read_bytes() for name in
                            ['agent.py', 'rag.py', 'model.py', 'grounding.py', 'index.py'])).hexdigest()
    record = {'utc': utc_now(), 'mode': 'actual API/model token-boundary test, no synthetic upstream',
              'api_url': base, 'tls_verified': base.startswith('https://'),
              'source_sha256': source, 'profile': health['configured_profile'],
              'model_file': Path(props['model_path']).name, 'context': context, 'output_reserve': reserve,
              'body_limit_bytes': body_limit, 'token_count_calls': counter_calls,
              'accepted': {'status': 200, 'prompt_tokens': target, 'body_bytes': accepted_bytes,
                           'filler_repetitions': low, 'request_id': result['request_id'],
                           'question_sha256': hashlib.sha256(accepted_question.encode()).hexdigest(),
                           'text': result['text'], 'usage': result['usage'], 'finish_reason': result['finish_reason'],
                           'timings': calls[0]['timings'], 'actual_llm_calls': len(calls)},
              'rejected': rejected | {'body_bytes': overflow_bytes, 'filler_repetitions': high}}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'profile': record['profile'], 'context': context, 'reserve': reserve,
                      'accepted_prompt': target, 'rejected_prompt': target + 1, 'saved': str(path)}))


if __name__ == '__main__':
    main()
