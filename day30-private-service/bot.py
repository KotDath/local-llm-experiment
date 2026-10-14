"""Telegram adapter using Bot API directly. Inference remains in Chat on this PC."""
import argparse
import concurrent.futures
import json
import os
import threading
import time
from urllib.parse import urlencode
from common import ServiceError, append_jsonl, http_json, load_env, utc_now
from pathlib import Path
import hashlib
from chat import Chat


def selected_profile(explicit=None):
    path = Path(__file__).parent / 'configs/selected.json'
    profile = explicit or (json.loads(path.read_text()).get('profile', 'optimized') if path.exists() else 'optimized')
    if profile not in ('baseline', 'optimized'):
        raise ValueError('Invalid measured profile selection')
    return profile


class Bot:
    def __init__(self, rag=False, profile=None):
        self.token = os.environ['TG_BOT_TOKEN']
        self.allowed = {int(x) for x in os.getenv('TG_ALLOWED_IDS', '').split(',') if x.strip()}
        self.rag = rag
        self.profile = selected_profile(profile)
        self.sessions, self.locks = {}, {}
        self.guard = threading.Lock()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.pending = threading.BoundedSemaphore(10)

    def call(self, method, data=None):
        result = http_json('https://api.telegram.org/bot' + self.token + '/' + method, data, timeout=45)
        if not result.get('ok'):
            raise ServiceError('telegram_error', 502)
        return result['result']

    def handle(self, message):
        user = message.get('from', {}).get('id')
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text')
        if user not in self.allowed or not isinstance(text, str):
            return 'ignored'
        with self.guard:
            key = (user, chat_id)
            self.sessions.setdefault(key, Chat(profile=self.profile, rag=self.rag))
            self.locks.setdefault(key, threading.Lock())
        with self.locks[key]:
            if text.startswith('/start'):
                trace = None
                answer = 'Локальный Tiel Coder на ПК. Напишите вопрос. /reset очищает историю. Telegram передаёт сообщения через свою инфраструктуру.'
            elif text.startswith('/reset'):
                trace = None
                self.sessions[key].reset()
                answer = 'История очищена.'
            else:
                try:
                    trace = self.sessions[key].ask(text)
                    answer = trace['text']
                except ServiceError as exc:
                    trace = None
                    answer = 'Ошибка локального сервиса: ' + exc.code
            for start in range(0, len(answer), 3500):
                # Retry Telegram's own 429 independently of inference.
                for attempt in range(3):
                    try:
                        receipt = self.call('sendMessage', {'chat_id': chat_id, 'text': answer[start:start + 3500]})
                        append_jsonl(Path(__file__).parent / 'results/telegram_receipts.jsonl', {
                            'utc': utc_now(), 'message_id': receipt['message_id'],
                            'input_sha256': hashlib.sha256(text.encode()).hexdigest(),
                            'reply_sha256': hashlib.sha256(answer[start:start + 3500].encode()).hexdigest(),
                            'model_host': 'PC-loopback', 'usage': trace.get('usage') if trace else None,
                            'llm_calls': len(trace['llm_calls']) if trace else 0,
                            'command': text.split()[0] if text.startswith('/') else 'message',
                        })
                        break
                    except ServiceError as exc:
                        if exc.status != 429 or attempt == 2:
                            raise
                        delay = (exc.detail or {}).get('parameters', {}).get('retry_after', 2)
                        time.sleep(min(delay, 30))
        return 'handled'

    def worker(self, message):
        try:
            self.handle(message)
        except Exception as exc:
            print(json.dumps({'error': type(exc).__name__}), flush=True)
        finally:
            self.pending.release()

    def run(self):
        if not self.allowed:
            raise SystemExit('Set TG_ALLOWED_IDS to your Telegram user ID; see --inspect')
        if self.call('getWebhookInfo').get('url'):
            raise SystemExit('Existing webhook detected. Choose transport explicitly before switching.')
        print('Telegram polling ready; allowlist active; local inference only; profile=' + self.profile, flush=True)
        offset = None
        while True:
            try:
                updates = self.call('getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': ['message']})
                for update in updates:
                    offset = update['update_id'] + 1
                    message = update.get('message')
                    if not message or message.get('from', {}).get('id') not in self.allowed:
                        continue
                    if self.pending.acquire(blocking=False):
                        self.pool.submit(self.worker, message)
                    else:
                        self.call('sendMessage', {'chat_id': message['chat']['id'],
                                  'text': 'Очередь локального агента занята. Повторите запрос немного позже.'})
            except ServiceError as exc:
                print(json.dumps({'error': exc.code, 'status': exc.status}), flush=True)
                time.sleep(3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file')
    parser.add_argument('--rag', action='store_true')
    parser.add_argument('--profile', choices=['baseline', 'optimized'],
                        help='Override measured profile; default comes from configs/selected.json')
    parser.add_argument('--inspect', action='store_true')
    args = parser.parse_args()
    load_env(args.env_file)
    bot = Bot(rag=args.rag, profile=args.profile)
    if args.inspect:
        me, webhook = bot.call('getMe'), bot.call('getWebhookInfo')
        updates = [] if webhook.get('url') else bot.call('getUpdates', {'timeout': 0, 'limit': 20})
        print(json.dumps({'username': me['username'], 'webhook_present': bool(webhook.get('url')),
                          'pending_message_count': sum('message' in u for u in updates),
                          'user_ids': sorted({u['message']['from']['id'] for u in updates if 'message' in u})}))
    else:
        bot.run()
