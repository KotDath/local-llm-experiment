"""Private authenticated HTTP chat, one process, bounded admission and sessions."""
import asyncio
from collections import defaultdict, deque
import hashlib
import json
import math
import os
import secrets
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from chat import Chat
from common import ServiceError, append_jsonl, load_env, utc_now
from model import Model

load_env(Path(__file__).parent / '.env')
CORE_SHA=hashlib.sha256(b''.join((Path(__file__).parent/name).read_bytes() for name in
    ['agent.py','rag.py','model.py','grounding.py','index.py'])).hexdigest()
app = FastAPI(title='Private local LLM', docs_url=None, redoc_url=None, openapi_url=None)
BODY_LIMIT = 524288
RATE = int(os.getenv('RATE_LIMIT', '20'))
WINDOW = float(os.getenv('RATE_WINDOW', '60'))
ACTIVE = int(os.getenv('API_SLOTS', '3'))
QUEUE = int(os.getenv('API_QUEUE', '10'))
QUEUE_WAIT = float(os.getenv('API_QUEUE_WAIT_TIMEOUT', '120'))
TTL = 1800
SESSION_LIMIT = 100
TOKENS = [t for t in [os.getenv('API_TOKEN', ''), *os.getenv('API_TEST_TOKENS', '').split(',')] if t]
if not TOKENS:
    raise RuntimeError('Set API_TOKEN in private .env')
requests = defaultdict(deque)
semaphore = asyncio.Semaphore(ACTIVE)
pending = 0
sessions = {}


def error(code, status, detail=None, headers=None):
    return JSONResponse({'error': code, 'detail': detail}, status_code=status, headers=headers)


@app.middleware('http')
async def authenticate_and_limit(request, call_next):
    header = request.headers.get('authorization', '')
    provided = header.removeprefix('Bearer ') if header.startswith('Bearer ') else ''
    matched = False
    for token in TOKENS:
        matched = secrets.compare_digest(provided.encode(), token.encode()) or matched
    if not matched:
        return error('unauthorized', 401)
    owner = hashlib.sha256(provided.encode()).hexdigest()
    request.state.owner = owner
    if request.method != 'GET':
        now = time.monotonic()
        queue = requests[owner]
        while queue and queue[0] <= now - WINDOW:
            queue.popleft()
        if len(queue) >= RATE:
            return error('rate_limit', 429, headers={'Retry-After': str(max(1, math.ceil(WINDOW - (now - queue[0]))))})
        queue.append(now)
    length = request.headers.get('content-length')
    if length:
        try:
            if int(length) > BODY_LIMIT:
                return error('body_limit', 413)
        except ValueError:
            return error('invalid_content_length', 400)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > BODY_LIMIT:
            return error('body_limit', 413)
    request._body = bytes(body)
    return await call_next(request)


def prune_sessions():
    now = time.monotonic()
    for sid in list(sessions):
        entry = sessions[sid]
        if now - entry['touched'] > TTL and not entry['lock'].locked():
            del sessions[sid]


async def body(request):
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, TypeError):
        raise ServiceError('invalid_json', 422) from None


@app.exception_handler(ServiceError)
async def handle_service_error(request, exc):
    return error(exc.code, exc.status, exc.detail)


def selected_profile():
    path = Path(__file__).parent / 'configs/selected.json'
    profile = json.loads(path.read_text()).get('profile', 'optimized') if path.exists() else 'optimized'
    if profile not in ('baseline', 'optimized'):
        raise RuntimeError('Invalid measured profile selection')
    return profile


@app.get('/health')
async def health():
    try:
        model = Model()
        await asyncio.to_thread(model.health)
        props = await asyncio.to_thread(model.info)
        from index import Index, Embeddings
        try:
            index = await asyncio.to_thread(Index)
            embedding = await asyncio.to_thread(Embeddings().health)
            rag_ready = embedding['fingerprint'] == index.manifest['fingerprint']
            generation = index.manifest['generation']
        except (ServiceError, ValueError, OSError):
            rag_ready, generation = False, None
        settings = json.loads((Path(__file__).parent / 'configs' / (selected_profile()+'.json')).read_text())
        return {'ready': True, 'agent_source_sha256': CORE_SHA, 'configured_profile': selected_profile(),
                'configured_context': settings['context'], 'configured_max_tokens': settings['max_tokens'],
                'context_matches': props['default_generation_settings']['n_ctx'] == settings['context'],
                'model': props['model_alias'], 'model_host': 'PC-loopback',
                'slots': props['total_slots'], 'context_per_slot': props['default_generation_settings']['n_ctx'],
                'api_slots': ACTIVE, 'slots_match': props['total_slots'] == ACTIVE,
                'rag_ready': rag_ready, 'index_generation': generation,
                'pending': pending, 'queue_limit': QUEUE, 'queue_wait_timeout_s': QUEUE_WAIT, 'rate': RATE, 'rate_window': WINDOW}
    except ServiceError:
        return error('model_unavailable', 503)


@app.post('/sessions')
async def create_session(request: Request):
    await body(request)
    prune_sessions()
    if len(sessions) >= SESSION_LIMIT:
        return error('session_limit', 503)
    sid = uuid.uuid4().hex
    sessions[sid] = {'owner': request.state.owner, 'chat': None, 'lock': asyncio.Lock(), 'touched': time.monotonic()}
    return {'session_id': sid}


@app.post('/sessions/reset')
async def reset_session(request: Request):
    data = await body(request)
    if not isinstance(data.get('session_id'), str):
        return error('invalid_session_id', 422)
    entry = sessions.get(data.get('session_id'))
    if not entry or entry['owner'] != request.state.owner:
        return error('session_not_found', 404)
    if entry['lock'].locked():
        return error('session_busy', 409)
    if entry['chat']:
        entry['chat'].reset()
        entry['chat'] = None
    entry['touched'] = time.monotonic()
    return {'reset': True}


@app.post('/chat')
async def chat(request: Request):
    global pending
    data = await body(request)
    if set(data) - {'message', 'session_id', 'rag', 'rerank', 'web'}:
        return error('unknown_fields', 422)
    question = data.get('message')
    if not isinstance(question, str) or not question.strip():
        return error('empty_question', 422)
    if 'session_id' in data and not isinstance(data['session_id'], str):
        return error('invalid_session_id', 422)
    for flag in ['rag', 'rerank', 'web']:
        if flag in data and type(data[flag]) is not bool:
            return error('invalid_flag', 422)
    if pending >= ACTIVE + QUEUE:
        return error('busy', 503)
    prune_sessions()
    entry = None
    if data.get('session_id'):
        entry = sessions.get(data['session_id'])
        if not entry or entry['owner'] != request.state.owner:
            return error('session_not_found', 404)
        if entry['lock'].locked():
            return error('session_busy', 409)
    started = time.monotonic()
    pending += 1
    if entry:
        await entry['lock'].acquire()
    acquired = False
    try:
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=QUEUE_WAIT)
            acquired = True
        except asyncio.TimeoutError:
            return error('queue_wait_timeout', 503)
        if acquired:
            if entry and entry['chat']:
                service = entry['chat']
                if (service.rag, service.rerank, service.web) != (data.get('rag', False), data.get('rerank', False), data.get('web', False)):
                    return error('session_mode_mismatch_reset_or_create', 409)
            else:
                service = Chat(profile=selected_profile(), rag=data.get('rag', False), rerank=data.get('rerank', False), web=data.get('web', False))
                if entry:
                    entry['chat'] = service
            # Reject oversized question before embedding/retrieval. Exact full budget is checked in Chat.
            count, _ = await asyncio.to_thread(service.model.count_prompt, [{'role': 'user', 'content': question}])
            if count + service.profile['max_tokens'] > service.profile['context']:
                return error('context_limit', 422, {'prompt_tokens': count})
            result = await asyncio.to_thread(service.ask, question)
            result['source_sha256']=CORE_SHA
            result['http_total_ms'] = (time.monotonic() - started) * 1000
            if entry:
                entry['touched'] = time.monotonic()
            append_jsonl(Path(__file__).parent / 'runtime/api_requests.jsonl', {
                'request_id': result['request_id'], 'utc': utc_now(), 'status': 200,
                'source_sha256': CORE_SHA, 'usage': result['usage'], 'llm_calls': len(result['llm_calls']),
                'total_ms': result['http_total_ms'], 'question_sha256': hashlib.sha256(question.encode()).hexdigest(),
            })
            return result
    finally:
        if acquired:
            semaphore.release()
        pending -= 1
        if entry:
            entry['lock'].release()
