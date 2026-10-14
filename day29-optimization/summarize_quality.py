"""Join immutable actual answers with independent grades; never invoke a model."""
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_series(directory, stem, expected):
    answers_path = directory / (stem + '_answers.jsonl')
    grades_path = directory / (stem + '_grades_independent.json')
    answers = [json.loads(line) for line in answers_path.read_text().splitlines() if line.strip()]
    document = json.loads(grades_path.read_text())
    assert document.get('complete') is True, 'Independent grading is not complete'
    grades = {(g['repeat'], g['id']): g for g in document['grades']}
    keys = {(a['repeat'], a['id']) for a in answers}
    assert len(answers) == len(keys) == len(grades) == expected, 'Incomplete or duplicated series'
    assert keys == set(grades), 'Grades and actual answers differ'
    assert len({a['source_sha256'] for a in answers}) == 1, 'Implementation changed during series'
    assert len({a['questions_sha256'] for a in answers}) == 1, 'Questions changed during series'
    assert document['source_sha256'] == answers[0]['source_sha256']
    assert document['questions_sha256'] == answers[0]['questions_sha256']
    rows = []
    for answer in answers:
        grade = grades[(answer['repeat'], answer['id'])]
        assert grade['answer_sha256'] == sha(answer.get('text', '').encode()), 'Grade belongs to another answer'
        calls = answer.get('llm_calls', [])
        tokens = sum(c.get('timings', {}).get('predicted_n', 0) for c in calls)
        generation_ms = sum(c.get('timings', {}).get('predicted_ms', 0) for c in calls)
        rows.append({'series': stem, 'id': answer['id'], 'repeat': answer['repeat'],
                     'correct': grade['correctness'], 'hallucination': grade['hallucination'],
                     'verdict': grade['verdict'], 'delivery_ok': grade['delivery_ok'],
                     'total_ms': answer['total_ms'], 'focus_ms': answer.get('focus_ms', 0),
                     'llm_calls': len(calls), 'generation_tokens_s': tokens * 1000 / generation_ms if generation_ms else None,
                     'completion_tokens': answer.get('usage', {}).get('completion_tokens'),
                     'truncated': any(c.get('finish_reason') == 'length' for c in calls),
                     'source_sha256': answer['source_sha256'], 'answer_sha256': grade['answer_sha256']})
    summary = {'source_sha256': answers[0]['source_sha256'], 'questions_sha256': answers[0]['questions_sha256'],
               'answers_file_sha256': sha(answers_path.read_bytes()), 'grades_file_sha256': sha(grades_path.read_bytes()),
               'runtime_model': answers[0].get('runtime_model'),
               'count': expected, 'correct': sum(r['correct'] for r in rows),
               'hallucinations': sum(r['hallucination'] for r in rows),
               'delivery_failures': sum(not r['delivery_ok'] for r in rows),
               'truncated': sum(r['truncated'] for r in rows),
               'mean_total_ms': statistics.mean(r['total_ms'] for r in rows),
               'mean_focus_ms': statistics.mean(r['focus_ms'] for r in rows),
               'mean_generation_tokens_s': statistics.mean(r['generation_tokens_s'] for r in rows if r['generation_tokens_s'] is not None)}
    summary['meets_quality_target'] = summary['correct'] / expected >= .8 and summary['hallucinations'] == 0
    summary['by_repeat'] = {str(repeat): {'count': len(group), 'correct': sum(r['correct'] for r in group),
                                       'hallucinations': sum(r['hallucination'] for r in group)}
                            for repeat in sorted({r['repeat'] for r in rows})
                            for group in [[r for r in rows if r['repeat'] == repeat]]}
    first = {r['id']: r['verdict'] for r in rows if r['repeat'] == 0}
    summary['stable_verdicts'] = sum(r['verdict'] == first[r['id']] for r in rows if r['repeat'] == 1)
    return answers, rows, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=ROOT / 'results/quality-v2')
    parser.add_argument('--focus', action='store_true')
    args = parser.parse_args()
    base, rows, summary = read_series(args.directory, 'heldout', 40)
    summaries = {'heldout': summary}
    if args.focus:
        focused, focus_rows, focus_summary = read_series(args.directory, 'heldout_focus', 40)
        originals = {(a['repeat'], a['id']): a for a in base}
        for answer in focused:
            original = originals[(answer['repeat'], answer['id'])]
            assert answer['paired_input_answer_sha256'] == sha(original.get('text', '').encode())
            assert answer['generation_source_sha256'] == original['source_sha256']
            if original.get('claims'):
                assert answer['llm_calls'][:-1] == original['llm_calls'], 'Paired upstream calls changed'
                assert answer['llm_calls'][-1]['phase'] == 'answer_focus'
            else:
                assert answer['llm_calls'] == original['llm_calls'], 'Refusal without claims should not invoke focus'
        rows += focus_rows
        focus_summary['scope'] = 'Paired postprocessing of the same 40 actual outputs; one additional real focus call per answer with claims. No call for empty refusals. Not a fresh end-to-end repeat.'
        summaries['heldout_focus'] = focus_summary
    with (args.directory / 'quality.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (args.directory / 'quality_summary.json').write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Независимая проверка качества v2', '',
             '20 новых вопросов × два прохода; 16 вопросов по статьям и четыре без подтверждённого ответа.',
             'Correct включает обоснованный отказ. Частичные ответы и любые неподтверждённые дополнительные факты не correct.', '',
             '| Серия | Correct /40 | Неподтверждённые факты /40 | Ошибки доставки | Среднее время, с | Generation tokens/s |',
             '|---|---:|---:|---:|---:|---:|']
    for name, result in summaries.items():
        lines.append(f"| {name} | {result['correct']} | {result['hallucinations']} | {result['delivery_failures']} | {result['mean_total_ms']/1000:.2f} | {result['mean_generation_tokens_s']:.2f} |")
        lines += ['', f"{name}: source `{result['source_sha256']}`; по проходам: {result['by_repeat']}; одинаковый verdict в {result['stable_verdicts']}/20 парах.", '']
    lines += ['Для paired focus исходные генерации/время/usage повторно используются, добавляется фактическая стоимость фильтра. Это не независимый повтор полного агента.', '',
              'Скорость генерации относится к backend timings всех сохранённых calls; полное время включает retrieval/review/revision. Для focus сложены исходное и новое время, а не измерена новая задержка всего запроса.', '',
              'Прогон качества выполнялся на Q8/optimized, три слота по32768, с параллельными cloud/focus/HTTPS проверками. Эти наблюдения времени не являются сравнением скорости с прежней однопоточной матрицей. В этих прогонах память не измерялась. Исторические ресурсы/квантование относятся к core37e и отдельной контролируемой матрице; они не приписываются v2.', '',
              'Программа проверяет полноту series, source/question hashes, принадлежность независимых оценок actual answer SHA и неизменность исходных calls в paired эксперименте. Expected facts не поступают модели.', '']
    (args.directory / 'comparison.md').write_text('\n'.join(lines))
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
