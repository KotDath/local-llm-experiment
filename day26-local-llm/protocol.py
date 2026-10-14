"""JSONL stdio agent protocol: one JSON request/response per line, no Telegram."""
import json
import sys
import uuid
from agent import Agent
from common import ServiceError, load_env


def main():
    load_env()
    sessions = {}
    for line in sys.stdin:
        identifier = None
        try:
            if len(line.encode()) > 524288:
                raise ServiceError('body_limit', 413)
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ServiceError('invalid_request', 422)
            identifier = request.get('id')
            method = request['method']
            params = request.get('params', {})
            if not isinstance(params, dict):
                raise ServiceError('invalid_params', 422)
            if method == 'session.create':
                if len(sessions) >= 100:
                    raise ServiceError('session_limit', 503)
                sid = uuid.uuid4().hex
                agent = Agent(profile=params.get('profile', 'optimized'), rag=params.get('rag', False),
                              rerank=params.get('rerank', False), web=params.get('web', False))
                sessions[sid] = agent
                result = {'session_id': sid, 'agent_id': agent.agent_id}
            elif method in ('agent.message', 'session.reset', 'session.close'):
                sid = params.get('session_id')
                if not isinstance(sid, str):
                    raise ServiceError('invalid_session_id', 422)
                if sid not in sessions:
                    raise ServiceError('session_not_found', 404)
                agent = sessions[sid]
                if method == 'agent.message':
                    result = agent.ask(params['message'])
                elif method == 'session.reset':
                    agent.reset()
                    result = {'reset': True}
                else:
                    del sessions[sid]
                    result = {'closed': True}
            elif method == 'capabilities':
                result = {'protocol': 'local-agent-jsonl-v1', 'methods': ['session.create', 'agent.message', 'session.reset', 'session.close'],
                          'transport': 'stdio', 'generation': 'local-chat-api', 'framework': None}
            else:
                raise ServiceError('unknown_method', 404)
            response = {'id': identifier, 'result': result}
        except ServiceError as exc:
            response = {'id': identifier, 'error': {'code': exc.code, 'status': exc.status, 'detail': exc.detail}}
        except (ValueError, KeyError, TypeError):
            response = {'id': identifier, 'error': {'code': 'invalid_request', 'status': 422}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
