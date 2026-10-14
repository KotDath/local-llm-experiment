"""Join independent semantic grades with measured data and publish comparison."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).parent


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values)-1, max(0, math.ceil(len(values)*p)-1))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison-mode', choices=['fixed-context', 'end-to-end'], default='fixed-context',
                        help='Fixed context asserts identical answer inputs; end-to-end records planner/context drift.')
    args = parser.parse_args()
    records = [json.loads(line) for line in (ROOT / 'results/benchmark_raw.jsonl').read_text().splitlines()]
    grade_rows = []
    for case in 'ABCD':
        document = json.loads((ROOT / ('results/benchmark_grades_' + case + '_independent.json')).read_text())
        grade_rows.extend(document['grades'])
    grades = {(g['run_id'], g['id'], g['repeat']): g for g in grade_rows}
    latest = {case: next(r['run_id'] for r in reversed(records) if r['case'] == case) for case in 'ABCD'}
    records = [r for r in records if r['run_id'] == latest[r['case']]]
    assert len(records) == 80, 'Incomplete final matrix'
    assert len({r['questions_sha256'] for r in records}) == 1
    assert len({r['source_sha256'] for r in records}) == 1, 'Agent implementation changed between conditions'
    assert len({r['index_generation'] for r in records}) == 1, 'Index changed between conditions'
    assert len({r['embedding_fingerprint'] for r in records}) == 1
    assert len({json.dumps(r['retrieval_config'], sort_keys=True) for r in records}) == 1
    assert len({r['model_build'] for r in records}) == 1
    assert all(r['parallel'] == 1 and not r['rerank'] for r in records)
    assert all(call.get('timings', {}).get('cache_n', 0) == 0
               for r in records for call in r.get('llm_calls', [])), 'Unexpected prompt cache hit'
    pair = json.loads((ROOT / 'results/model_pair_metadata.json').read_text())
    expected = json.loads((ROOT / 'configs/models.json').read_text())
    assert pair['passed'] and pair['snapshot'] == expected['snapshot']
    for record in records:
        model = pair['models'][record['quant']]
        assert model['actual_sha256'] == expected[record['quant']]['sha256']
        assert record['model_file'] == model['file'] and record['model_bytes'] == model['bytes']
    controls = {'comparison_mode': args.comparison_mode, 'source_sha256': records[0]['source_sha256'],
                'scope': 'Identical answer context' if args.comparison_mode == 'fixed-context' else
                         'End-to-end agent; quantization can change planning, retrieval, reviews and answers.', 'pairs': {}}
    for first, second in [('A', 'C'), ('B', 'D')]:
        left = [r for r in records if r['case'] == first]
        right = [r for r in records if r['case'] == second]
        assert [r['profile_settings'] for r in left] == [r['profile_settings'] for r in right]
        assert [(r['id'], r['repeat'], r['question']) for r in left] == [(r['id'], r['repeat'], r['question']) for r in right]
        checks = []
        for a, b in zip(left, right):
            def sent(record):
                return [(e['chunk']['id'], e['chunk']['text']) for e in record['evidence']]
            answer_a = next((c for c in a.get('llm_calls', []) if c.get('phase') == 'answer'), None)
            answer_b = next((c for c in b.get('llm_calls', []) if c.get('phase') == 'answer'), None)
            check = {'id': a['id'], 'repeat': a['repeat'], 'same_ordered_evidence': sent(a) == sent(b),
                     'same_evidence_set': {e['chunk']['id'] for e in a.get('evidence', [])} == {e['chunk']['id'] for e in b.get('evidence', [])},
                     'answer_call_both_present': answer_a is not None and answer_b is not None,
                     'same_answer_prompt': bool(answer_a and answer_b and answer_a['prompt_hash'] == answer_b['prompt_hash']),
                     'same_answer_prompt_tokens': bool(answer_a and answer_b and answer_a['counted_prompt_tokens'] == answer_b['counted_prompt_tokens']),
                     'question_plan_both_present': bool(a.get('question_plan') and b.get('question_plan')),
                     'same_question_plan': a.get('question_plan') == b.get('question_plan'),
                     'same_retrieval_queries': [p.get('search') for p in a.get('question_plan', [])] == [p.get('search') for p in b.get('question_plan', [])]}
            checks.append(check)
            if args.comparison_mode == 'fixed-context':
                assert check['same_ordered_evidence'], 'Different answer evidence; use explicit end-to-end mode for adaptive planner'
                if answer_a or answer_b:
                    assert check['same_answer_prompt'] and check['same_answer_prompt_tokens'], 'Different answer prompt; not a fixed-context quantization comparison'
            if a.get('llm_calls') and b.get('llm_calls'):
                assert a['llm_calls'][0]['prompt_hash'] == b['llm_calls'][0]['prompt_hash']
                assert a['llm_calls'][0]['counted_prompt_tokens'] == b['llm_calls'][0]['counted_prompt_tokens']
        controls['pairs'][first + second] = {'count': len(checks), 'rows': checks,
            'different_evidence': sum(not c['same_ordered_evidence'] for c in checks),
            'different_evidence_set': sum(not c['same_evidence_set'] for c in checks),
            'different_question_plan': sum(c['question_plan_both_present'] and not c['same_question_plan'] for c in checks),
            'different_retrieval_queries': sum(not c['same_retrieval_queries'] for c in checks),
            'missing_question_plan': sum(not c['question_plan_both_present'] for c in checks),
            'different_answer_prompt': sum(c['answer_call_both_present'] and not c['same_answer_prompt'] for c in checks),
            'missing_answer_call': sum(not c['answer_call_both_present'] for c in checks)}
    (ROOT / 'results/benchmark_controls.json').write_text(json.dumps(controls, ensure_ascii=False, indent=2) + '\n')
    rows, summaries = [], {}
    for record in records:
        grade = grades[(record['run_id'], record['id'], record['repeat'])]
        digest = hashlib.sha256(record.get('text', '').encode()).hexdigest()
        assert grade['answer_sha256'] == digest, 'Grade belongs to another actual answer'
        calls = record.get('llm_calls', [])
        tokens = sum(c.get('timings', {}).get('predicted_n', 0) for c in calls)
        milliseconds = sum(c.get('timings', {}).get('predicted_ms', 0) for c in calls)
        rows.append({key: record.get(key) for key in ['run_id', 'case', 'quant', 'profile_name', 'id', 'repeat', 'ok', 'status', 'total_ms']} |
                    {'verdict': grade['verdict'], 'correct': grade['correctness'], 'hallucination': grade['hallucination'],
                     'generation_tokens_s': tokens/milliseconds*1000 if milliseconds else None,
                     'llm_calls': len(calls), 'output_tokens': record.get('usage', {}).get('completion_tokens'),
                     'truncated': any(c.get('finish_reason') == 'length' for c in calls)} | record['resource_peak'])
    with (ROOT / 'results/benchmark.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    for case in 'ABCD':
        group = [r for r in rows if r['case'] == case]
        primary = [r for r in group if r['repeat'] == 0]
        repeated = [r for r in group if r['repeat'] == 1]
        assert len(primary) == 10 and len({r['id'] for r in primary}) == 10
        assert len(repeated) == 10 and len({r['id'] for r in repeated}) == 10
        first_verdicts = {r['id']: r['verdict'] for r in primary}
        summaries[case] = {'correct_out_of_10': sum(r['correct'] for r in primary),
                           'hallucinations_out_of_10': sum(r['hallucination'] for r in primary),
                           'repeat1_correct_out_of_10': sum(r['correct'] for r in repeated),
                           'repeat1_hallucinations_out_of_10': sum(r['hallucination'] for r in repeated),
                           'verdict_stable_out_of_10': sum(r['verdict'] == first_verdicts[r['id']] for r in repeated),
                           'mean_total_ms': statistics.mean(r['total_ms'] for r in group),
                           'p50_ms': statistics.median(r['total_ms'] for r in group),
                           'p95_ms': percentile([r['total_ms'] for r in group], .95),
                           'max_total_ms': max(r['total_ms'] for r in group),
                           'mean_generation_tokens_s': statistics.mean(r['generation_tokens_s'] for r in group if r['generation_tokens_s'] is not None),
                           'peak_rss_bytes': max(r['rss_bytes'] for r in group),
                           'peak_pss_bytes': max(r['pss_bytes'] for r in group),
                           'peak_host_used_bytes': max(r['host_used_bytes'] for r in group),
                           'peak_vram_bytes': max(r['vram_bytes'] for r in group if r['vram_bytes'] is not None),
                           'peak_gtt_bytes': max(r['gtt_bytes'] for r in group if r['gtt_bytes'] is not None),
                           'delivery_failures': sum(not r['ok'] for r in group),
                           'truncated_turns': sum(r['truncated'] for r in group),
                           'model_bytes': next(r['model_bytes'] for r in records if r['case'] == case),
                           'load_ms': next(r['load_ms'] for r in records if r['case'] == case)}
    (ROOT / 'results/benchmark_summary.json').write_text(json.dumps(summaries, ensure_ascii=False, indent=2))
    lines = ['# Сравнение настроек и квантований', '',
             f"Измеренный core SHA: `{records[0]['source_sha256']}`; режим `{args.comparison_mode}`.",
             'Эта таблица относится к указанным actual runs; текущие исходники могут иметь другой SHA.', '',
             '| Метрика | A baseline Q8 | B optimized Q8 | C baseline Q4 | D optimized Q4 |',
             '|---|---:|---:|---:|---:|']
    for field, label in [('correct_out_of_10', 'Correct из 10 (repeat 0)'), ('hallucinations_out_of_10', 'Галлюцинации из 10'),
                         ('repeat1_correct_out_of_10', 'Correct из 10 (repeat 1)'),
                         ('repeat1_hallucinations_out_of_10', 'Галлюцинации из 10 (repeat 1)'),
                         ('verdict_stable_out_of_10', 'Одинаковый verdict в двух повторах /10'),
                         ('mean_total_ms', 'Mean total ms (20 turns)'), ('p95_ms', 'p95 ms (20 turns)'),
                         ('max_total_ms', 'Max total ms (20 turns)'),
                         ('delivery_failures', 'Delivery failures /20'), ('truncated_turns', 'Turns with truncated generation /20'),
                         ('mean_generation_tokens_s', 'Generation tokens/s'), ('peak_rss_bytes', 'Sampled peak RSS bytes'),
                         ('peak_pss_bytes', 'Sampled peak PSS bytes'), ('peak_host_used_bytes', 'Sampled whole-host used RAM bytes'),
                         ('peak_vram_bytes', 'Sampled global GPU VRAM bytes'), ('peak_gtt_bytes', 'Sampled global GPU GTT bytes'),
                         ('model_bytes', 'Размер GGUF bytes'), ('load_ms', 'Model launch/readiness ms')]:
        values = [summaries[c][field] for c in 'ABCD']
        lines.append('| '+label+' | '+' | '.join(f'{v:.2f}' if isinstance(v,float) else str(v) for v in values)+' |')
    comparison_scope = ('A/C и B/D меняют квантование одного snapshot при одинаковом answer prompt/контексте.'
                        if args.comparison_mode == 'fixed-context' else
                        'A/C и B/D меняют квантование одного snapshot в полном Agent: planner/retrieval/review могут дать другой контекст. Drift записан в benchmark_controls.json; это не fixed-context тест одного generation call.')
    lines += ['', 'Настройки A/B сравнивают bundle temperature/output/context/prompt, не отдельную причину каждого изменения. ' + comparison_scope, '',
              '10 одинаковых вопросов ×2, один server slot, excluded warmup, seed42, cache_prompt:false. Известный frozen corpus/evaluation; ожидания не входят в prompt. Independent grades связаны с actual answer SHA.', '',
              'Host abstention учитывается в total time, generation rate=N/A. Repairs включены в cost и отдельный call count. Частичный ответ не correct. Все failures/truncations сохранены.', '',
              'cache_prompt:false отключает prompt/KV reuse между измеряемыми запросами, не OS file cache. Launch/readiness — фактическое отдельное наблюдение, без заявления о сопоставимом холодном дисковом старте.', '',
              'Strix Halo использует shared memory. RSS/PSS/host memory/VRAM/GTT не складываются. Sampling ~200 ms: аппаратный абсолютный максимум не заявляется. Backend, slot и configuration контролировались; host/GPU счётчики включают фоновую нагрузку системы. p95 из 20 небольших samples не является production SLA.', '']
    selected_path = ROOT / 'configs/selected.json'
    if selected_path.exists():
        selected = json.loads(selected_path.read_text())
        if (selected.get('run_ids') == latest
                and selected.get('source_sha256') == records[0]['source_sha256']
                and selected.get('questions_sha256') == records[0]['questions_sha256']):
            case = selected['case']
            summary = summaries[case]
            correct = summary['correct_out_of_10'] + summary['repeat1_correct_out_of_10']
            hallucinations = summary['hallucinations_out_of_10'] + summary['repeat1_hallucinations_out_of_10']
            lines += [f"Выбрана {selected['quant']}/{case} {selected['profile']}: {correct}/20 correct, {hallucinations} найденных галлюцинаций и {summary['delivery_failures']} delivery failures в этом наборе. Основание: {selected.get('basis', '')}", '']
    (ROOT / 'results/comparison.md').write_text('\n'.join(lines))
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
