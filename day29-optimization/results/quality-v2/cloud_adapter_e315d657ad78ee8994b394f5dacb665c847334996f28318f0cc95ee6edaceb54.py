"""Explicit DeepSeek comparison using the same own Agent and local public-paper RAG."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from agent import Agent
from common import ServiceError, append_jsonl, http_json, utc_now
from model import Model

ROOT = Path(__file__).parent


class DeepSeekComparisonClient:
    def __init__(self):
        self.reference = Model()
        self.token = os.environ['DEEPSEEK_API_KEY']

    @staticmethod
    def brief_schema(schema):
        if isinstance(schema,list):return [DeepSeekComparisonClient.brief_schema(v) for v in schema]
        if not isinstance(schema,dict):return schema
        return {k:DeepSeekComparisonClient.brief_schema(v) for k,v in schema.items()
                if not (k=='enum' and isinstance(v,list) and len(v)>12)}

    @staticmethod
    def inferred_schema(messages):
        # Preflight sees the same generation shape before complete(profile) is called.
        try:payload=json.loads(messages[-1]['content'])
        except (ValueError,KeyError,TypeError):return None
        if not isinstance(payload,dict) or 'parts' not in payload or 'evidence' not in payload:return None
        from grounding import reference_format
        item=reference_format({row['id']:row for row in payload['evidence']})['schema']
        return {'type':'object','additionalProperties':False,'required':list(payload['parts']),
                'properties':{key:item for key in payload['parts']}}

    @classmethod
    def wire_messages(cls,messages,schema=None):
        copied=[dict(m) for m in messages]
        instruction='\nReturn only valid JSON.'
        if schema:instruction+=' Match this JSON schema exactly (no extra keys): '+json.dumps(cls.brief_schema(schema),ensure_ascii=False)
        if copied and copied[0]['role']=='system':copied[0]['content']+=instruction
        return copied

    def count_prompt(self,messages):
        return self.reference.count_prompt(self.wire_messages(messages,self.inferred_schema(messages)))

    def complete(self, messages, profile):
        schema=(profile.get('response_format') or {}).get('schema')
        wire=self.wire_messages(messages,schema)
        reference_count, reference_hash = self.reference.count_prompt(wire)
        if reference_count + profile['max_tokens'] > profile['context']:
            raise ServiceError('context_limit', 422)
        body = {'model': 'deepseek-flash', 'messages': wire,
                'temperature': profile['temperature'], 'top_p': 0.95, 'max_tokens': profile['max_tokens'],
                'thinking': {'type': 'disabled'}}
        if profile.get('response_format'):
            # DeepSeek JSON mode, not llama.cpp's schema-constrained decoder.
            body['response_format'] = {'type': 'json_object'}
        start = time.monotonic()
        raw = http_json('https://api.deepseek.com/chat/completions', body, token=self.token, timeout=600)
        try:
            choice = raw['choices'][0]
            text = choice['message']['content']
            if not isinstance(text, str) or not text:
                raise ValueError()
            usage = raw['usage']
        except (KeyError, IndexError, TypeError, ValueError):
            raise ServiceError('invalid_cloud_response', 502) from None
        return {'text': text, 'usage': usage, 'finish_reason': choice['finish_reason'],
                'generation_ms': (time.monotonic()-start)*1000, 'timings': {},
                'reference_prompt_tokens': reference_count, 'reference_prompt_hash': reference_hash,
                'reference_budget': 'Tiel template/tokenizer for actual wire messages incl explicit provider JSON schema instruction; cloud token usage is from API',
                'profile': profile, 'model': raw.get('model', 'deepseek-flash'), 'raw': raw}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'results/cloud_answers.jsonl')
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; choose a new file to preserve source/run provenance')
    client = DeepSeekComparisonClient()
    models = http_json('https://api.deepseek.com/models', token=client.token)
    ids = [row['id'] for row in models['data']]
    assert 'deepseek-flash' in ids, 'Requested model not available'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.with_suffix('.identity.json').write_text(json.dumps({
        'utc': utc_now(), 'endpoint': 'https://api.deepseek.com/models',
        'available_model_ids': ids, 'selected_model_id': 'deepseek-flash',
        'selected_model_available': True, 'transport': 'direct HTTP; no SDK',
        'role': 'explicit comparison only; no production fallback'}, indent=2))
    source_hash = hashlib.sha256(b''.join((ROOT/name).read_bytes() for name in
        ['agent.py','rag.py','model.py','grounding.py','index.py'])).hexdigest()
    questions = [json.loads(line) for line in (ROOT/'eval/golden_questions.jsonl').read_text().splitlines()]
    for question in questions:
        agent = Agent(profile='optimized', rag=True)
        # Agent initializes retrieval lazily; instantiate/verify before any cloud request.
        from rag import RAG
        agent.retriever = RAG()
        assert len(agent.retriever.index.documents)==3
        assert {(d['source'], d['revision']) for d in agent.retriever.index.documents} == {('https://arxiv.org/pdf/2310.08560v2','959a22bc9c10dd84ca52c1fd24d4ebd7ced4f4934f2051efe8e5f3696959098b'),('https://arxiv.org/pdf/2305.10250v3','4fc139a3be18ef695e860681d008e84d51eef89aab6c53ea71e792f1d3520775'),('https://arxiv.org/pdf/2304.03442v2','17bcff1a532f2ff7fc3193926f1048913d757df96f67ea9b8f40e30aa69a5a44')}
        agent.model = client
        record = {'id': question['id'], 'question': question['question'], 'mode': 'cloud',
                  'utc': utc_now(), 'source_sha256': source_hash,
                  'comparison_policy': 'same local retrieval, own Agent, system prompt and bounded review/revision; cloud JSON mode lacks local schema decoder; provider tokenizers/context differ'}
        start = time.monotonic()
        try:
            record.update(agent.ask(question['question']));record['ok']=True
        except ServiceError as exc:
            if isinstance(exc.detail, dict) and 'failure_trace' in exc.detail:
                record.update(exc.detail['failure_trace'])
            record.update(ok=False,error=exc.code,detail=exc.detail)
        record['total_ms']=(time.monotonic()-start)*1000
        append_jsonl(args.output,record)
        print(question['id'], record.get('status',record.get('error')),round(record['total_ms']),flush=True)


if __name__ == '__main__':main()
