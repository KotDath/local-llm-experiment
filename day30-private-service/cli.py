"""CLI frontend for the stateful Agent or its private HTTP service."""
import argparse
import json
import os
import sys
from common import ServiceError, http_json, load_env
from model import Model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['ask', 'chat', 'health'])
    parser.add_argument('question', nargs='?')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--rag', action='store_true')
    parser.add_argument('--rerank', action='store_true')
    parser.add_argument('--web', action='store_true')
    parser.add_argument('--profile', choices=['baseline', 'optimized'], default='optimized')
    parser.add_argument('--api-url')
    parser.add_argument('--env-file')
    args = parser.parse_args()
    load_env(args.env_file)
    args.api_url = args.api_url or os.getenv('API_URL')
    token = os.environ.get('API_TOKEN')
    if args.api_url and not token:
        parser.error('Set API_TOKEN in private env for --api-url')
    if args.command == 'ask' and not args.question:
        parser.error('ask requires a question')

    def output(answer):
        print(json.dumps(answer, ensure_ascii=False) if args.json else answer['text'], flush=True)

    try:
        if args.command == 'health':
            result = http_json(args.api_url.rstrip('/') + '/health', token=token) if args.api_url else Model().health()
            print(json.dumps(result, ensure_ascii=False))
            return
        if args.api_url:
            base = args.api_url.rstrip('/')
            session = http_json(base + '/sessions', {}, token)['session_id']

            def ask(question):
                return http_json(base + '/chat', {
                    'session_id': session, 'message': question, 'rag': args.rag,
                    'rerank': args.rerank, 'web': args.web,
                }, token)

            def reset():
                http_json(base + '/sessions/reset', {'session_id': session}, token)
        else:
            from agent import Agent
            agent = Agent(profile=args.profile, rag=args.rag, rerank=args.rerank, web=args.web)
            ask, reset = agent.ask, agent.reset
        if args.command == 'ask':
            output(ask(args.question))
        else:
            for line in sys.stdin:
                question = line.strip()
                if question == '/exit':
                    break
                if question == '/reset':
                    reset()
                    print('История очищена.', flush=True)
                elif question:
                    output(ask(question))
    except ServiceError as exc:
        print(json.dumps({'error': exc.code, 'status': exc.status, 'detail': exc.detail}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
