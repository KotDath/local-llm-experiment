"""Local hybrid retrieval with rank fusion and canonical context expansion."""
import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from common import http_json
from index import Index, utf16_slice

PAPERS = {'memgpt': ('MemGPT', '2310.08560v2'),
          'memorybank': ('MemoryBank', '2305.10250v3'),
          'generative agents': ('Generative Agents', '2304.03442v2')}


def terms(text):
    return re.findall(r'[a-zа-яё0-9]+', text.lower())


def fuse(rankings, constant=60):
    """Scores from distinct queries are never compared directly."""
    merged = {}
    for label, rows, weight in rankings:
        for rank, entry in enumerate(rows, 1):
            cid = entry['chunk']['id']
            row = merged.setdefault(cid, {**entry, 'fusion_score': 0.0, 'retrieval_ranks': {}})
            row['fusion_score'] += weight / (constant + rank)
            row['retrieval_ranks'][label] = rank
    return sorted(merged.values(), key=lambda row: (-row['fusion_score'], row['chunk']['id']))


class RAG:
    def __init__(self):
        self.index = Index()
        path = os.path.join(os.path.dirname(__file__), 'configs/retrieval.json')
        self.config = json.load(open(path))
        if self.config.get('index_generation', self.index.manifest['generation']) != self.index.manifest['generation']:
            from common import ServiceError
            raise ServiceError('retrieval_calibration_drift', 409)
        self.bags = [Counter(terms(c['text'])) for c in self.index.chunks]
        self.df = Counter(term for bag in self.bags for term in bag)
        self.average_length = sum(sum(bag.values()) for bag in self.bags) / len(self.bags)
        self.documents = {d['source']: d for d in self.index.documents}

    @staticmethod
    def retrieval_query(question):
        return question

    def lexical(self, query, requested):
        query_terms = set(terms(query))
        rows = []
        for chunk, bag in zip(self.index.chunks, self.bags):
            if requested and chunk.get('source_revision') not in requested:
                continue
            length = sum(bag.values())
            score = 0.0
            for term in query_terms:
                count = bag[term]
                if not count:
                    continue
                idf = math.log(1 + (len(self.bags) - self.df[term] + .5) / (self.df[term] + .5))
                score += idf * count * 2.2 / (count + 1.2 * (.25 + .75 * length / self.average_length))
            if score > 0:
                rows.append({'chunk': chunk, 'lexical_score': score})
        return sorted(rows, key=lambda row: (-row['lexical_score'], row['chunk']['id']))

    def expand(self, row):
        chunk = row['chunk']
        same = [c for c in self.index.chunks if c['source'] == chunk['source']]
        position = next(i for i, c in enumerate(same) if c['id'] == chunk['id'])
        neighbors = same[max(0, position - 1):position + 2]
        start, end = min(c['start'] for c in neighbors), max(c['end'] for c in neighbors)
        document = self.documents[chunk['source']]
        expanded = dict(chunk, id=hashlib.sha256((chunk['source']+':'+str(start)+':'+str(end)).encode()).hexdigest(),
                        start=start, end=end, text=utf16_slice(document['text'], start, end),
                        native_chunk_ids=[c['id'] for c in neighbors], retrieval_anchor=chunk['id'])
        from bisect import bisect_right
        starts = document.get('page_starts', [])
        if starts:
            expanded.update(page_start=bisect_right(starts, start), page_end=bisect_right(starts, end - 1))
        return {**row, 'chunk': expanded}

    def retrieve(self, question, rerank=False):
        start = time.monotonic()
        requested = list(dict.fromkeys(pid for alias, (_, pid) in PAPERS.items() if alias in question.lower()))
        if ('трёх стат' in question.lower() or 'всех стат' in question.lower()) and len(requested) < 2:
            requested = [pid for _, pid in PAPERS.values()]
        queries = [question]
        queries += [name + ': ' + question for name, pid in PAPERS.values() if pid in requested]
        rankings = []
        for number, query in enumerate(dict.fromkeys(queries)):
            rows = self.index.search(query, len(self.index.chunks))
            if requested:
                rows = [r for r in rows if r['chunk'].get('source_revision') in requested]
            rankings.append(('dense:'+str(number), rows, 1.0))
            rankings.append(('lexical:'+str(number), self.lexical(query, requested), .35))
        candidates = fuse(rankings)
        dense_ms = (time.monotonic() - start) * 1000
        rerank_ms = 0.0
        if rerank:
            if len(requested) > 1:
                buckets=[[r for r in candidates if r['chunk']['source_revision']==pid] for pid in requested]
                shortlist=[]
                for depth in range(max(map(len,buckets),default=0)):
                    for bucket in buckets:
                        if depth<len(bucket) and len(shortlist)<20:shortlist.append(bucket[depth])
                    if len(shortlist)==20:break
            else:
                shortlist = candidates[:20]
            url = os.getenv('EMBED_URL', 'http://127.0.0.1:8765').rstrip('/')
            health = http_json(url + '/v1/reranker/health')
            then = time.monotonic()
            result = http_json(url + '/v1/rerank', {'query': question,
                'expected_model_fingerprint': health['fingerprint'],
                'candidates': [{'id': r['chunk']['id'], 'text': r['chunk']['text']} for r in shortlist]})
            scores = {r['id']: r['score'] for r in result['outputs']}
            candidates = [{**r, 'rerank_score': scores[r['chunk']['id']]} for r in shortlist]
            candidates.sort(key=lambda r: -r['rerank_score'])
            rerank_ms = (time.monotonic() - then) * 1000
        selected = []
        top_k = self.config.get('top_k', 4)
        per_paper = math.ceil(top_k / len(requested)) if requested else top_k
        ordered=candidates
        if len(requested)>1:
            buckets=[[r for r in candidates if r['chunk']['source_revision']==pid] for pid in requested]
            ordered=[bucket[depth] for depth in range(max(map(len,buckets),default=0))
                     for bucket in buckets if depth<len(bucket)]
        for row in ordered:
            c = row['chunk']
            if len(selected) >= top_k:break
            if sum(r['chunk']['source'] == c['source'] for r in selected) >= per_paper:continue
            expanded = self.expand(row)
            span = expanded['chunk']
            overlap = any(span['source'] == r['chunk']['source'] and
                max(0, min(span['end'], r['chunk']['end'])-max(span['start'], r['chunk']['start'])) /
                max(1, min(span['end']-span['start'], r['chunk']['end']-r['chunk']['start'])) > .7 for r in selected)
            if not overlap:selected.append(expanded)
        return {'evidence': selected, 'candidates': candidates, 'index_generation': self.index.manifest['generation'],
                'embedding_fingerprint': self.index.manifest['fingerprint'], 'retrieval_config': self.config,
                'retrieval_query': question, 'retrieval_queries': list(dict.fromkeys(queries)),
                'dense_ms': dense_ms, 'rerank_ms': rerank_ms, 'fusion': 'weighted reciprocal rank fusion'}
