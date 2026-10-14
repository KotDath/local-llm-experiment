"""Measure dev score diagnostics; retrieval ranks and grounded generation decides abstention."""
import hashlib
import json
from pathlib import Path
from common import append_jsonl
from rag import RAG

ROOT = Path(__file__).parent


def choose(samples):
    values = sorted(set(s['score'] for s in samples))
    # Midpoints avoid a threshold exactly on a floating-point dev score.
    cutoffs = [values[0] - 1, values[-1] + 1] + [(a + b) / 2 for a, b in zip(values, values[1:])]
    ranked = []
    for cutoff in cutoffs:
        tp = sum(s['answerable'] and s['score'] >= cutoff for s in samples)
        fp = sum(not s['answerable'] and s['score'] >= cutoff for s in samples)
        fn = sum(s['answerable'] and s['score'] < cutoff for s in samples)
        f1 = 2 * tp / max(1, 2 * tp + fp + fn)
        ranked.append((f1, -fp, cutoff, tp, fp, fn))
    winner = max(ranked)
    return {'threshold': winner[2], 'f1': winner[0], 'tp': winner[3], 'fp': winner[4], 'fn': winner[5]}


def main():
    data = (ROOT / 'eval/dev_questions.jsonl').read_bytes()
    questions = [json.loads(line) for line in data.splitlines()]
    rag = RAG()
    rag.config = {'dense_threshold': -1, 'rerank_threshold': -1e5, 'topic_prefix': True, 'top_k': 12, 'candidate_k': 20}
    samples = {'dense': [], 'rerank': []}
    for question in questions:
        result = rag.retrieve(question['question'], True)
        record = {'id': question['id'], 'question': question['question'], 'answerable': question['answerable'], **result}
        append_jsonl(ROOT / 'results/dev_retrieval.jsonl', record)
        samples['dense'].append({'id': question['id'], 'score': max(c['dense_score'] for c in result['candidates']), 'answerable': question['answerable']})
        samples['rerank'].append({'id': question['id'], 'score': max(c['rerank_score'] for c in result['candidates']), 'answerable': question['answerable']})
        print(question['id'], samples['dense'][-1]['score'], samples['rerank'][-1]['score'], flush=True)
    dense, rerank = choose(samples['dense']), choose(samples['rerank'])
    config = {'dense_threshold': -1, 'dense_question_threshold': -1, 'rerank_threshold': -1e5,
              'topic_prefix': True, 'top_k': 12, 'candidate_k': 20,
              'dev_sha256': hashlib.sha256(data).hexdigest(), 'method': 'rank_only_with_grounded_generation_abstention_v2',
              'cutoff_policy': 'Cosine/cross-encoder scores rank passages; they do not prove that a question is answerable. Dev classifier cutoffs below are diagnostics, not production rejection.',
              'diagnostic_dense_dev_metrics': dense, 'diagnostic_rerank_dev_metrics': rerank,
              'index_generation': rag.index.manifest['generation'], 'samples': samples}
    (ROOT / 'configs').mkdir(exist_ok=True)
    (ROOT / 'configs/retrieval.json').write_text(json.dumps(config, ensure_ascii=False, indent=2))
    print(json.dumps(config, ensure_ascii=False))


if __name__ == '__main__':
    main()
