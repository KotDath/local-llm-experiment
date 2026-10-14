"""Adversarial index/citation/protocol checks; inference is tested separately."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import ServiceError
from agent import Agent
from grounding import validate
from index import Index, utf16_slice


class ProvenanceTests(unittest.TestCase):
    def test_real_index_and_tampered_footer(self):
        source = ROOT / 'data/week6/fixed.jsonl'
        index = Index(source)
        self.assertEqual(len(index.chunks), 182)
        with tempfile.TemporaryDirectory() as directory:
            corrupted = Path(directory) / 'index.jsonl'
            corrupted.write_bytes(source.read_bytes().replace(b'"dimension":1024', b'"dimension":1023', 1))
            # Mutation may have spaces in JSON; always change one byte in the payload.
            payload = bytearray(source.read_bytes())
            payload[payload.index(b'fixed')] = ord('F')
            corrupted.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, 'footer'):
                Index(corrupted)

    def test_utf16_surrogate_pair(self):
        self.assertEqual(utf16_slice('A😀Б', 1, 3), '😀')
        self.assertEqual(utf16_slice('A😀Б', 3, 4), 'Б')

    def test_citation_is_bound_to_sent_evidence(self):
        chunk = {'id': 'sent', 'source': 'source.md', 'revision': 'v1', 'section': 'rules',
                 'start': 2, 'text': 'Exact source quotation. More context.'}
        evidence = [{'chunk': chunk}]
        answer = {'status': 'answered', 'claims': [{'text': 'A claim', 'evidence': [
            {'chunk_id': 'sent', 'quote': 'Exact source quotation.'}]}]}
        self.assertEqual(validate(json.dumps(answer), evidence)['sources'][0]['start_utf16'], 2)
        answer['claims'][0]['evidence'][0]['chunk_id'] = 'not-sent'
        with self.assertRaises(ServiceError):
            validate(json.dumps(answer), evidence)
        answer['claims'][0]['evidence'][0] = {'chunk_id': 'sent', 'quote': 'Invented source quotation.'}
        with self.assertRaises(ServiceError):
            validate(json.dumps(answer), evidence)

    def test_protocol_survives_invalid_payloads(self):
        payload = '\n'.join(['[]', '{"id":2,"method":"session.create","params":[]}',
                             '{"id":3,"method":"capabilities"}']) + '\n'
        result = subprocess.run([sys.executable, str(ROOT / 'protocol.py')], input=payload,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(replies[0]['error']['status'], 422)
        self.assertEqual(replies[1]['error']['status'], 422)
        self.assertEqual(replies[2]['result']['protocol'], 'local-agent-jsonl-v1')

    def test_failed_repair_preserves_primary_response_and_usage(self):
        # Controller fault fixture, not evidence of real model quality.
        invalid = json.dumps({'P1':{'status': 'answered', 'claims': [{'text': 'A claim',
            'evidence': [{'chunk_id': 'fixture', 'quote': 'Invented source quotation.'}]}]}})

        class RepairTimeout:
            calls = 0

            def count_prompt(self, messages):
                return 50, 'fixture'

            def complete(self, messages, profile):
                self.calls += 1
                if profile['max_tokens'] == 512:
                    return {'text': json.dumps({'parts':[{'question':'A fixture question','search':'A fixture question'}]}),
                            'usage': {'prompt_tokens':5,'completion_tokens':9,'total_tokens':14},'finish_reason':'stop','timings':{}}
                if self.calls == 3:
                    raise ServiceError('upstream_timeout', 504)
                return {'text': invalid, 'usage': {'prompt_tokens': 5, 'completion_tokens': 9, 'total_tokens': 14},
                        'finish_reason': 'stop', 'timings': {}}

        class FixtureRetriever:
            def retrieve(self, question, rerank):
                return {'evidence': [{'chunk': {'id': 'fixture', 'source': 'fixture.md',
                    'revision': 'fixture', 'section': 'fixture', 'start': 0,
                    'text': 'Real supported source quotation.'}}]}

        agent = Agent(rag=True)
        agent.model, agent.retriever = RepairTimeout(), FixtureRetriever()
        with self.assertRaises(ServiceError) as caught:
            agent.ask('A fixture question')
        self.assertEqual(caught.exception.status, 504)
        trace = caught.exception.detail['failure_trace']
        self.assertEqual(trace['llm_calls'][1]['text'], invalid)
        self.assertEqual(trace['usage'], {'prompt_tokens': 10, 'completion_tokens': 18, 'total_tokens': 28})
        self.assertEqual(agent.history, [])

    def test_unresolved_reference_keeps_user_topic_outside_evidence(self):
        # Resolver fault fixture: previous assistant text must not enter retrieval.
        question = 'Какие из них общие?'
        user_topic = 'Какие слои памяти есть в проекте?'
        assistant_text = 'UNSUPPORTED PREVIOUS ANSWER'

        class UnresolvedModel:
            def count_prompt(self, messages):
                return 50, 'fixture'

            def complete(self, messages, profile):
                if profile['max_tokens']==512 and any(key.startswith('C') for key in profile.get('response_format',{}).get('schema',{}).get('properties',{})):
                    return {'text':json.dumps({key:True for key in profile['response_format']['schema']['properties']}),
                            'usage':{'prompt_tokens':5,'completion_tokens':9,'total_tokens':14},'finish_reason':'stop','timings':{}}
                value = ({'query': question} if profile['max_tokens'] == 256 else
                         {'parts':[{'question':messages[-1]['content'],'search':messages[-1]['content']}]} if profile['max_tokens']==512 else
                         {'coverage':{'complete':True,'issues':[]},'P1':{'complete': True, 'unsupported_claims': [], 'issues': []}} if profile['max_tokens'] == 1024 else {'P1':{
                    'status': 'answered', 'claims': [{'text': 'The supported answer',
                    'citations': ['E001']}]}})
                return {'text': json.dumps(value), 'usage': {'prompt_tokens': 5, 'completion_tokens': 9, 'total_tokens': 14},
                        'finish_reason': 'stop', 'timings': {}}

        class CaptureRetriever:
            query = None

            def retrieve(self, query, rerank):
                self.query = query
                return {'evidence': [{'chunk': {'id': 'fixture', 'source': 'fixture.md',
                    'revision': 'fixture', 'section': 'fixture', 'start': 0,
                    'text': 'Real supported source quotation.'}}]}

        agent = Agent(rag=True)
        agent.history = [{'role': 'user', 'content': user_topic}, {'role': 'assistant', 'content': assistant_text}]
        agent.model, agent.retriever = UnresolvedModel(), CaptureRetriever()
        result = agent.ask(question)
        self.assertIn(user_topic, agent.retriever.query)
        self.assertIn(question, agent.retriever.query)
        self.assertNotIn(assistant_text, agent.retriever.query)
        self.assertEqual(result['sources'][0]['source'], 'fixture.md')
        self.assertEqual(len(result['llm_calls']), 5)


if __name__ == '__main__':
    unittest.main()
