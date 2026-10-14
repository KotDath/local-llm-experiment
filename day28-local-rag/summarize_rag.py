"""Export real paper-RAG runs and independent grades; never infer semantic grades."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).parent


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def import_m1(benchmark_path):
    records = read_rows(benchmark_path)
    b = [row for row in records if row['case'] == 'B']
    run = b[-1]['run_id']
    b = [row for row in b if row['run_id'] == run]
    assert len(b) == 20 and all(row['parallel'] == 1 for row in b)
    core = hashlib.sha256(b''.join((ROOT/name).read_bytes() for name in
                                   ['agent.py', 'rag.py', 'model.py', 'grounding.py', 'index.py'])).hexdigest()
    questions_hash = hashlib.sha256((ROOT/'eval/golden_questions.jsonl').read_bytes()).hexdigest()
    assert all(row['source_sha256'] == core and row['questions_sha256'] == questions_hash for row in b)
    selected = [row | {'mode': 'M1', 'reuse_policy': 'day29 B repeat0: identical Q8 optimized Agent, corpus, questions and one-slot backend; no additional inference'}
                for row in b if row['repeat'] == 0]
    assert len(selected) == 10 and len({row['id'] for row in selected}) == 10
    path = ROOT/'results/golden_rag_answers.jsonl'
    original = read_rows(path)
    retained = [row for row in original if row['mode'] != 'M1']
    assert len(retained) == 20 and {row['source_sha256'] for row in retained} == {core}
    path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in retained+selected))
    print('Imported ten genuine M1 answers from', run)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--import-b', type=Path, help='Path to a completed day29 benchmark_raw.jsonl')
    parser.add_argument('--import-only', action='store_true')
    args = parser.parse_args()
    if args.import_b:
        import_m1(args.import_b)
    if args.import_only:
        return
    local = read_rows(ROOT/'results/golden_rag_answers.jsonl')
    cloud = read_rows(ROOT/'results/cloud_answers.jsonl')
    grades = json.loads((ROOT/'results/golden_grades_independent.json').read_text())['grades']
    grades += json.loads((ROOT/'results/cloud_grades_independent.json').read_text())['grades']
    by_answer = {(row['mode'], row['id'], row['answer_sha256']): row for row in grades}
    expected_questions = {row['id']:row['question'] for row in read_rows(ROOT/'eval/golden_questions.jsonl')}
    core = hashlib.sha256(b''.join((ROOT/name).read_bytes() for name in
        ['agent.py', 'rag.py', 'model.py', 'grounding.py', 'index.py'])).hexdigest()
    assert all(row['source_sha256'] == core and row['question'] == expected_questions[row['id']] for row in local+cloud)
    rows, summary = [], {}
    for mode in ['M0', 'M1', 'M2', 'cloud']:
        group = [row for row in local+cloud if row['mode'] == mode]
        assert len(group) == 10 and len({row['id'] for row in group}) == 10, 'Incomplete or duplicate final mode'
        for row in group:
            digest = hashlib.sha256(row.get('text', '').encode()).hexdigest()
            grade = by_answer[(mode, row['id'], digest)]
            rows.append({'mode': mode, 'id': row['id'], 'ok': row['ok'], 'status': row.get('status', row.get('error')),
                         'verdict': grade['verdict'], 'correct': grade['correctness'], 'hallucination': grade['hallucination'],
                         'total_ms': row['total_ms'], 'llm_calls': len(row.get('llm_calls', [])),
                         'output_tokens': row.get('usage', {}).get('completion_tokens'), 'answer_sha256': digest})
        measured = [row for row in rows if row['mode'] == mode]
        summary[mode] = {'correct_out_of_10': sum(row['correct'] for row in measured),
                         'hallucinations_out_of_10': sum(row['hallucination'] for row in measured),
                         'delivery_failures': sum(not row['ok'] for row in measured),
                         'mean_total_ms': statistics.mean(row['total_ms'] for row in measured),
                         'mean_llm_calls': statistics.mean(row['llm_calls'] for row in measured)}
    with (ROOT/'results/rag_comparison.csv').open('w') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    (ROOT/'results/rag_comparison_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    lines = ['# Локальные и облачные ответы по трём статьям', '',
             '| Метрика | M0 Tiel без RAG | M1 Tiel dense | M2 Tiel + BGE | DeepSeek dense |',
             '|---|---:|---:|---:|---:|']
    for field, label in [('correct_out_of_10', 'Полностью correct /10'), ('hallucinations_out_of_10', 'Фактические галлюцинации /10'),
                         ('delivery_failures', 'Ошибки доставки /10'), ('mean_total_ms', 'Среднее полное время, ms'),
                         ('mean_llm_calls', 'Среднее число LLM calls')]:
        lines.append('| '+label+' | '+' | '.join(f'{summary[mode][field]:.2f}' if isinstance(summary[mode][field], float)
                                                else str(summary[mode][field]) for mode in summary)+' |')
    lines += ['', 'Все 10 вопросов одинаковы; новые независимые grades связаны с SHA ответов. Partial не correct. '
              'Для M0 отсутствие цитат не считается галлюцинацией; для RAG отдельно проверяется их смысловая поддержка.', '',
              'M1 использует B/repeat0 контролируемой матрицы дня29. Второй проход B оценивает стабильность. '
              'M0/M2 и B запускались последовательно в разные моменты; возможный временной confound не исключён.', '',
              'В DeepSeek используется тот же собственный Agent и локальный dense retrieval. JSON mode провайдера '
              'отличается от локального schema decoder; токенизаторы и provider context различаются. '
              'Tiel template — только общий reference budget, usage облака берётся из API. '
              'Cloud wall time включает HTTP, очередь и prefill: отдельная backend tokens/s не выдумывается.', '',
              'Самопроверка оценивает первый draft и может ошибаться; после одной revision повторной semantic review нет. '
              'Оценка отражает этот известный контрольный набор, не качество на неизвестных вопросах.', '']
    (ROOT/'results/cloud_comparison.md').write_text('\n'.join(lines))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
