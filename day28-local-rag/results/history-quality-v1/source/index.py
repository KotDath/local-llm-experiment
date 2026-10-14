"""Import Week 6 JSONL and rebuild token-aware indexes. No vector DB/framework."""
import argparse
from bisect import bisect_right
import hashlib
import json
import math
import os
from pathlib import Path
import numpy as np
from common import ServiceError, http_json

ROOT = Path(__file__).resolve().parent


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def utf16_slice(text, start, end):
    return text.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le')


class Embeddings:
    def __init__(self):
        self.url = os.getenv('EMBED_URL', 'http://127.0.0.1:8765').rstrip('/')

    def health(self):
        return http_json(self.url + '/health')

    def encode(self, texts, fingerprint, query=False):
        result = http_json(self.url + '/v1/embeddings', {
            'expected_model_fingerprint': fingerprint,
            'inputs': [{'id': str(i), 'text': text, 'kind': 'query' if query else 'passage'}
                       for i, text in enumerate(texts)],
        })
        if result['fingerprint'] != fingerprint or result['dimension'] != 1024 or result['truncated']:
            raise ServiceError('embedding_drift', 409)
        return [row['vector'] for row in result['outputs']]

    def offsets(self, text):
        return http_json(self.url + '/v1/tokenize', {'text': text, 'kind': 'embedding'})['offsets']


class Index:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('INDEX_PATH', ROOT / 'data/week6/fixed.jsonl'))
        lines = self.path.read_bytes().splitlines(keepends=True)
        if len(lines) < 3:
            raise ValueError('incomplete_index')
        footer = json.loads(lines[-1])
        if footer.get('type') != 'end' or footer.get('hash') != hashlib.sha256(b''.join(lines[:-1])).hexdigest():
            raise ValueError('index_footer_mismatch')
        records = [json.loads(line) for line in lines[:-1]]
        self.manifest = records[0]
        if self.manifest.get('type') != 'manifest' or self.manifest.get('dimension') != 1024:
            raise ValueError('index_manifest_invalid')
        self.documents = [row['data'] for row in records if row.get('type') == 'document']
        corpus_manifest = ROOT / 'data/corpus/manifest.json'
        assets = {e['source']: e for e in json.loads(corpus_manifest.read_text())} if corpus_manifest.exists() else {}
        documents = {d['source']: d for d in self.documents}
        if len(documents) != len(self.documents):
            raise ValueError('duplicate_documents')
        for document in self.documents:
            if sha(document['text']) != document['revision']:
                raise ValueError('document_hash_mismatch')
        self.chunks, vectors = [], []
        ids = set()
        for row in records:
            if row.get('type') != 'chunk':
                continue
            chunk = row['data']
            doc = documents[chunk['source']]
            if chunk['id'] in ids or chunk['revision'] != doc['revision']:
                raise ValueError('invalid_chunk_identity')
            if utf16_slice(doc['text'], chunk['start'], chunk['end']) != chunk['text']:
                raise ValueError('chunk_utf16_span_mismatch')
            starts = doc.get('page_starts', [])
            if starts:
                if chunk.get('page_start') != bisect_right(starts, chunk['start']) or chunk.get('page_end') != bisect_right(starts, chunk['end'] - 1):
                    raise ValueError('chunk_pdf_page_mismatch')
            # Read-only enrichment: original Week6 generation/vectors/IDs stay intact.
            chunk['page_starts'] = starts
            chunk['source_revision'] = doc.get('source_revision')
            asset = assets.get(chunk['source'], {})
            if asset and asset['sha256'] != doc['revision']:
                raise ValueError('corpus_index_revision_mismatch')
            chunk['pdf_file'] = asset.get('pdf_file')
            chunk['pdf_sha256'] = asset.get('pdf_sha256')
            vector = row['vector']
            norm = math.sqrt(sum(x * x for x in vector))
            if len(vector) != 1024 or not all(math.isfinite(x) for x in vector) or abs(norm - 1) > 1e-5:
                raise ValueError('invalid_vector')
            ids.add(chunk['id'])
            self.chunks.append(chunk)
            vectors.append(vector)
        if len(self.chunks) != self.manifest['count']:
            raise ValueError('index_count_mismatch')
        self.matrix = np.asarray(vectors, dtype=np.float64)

    def search(self, question, limit=20):
        embedding = Embeddings()
        if embedding.health()['fingerprint'] != self.manifest['fingerprint']:
            raise ServiceError('embedding_drift_rebuild_required', 409)
        vector = embedding.encode([question], self.manifest['fingerprint'], query=True)[0]
        scores = self.matrix @ np.asarray(vector)
        order = np.argsort(-scores, kind='stable')[:limit]
        return [{'chunk': self.chunks[i], 'dense_score': float(scores[i])} for i in order]


def rebuild(output):
    embedding = Embeddings()
    fingerprint = embedding.health()['fingerprint']
    corpus = ROOT / 'data/corpus'
    manifest = json.loads((corpus / 'manifest.json').read_text())
    documents, chunks, vectors = [], [], []
    for entry in manifest:
        source = entry['source']
        text = (corpus / entry['asset']).read_text()
        if sha(text) != entry['sha256']:
            raise ValueError('corpus_manifest_mismatch')
        revision = sha(text)
        doc = {'source': source, 'title': entry['title'], 'text': text, 'revision': revision,
               'source_revision': entry['revision'], 'page_starts': entry['page_starts'],
               'pdf_ref': entry['pdf_ref'], 'pdf_size': entry['pdf_size']}
        if hashlib.sha256((ROOT / entry['pdf_file']).read_bytes()).hexdigest() != entry['pdf_sha256']:
            raise ValueError('original_pdf_hash_mismatch')
        documents.append(doc)
        offsets = embedding.offsets(text)
        for ordinal, start_token in enumerate(range(0, len(offsets), 320)):
            end_token = min(start_token + 384, len(offsets))
            start = offsets[start_token][0]
            end = offsets[end_token - 1][1]
            if end <= start:
                continue
            passage = text[start:end]
            chunk = {
                'id': sha(source + ':' + revision + ':' + str(start_token)),
                'document': sha(source), 'revision': revision, 'source': source, 'title': entry['title'],
                'section': entry['title'], 'start': len(text[:start].encode('utf-16-le')) // 2,
                'end': len(text[:end].encode('utf-16-le')) // 2, 'text': passage,
                'tokens': end_token - start_token, 'strategy': 'fixed', 'ordinal': ordinal,
                'config': 'python-articles-fixed-384-64-v1',
                'page_start': bisect_right(doc['page_starts'], len(text[:start].encode('utf-16-le')) // 2),
                'page_end': bisect_right(doc['page_starts'], len(text[:end].encode('utf-16-le')) // 2 - 1),
                'forced_split': False,
            }
            chunks.append(chunk)
            if end_token == len(offsets):
                break
    for start in range(0, len(chunks), 8):
        vectors.extend(embedding.encode([c['text'] for c in chunks[start:start + 8]], fingerprint))
    generation = sha(json.dumps({'documents': [d['revision'] for d in documents],
                                  'chunks': [c['id'] for c in chunks], 'fingerprint': fingerprint}, sort_keys=True))
    header = {'type': 'manifest', 'fingerprint': fingerprint, 'dimension': 1024,
              'strategy': 'fixed', 'generation': generation, 'count': len(chunks), 'elapsed_ms': None}
    records = [header] + [{'type': 'document', 'data': d} for d in documents]
    records += [{'type': 'chunk', 'data': c, 'vector': v} for c, v in zip(chunks, vectors)]
    payload = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records).encode()
    payload += (json.dumps({'type': 'end', 'version': 1, 'hash': hashlib.sha256(payload).hexdigest()}) + '\n').encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.tmp')
    temp.write_bytes(payload)
    Index(temp)
    temp.replace(output)
    return header


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['check', 'search', 'rebuild'])
    p.add_argument('question', nargs='?')
    p.add_argument('--output', default=str(ROOT / 'data/index/rebuilt.jsonl'))
    args = p.parse_args()
    if args.command == 'rebuild':
        result = rebuild(args.output)
    else:
        index = Index()
        result = index.manifest if args.command == 'check' else index.search(args.question)
    print(json.dumps(result, ensure_ascii=False))
