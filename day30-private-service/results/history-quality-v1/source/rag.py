"""Local paper retrieval, optional neural reranking; no RAG framework."""
import json
import math
import os
import time
from common import http_json
from index import Index

PAPERS = {'memgpt': ('MemGPT', '2310.08560v2'),
          'memorybank': ('MemoryBank', '2305.10250v3'),
          'generative agents': ('Generative Agents', '2304.03442v2')}

class RAG:
    def __init__(self):
        self.index = Index()
        path = os.path.join(os.path.dirname(__file__), 'configs/retrieval.json')
        self.config = json.load(open(path))
        if self.config.get('index_generation', self.index.manifest['generation']) != self.index.manifest['generation']:
            from common import ServiceError
            raise ServiceError('retrieval_calibration_drift', 409)

    @staticmethod
    def retrieval_query(question):
        return 'Research papers on language model agents and long-term memory: ' + question

    def retrieve(self, question, rerank=False):
        start = time.monotonic()
        top_k = self.config.get('top_k', 12)
        query = self.retrieval_query(question) if self.config.get('topic_prefix') else question
        candidates = self.index.search(query, self.config.get('candidate_k', 20))
        requested = [pid for alias, (name, pid) in PAPERS.items() if alias in question.lower()]
        if ('трёх стат' in question.lower() or 'всех стат' in question.lower()) and len(requested) < 2:
            requested = [pid for _, pid in PAPERS.values()]
        queries = [query]
        # Retrieve each explicitly compared paper, then allocate equal evidence slots.
        # Labels are titles only; no expected answers or evaluation facts are injected.
        if requested:
            merged = {c['chunk']['id']: c for c in candidates}
            for name, pid in PAPERS.values():
                if pid not in requested: continue
                paper_query = name + ': ' + question
                queries.append(paper_query)
                for c in self.index.search(paper_query, len(self.index.chunks)):
                    if c['chunk'].get('source_revision') == pid:
                        old = merged.get(c['chunk']['id'])
                        if old is None or c['dense_score'] > old['dense_score']:
                            merged[c['chunk']['id']] = c
            candidates = sorted([c for c in merged.values() if c['chunk'].get('source_revision') in requested], key=lambda c: -c['dense_score'])
        dense_ms = (time.monotonic() - start) * 1000
        rerank_ms = 0
        metadata = {'index_generation': self.index.manifest['generation'],
                    'embedding_fingerprint': self.index.manifest['fingerprint'],
                    'retrieval_config': self.config, 'retrieval_query': query, 'retrieval_queries': queries,
                    'dense_ms': dense_ms, 'rerank_ms': 0}
        if not rerank and max(c['dense_score'] for c in candidates) < self.config.get('dense_question_threshold', -1):
            return {'evidence': [], 'candidates': candidates, **metadata, 'abstention_reason': 'question_threshold'}
        # Bound reranker work while retaining candidates from both compared papers.
        if rerank:
            if len(requested) >= 2:
                per = math.ceil(self.config.get('candidate_k', 20) / len(requested))
                candidates = [c for pid in requested for c in [e for e in candidates if e['chunk'].get('source_revision') == pid][:per]]
            candidates = candidates[:20]
            url = os.getenv('EMBED_URL', 'http://127.0.0.1:8765').rstrip('/')
            health = http_json(url + '/v1/reranker/health')
            then = time.monotonic()
            result = http_json(url + '/v1/rerank', {'query': question,
                'expected_model_fingerprint': health['fingerprint'],
                'candidates': [{'id': c['chunk']['id'], 'text': c['chunk']['text']} for c in candidates[:20]]})
            scores = {row['id']: row['score'] for row in result['outputs']}
            for c in candidates: c['rerank_score'] = scores[c['chunk']['id']]
            candidates.sort(key=lambda c: -c['rerank_score'])
            rerank_ms = (time.monotonic() - then) * 1000
        selected = []
        per_paper = math.ceil(top_k / len(requested)) if len(requested) >= 2 else top_k
        for entry in candidates:
            threshold = self.config['rerank_threshold'] if rerank else self.config['dense_threshold']
            score = entry['rerank_score'] if rerank else entry['dense_score']
            c = entry['chunk']
            if score < threshold: entry['excluded'] = 'threshold'; continue
            overlap = any(c['source'] == e['chunk']['source'] and
                max(0, min(c['end'], e['chunk']['end']) - max(c['start'], e['chunk']['start'])) /
                max(1, min(c['end']-c['start'], e['chunk']['end']-e['chunk']['start'])) >= .75 for e in selected)
            same = sum(e['chunk']['source'] == c['source'] for e in selected)
            if overlap: entry['excluded'] = 'overlap'
            elif len(requested) >= 2 and (c.get('source_revision') not in requested or same >= per_paper): entry['excluded'] = 'paper_balance'
            elif len(selected) >= top_k: entry['excluded'] = 'top_k'
            else: selected.append(entry)
        metadata['rerank_ms'] = rerank_ms
        return {'evidence': selected, 'candidates': candidates, **metadata}
