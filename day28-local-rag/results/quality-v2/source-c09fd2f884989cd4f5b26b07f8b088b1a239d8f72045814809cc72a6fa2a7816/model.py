"""Local llama.cpp HTTP client with actual rendered-prompt token accounting."""
import hashlib
import json
import os
import time
from urllib.parse import urlsplit
from common import ServiceError, http_json


class Model:
    def __init__(self, url=None):
        self.url = (url or os.getenv('MODEL_URL', 'http://127.0.0.1:8772')).rstrip('/')
        parsed = urlsplit(self.url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Generation endpoint must be local loopback HTTP')
        self.timeout = float(os.getenv('MODEL_TIMEOUT', '600'))

    def call(self, endpoint, body=None):
        return http_json(self.url + endpoint, body, timeout=self.timeout)

    def health(self):
        return self.call('/health')

    def info(self):
        return self.call('/props')

    def count_prompt(self, messages):
        rendered = self.call('/apply-template', {
            'messages': messages, 'add_generation_prompt': True,
            'chat_template_kwargs': {'enable_thinking': False},
        })['prompt']
        tokens = self.call('/tokenize', {
            'content': rendered, 'add_special': True, 'parse_special': True,
        })['tokens']
        return len(tokens), hashlib.sha256(rendered.encode()).hexdigest()

    def complete(self, messages, profile=None):
        profile = profile or {'temperature': 1.0, 'max_tokens': 6144, 'context': 32768}
        count, prompt_hash = self.count_prompt(messages)
        reserve = profile['max_tokens']
        runtime_context = self.info()['default_generation_settings']['n_ctx']
        context = min(profile['context'], runtime_context)
        if count + reserve > context:
            raise ServiceError('context_limit', 422, {'prompt_tokens': count, 'output_reserve': reserve,
                                                     'context': context})
        start = time.monotonic()
        body = {
            'model': 'tiel-coder', 'messages': messages, 'stream': False,
            'temperature': profile['temperature'], 'max_tokens': reserve,
            'top_p': 0.95, 'top_k': 20, 'min_p': 0, 'cache_prompt': False,
            'seed': profile.get('seed', 42),
            'chat_template_kwargs': {'enable_thinking': False}, 'reasoning_effort': 'none',
        }
        if profile.get('response_format'):
            body['response_format'] = profile['response_format']
        raw = self.call('/v1/chat/completions', body)
        try:
            choice = raw['choices'][0]
            text = choice['message'].get('content') or ''
            usage, timings = raw['usage'], raw.get('timings', {})
            if not text or not isinstance(text, str):
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError):
            raise ServiceError('invalid_model_response', 502) from None
        return {
            'text': text, 'usage': usage, 'timings': timings,
            'finish_reason': choice.get('finish_reason'), 'counted_prompt_tokens': count,
            'prompt_hash': prompt_hash, 'generation_ms': (time.monotonic() - start) * 1000,
            'profile': profile, 'model': 'tiel-coder', 'raw': raw,
        }
