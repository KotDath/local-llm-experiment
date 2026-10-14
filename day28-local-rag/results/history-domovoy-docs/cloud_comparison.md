# Реальное сравнение RAG и cloud

| Вариант | Полностью приемлемые /10 | Галлюцинации /10 | Ошибки delivery | Mean total ms |
|---|---:|---:|---:|---:|
| M0 | 2 | 7 | 0 | 16090.7 |
| M1 | 9 | 0 | 0 | 24425.4 |
| M2 | 6 | 0 | 0 | 13735.1 |
| cloud | 7 | 2 | 2 | 2389.1 |

M0: локальный агент без RAG; M1: dense RAG; M2: dense+BGE; cloud: direct HTTP `deepseek-flash` с локальным M1 context.

Одинаковые 10 вопросов, публичный frozen corpus, temperature 0.1, max output 1536. Local generation использует constrained quote decoding; cloud JSON output не имеет того же backend grammar. Это end-to-end сравнение приложений, не чистое ранжирование возможностей моделей.

Замеры времени реальны, но часть evaluation совпала с background overflow workload. Не делать причинных выводов о speedup из этой таблицы; отдельный день 29 измеряется в изолированном one-slot режиме.

M1 выбран основным retrieval: 9/10 полностью приемлемых, без найденных factual hallucinations. Q03 неполон (пропущен предел 12000 символов). BGE отбрасывает полезные источники Q02/Q04 и не улучшает итог в этом опыте.

У cloud две ошибки буквальной цитаты (переводы строк изменены); raw output сохранён и отдельно оценён, но недоставленный ответ не считается correct. Две строки содержат unsupported claims: Q02 смешивает confirmed/active, Q04 смешивает editing/removal. Из них одна была доставлена, другая отвергнута validator. Hallucination count таблицы включает raw rejected answers.

Literal citation validity не доказывает поддержку claim. Независимые grades содержат причины по каждому вопросу. Frozen golden уже известен из предыдущего проекта, это не held-out обобщение.
