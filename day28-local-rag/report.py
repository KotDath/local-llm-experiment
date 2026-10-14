"""Build CSV and Markdown from actual responses plus independent grades."""
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).parent


def main():
    raw = [json.loads(l) for l in (ROOT / 'results/golden_rag_answers.jsonl').read_text().splitlines()]
    raw += [json.loads(l) for l in (ROOT / 'results/cloud_answers.jsonl').read_text().splitlines()]
    grading = json.loads((ROOT / 'results/golden_grades_independent.json').read_text())
    cloud = json.loads((ROOT / 'results/cloud_grades_independent.json').read_text())
    grades = {(g['mode'], g['id']): g for g in grading['grades'] + cloud['grades']}
    rows = []
    for item in raw:
        grade = grades[(item['mode'], item['id'])]
        rows.append({'mode': item['mode'], 'id': item['id'], 'ok': item['ok'], 'total_ms': item['total_ms'],
                     'verdict': grade['verdict'], 'correct': grade['correctness'],
                     'hallucination': grade['hallucination'], 'delivered': grade['delivered'],
                     'literal_citation_valid': grade['literal_citation_valid']})
    with (ROOT / 'results/rag_comparison.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summaries = {**grading['summary'], **cloud['summary']}
    lines = ['# Реальное сравнение RAG и cloud', '',
             '| Вариант | Полностью приемлемые /10 | Галлюцинации /10 | Ошибки delivery | Mean total ms |',
             '|---|---:|---:|---:|---:|']
    for mode in ['M0', 'M1', 'M2', 'cloud']:
        s = summaries[mode];times = [r['total_ms'] for r in rows if r['mode'] == mode]
        lines.append(f"| {mode} | {s['acceptable_full_responses']} | {s['hallucination_responses']} | {s['delivery_failures']} | {statistics.mean(times):.1f} |")
    lines += ['', 'M0: локальный агент без RAG; M1: dense RAG; M2: dense+BGE; cloud: direct HTTP `deepseek-flash` с локальным M1 context.', '',
              'Одинаковые 10 вопросов, публичный frozen corpus, temperature 0.1, max output 1536. Local generation использует constrained quote decoding; cloud JSON output не имеет того же backend grammar. Это end-to-end сравнение приложений, не чистое ранжирование возможностей моделей.', '',
              'Замеры времени реальны, но часть evaluation совпала с background overflow workload. Не делать причинных выводов о speedup из этой таблицы; отдельный день 29 измеряется в изолированном one-slot режиме.', '',
              'M1 выбран основным retrieval: 9/10 полностью приемлемых, без найденных factual hallucinations. Q03 неполон (пропущен предел 12000 символов). BGE отбрасывает полезные источники Q02/Q04 и не улучшает итог в этом опыте.', '',
              'У cloud две ошибки буквальной цитаты (переводы строк изменены); raw output сохранён и отдельно оценён, но недоставленный ответ не считается correct. Две строки содержат unsupported claims: Q02 смешивает confirmed/active, Q04 смешивает editing/removal. Из них одна была доставлена, другая отвергнута validator. Hallucination count таблицы включает raw rejected answers.', '',
              'Literal citation validity не доказывает поддержку claim. Независимые grades содержат причины по каждому вопросу. Frozen golden уже известен из предыдущего проекта, это не held-out обобщение.']
    (ROOT / 'results/cloud_comparison.md').write_text('\n'.join(lines)+'\n')
    (ROOT / 'results/conclusions.md').write_text('''# Выводы дня 28

Реальный индекс недели 6 импортирован: 12 документов / 128 chunks / 1024D.
Fingerprint установленной Qwen embedding модели совпал. Footer/hash/vector/UTF-16
checks прошли. Fresh rebuild произведён, 128 chunks, индекс повторно открыт;
при смене generation старая retrieval calibration отклоняется.

Полностью локальная цепочка Agent → retrieval → Tiel Coder → grounded output
работает через CLI/JSONL без Telegram. BGE реально выполняет classifier inference,
raw logits проверяются отдельным gateway. Web off не вызывает GitHub/cloud;
tokenizers работают local_files_only. Web on проверил README на GitHub: текст
совпадает с frozen hash, timestamp и blob SHA сохранены в web_check.json.

По независимой оценке: M0 2/10, M1 9/10, M2 6/10 полностью приемлемых ответов.
M1/M2 — 0 найденных factual hallucinations, но частичные ответы и ложные отказы
есть. M1 выбран default; reranking опциональный, превосходство не заявляется.
Отдельные dev/early raw-query ошибки сохранены; topic vocabulary настроен на dev,
пороги midpoint исключают привязку к точному float boundary.

Cloud deepseek-flash реально выполнен через HTTP с ключом shell: 7/10 delivered
приемлемых, две literal validation failures. Найдены два unsupported claim ответа
(один доставлен, один отвергнут validator); они включены в hallucination count.
Подробное сравнение/ограничения
в cloud_comparison.md, sourceSHA и semantic reasons в independent reports.

Constrained schema не заменяет semantic entailment/completeness: dev показывает
частичные многоаспектные ответы. Все ошибки сохранены, их нельзя выдавать за
безошибочную систему. Тесты повреждённого footer, ложной quote/ID и UTF-16 прошли.
''')
    with (ROOT / 'results/conclusions.md').open('a') as stream:
        stream.write('\nПовторы Q02/Q03/Q10 сохранены в stability.json: correct/correct, correct/partial, appropriate_refusal/appropriate_refusal. Повторы заново выполнены после исправления истории на том же core SHA f1a41f303db90a8efbae7c593bca221e7b211391c28cd7ec61e617517132eabf. Два реальных повтора Q8optimized не гарантируют production reliability.\n')

    with (ROOT / 'results/conclusions.md').open('a') as stream:
        stream.write('\nЕстественный RAG dialogue проверен отдельно после исправления query resolution: исходные четыре вопроса дали 4/4 содержательно правильных ответа, шесть реальных локальных ChatAPI calls; небольшая языковая неточность turn3 сохранена. Два прежних неудачных прогона сохранены. История разрешает тему запроса, documentary evidence — только текущие документы. Stateless M0/M1/M2 данные выше получены до этого исправления; их input payload и retrieval при пустой history не изменились.\n')
        stream.write('\nStateless prompt validation сохранена в stateless_prompt_validation.json: все 10 вопросов/профилей/sent chunks совпали с новым B, primary prompt hash и token count совпали во всех девяти генерациях; Q10 — host refusal. Итоговый текст совпал только у Q10. Результаты M1 и B — разные реальные прогоны; полная битовая детерминированность и идентичность исторического server/sampler state не заявляются.\n')



if __name__ == '__main__':
    main()
