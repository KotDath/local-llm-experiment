# Выводы дня 29

Все четыре условия реально выполнены на одной версии Agent/RAG: 10 одинаковых вопросов ×2, один слот, excluded warmup, cache off. Новые 80 строк и независимые grades привязаны к точному answer SHA; ранние 40 строк сохранены и исключены из финальной таблицы. Полный SHA обеих GGUF проверен; architecture/tokenizer/template/753 tensor shapes совпали, quant types различаются.

| Метрика | A Q8 baseline | B Q8 optimized | C Q4 baseline | D Q4 optimized |
|---|---:|---:|---:|---:|
| Содержательно корректные, проход 0 /10 | 7 | 8 | 7 | 7 |
| Содержательно корректные, проход 1 /10 | 6 | 8 | 7 | 6 |
| Галлюцинации, проход 0 /10 | 1 | 0 | 0 | 0 |
| Галлюцинации, проход 1 /10 | 2 | 0 | 0 | 1 |
| Среднее полное время, с | 17.81 | 15.89 | 12.52 | 15.89 |
| Скорость генерации, токенов/с | 41.83 | 42.31 | 54.03 | 52.75 |
| Sampled whole-host RAM, GiB | 77.10 | 72.77 | 58.83 | 58.20 |
| Sampled global GPU GTT, GiB | 43.70 | 43.53 | 28.47 | 28.32 |
| Ошибки доставки /20 | 0 | 0 | 0 | 1 |

Выбрана **B: Q8 optimized**, `configs/selected.json`: temperature 0.1, max output 1536, context 8192, optimized RAG prompt. Приоритет — полнота и надёжная доставка ответа: 16/20, найденных галлюцинаций 0, delivery failures 0. Остальные условия дают 13/20 (A), 14/20 (C), 13/20 (D). Это решение по известному небольшому набору, не универсальное превосходство Q8.

Bundle настроек A→B улучшил первый проход 7→8/10 и убрал найденные галлюцинации 1→0; среднее total 17.81→15.89 с. Отдельный причинный вклад temperature/output/context/prompt не выделен. Generation rate почти не изменился: 41.83→42.31 tokens/s.

Q4 даёт меньший файл и меньше global GTT, а backend generation быстрее. Но в optimized D это не улучшило mean end-to-end: 15.887 с против 15.890 с у B. В D0Q06 обе попытки завершились `finish_reason:length`, по 1536 tokens, итог — `invalid_grounded_answer`, total 65.94 с. Сохранены первичный ответ, repair, 3072 output tokens и sampled resources; failure включён в качество/latency. D1Q09 добавляет неподдержанное Android-утверждение. Эти недостатки делают B предпочтительным для итогового сервиса на данном ПК.

Вердикты B совпали в 8/10 пар повторов: одинаковый общий correct count не означает одинаковую полноту каждого ответа. Partial ответы и semantic citation deficiencies перечислены в independent grades. Literal ID/quote checks не заменяют semantic entailment.

Условия A/C и B/D меняют только квантование: exporter подтвердил одинаковые settings, вопросы, sent chunks, primary prompt hash/count, index/embedding/retrieval/build и actual cache hits 0.

RSS/PSS процесса, whole-host RAM и global GPU VRAM/GTT — разные показатели общей памяти Strix Halo. Они не складываются. Sampling ~200 ms не гарантирует аппаратный абсолютный максимум; background download/desktop могут влиять на global counters. Prompt cache off не отключает OS file cache; launch/readiness не сравнивается как строго холодный старт.

Источники: comparison.md (полная таблица), benchmark.csv (80 финальных строк), benchmark_raw.jsonl (включая исторические записи/ошибки), resource_samples.jsonl, benchmark_grades_A/B/C/D_independent.json, model_pair_metadata.json.
