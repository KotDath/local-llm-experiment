# Локальный агент: дни 26–30

Пять самостоятельных версий: собственные исходники, README, PLAN, DEMO и результаты.
Улучшение качества RAG по полным научным статьям завершено: новый набор дал
36/40 correct, три ответа с неподтверждёнными фактами. [Отчёт и выводы](REPORT.md).
Предыдущая матрица завершена и сохранена отдельно; [ACCEPTANCE](ACCEPTANCE.md)
описывает её техническую приёмку; новый результат отдельно в [QUALITY](QUALITY.md).

| День | Содержание | Запуск |
|---|---|---|
| 26 | Tiel Coder, три запроса разной сложности | [README](day26-local-llm/README.md) |
| 27 | Собственный Agent, CLI/JSONL и Telegram | [README](day27-application/README.md) |
| 28 | RAG по MemGPT, MemoryBank, Generative Agents | [README](day28-local-rag/README.md) |
| 29 | Q8/Q4 × baseline/optimized | [README](day29-optimization/README.md) |
| 30 | Приватный HTTP chat на ПК через VPS-шлюз | [README](day30-private-service/README.md) |

Agent вызывает Chat Completions API напрямую через HTTP, без SDK, LangChain
или LlamaIndex. Local inference — Tiel Coder 35B-A3B через llama.cpp Vulkan.
Embeddings — Ollama qwen3-embedding:0.6b; optional rerank — локальный BGE.
Индекс недели 6: **три полные статьи, 182 чанка**, оригинальные PDF и страницы.
Исходная документация Domovoy больше не входит в действующую базу.

| Профиль | Общий context/slot | Максимальный ответ |
|---|---:|---:|
| baseline | 65536 | 8192 |
| optimized | 32768 | 6144 |

Output reserve входит в общий context budget. Это лимиты, не обещание, что
каждый ответ будет ровно в четыре раза длиннее. Генерация проверяет токены
настоящим backend template/tokenizer. Порог cosine не доказывает наличие ответа:
retrieval ранжирует, решение об отказе принимает модель по источникам.

Agent делит вопрос на необходимые части и переводит поисковые запросы для
английских статей. Retrieval объединяет dense-поиск и BM25 через weighted RRF;
соседние фрагменты дают контекст формулам и определениям. Модель выбирает
короткие ID цитат, а программа восстанавливает точные цитаты и координаты.
Модель проверяет полноту и поддержку утверждений, выполняет одну доработку
при замечаниях и проверяет её результат.
Все calls/tokens/time, ошибки и частичные ответы сохранены. Self-review также
может ошибаться; качество оценивается независимо по PDF и sent evidence.

На VPS Caddy HTTPS, stdlib gateway и внутренний reverse SSH; модели, индекс
и бот остаются на ПК. Клиенту SSH не нужен: **https://95.215.56.217/local-llm**.
Для чата: `python3 cli.py chat --env-file runtime/https_client.env` из дня 30;
этот закрытый файл создан deploy и содержит API_URL/API_TOKEN.
Cloud deepseek-flash доступен только явным отдельным сравнением публичных
статей. Web off по умолчанию. Telegram использует инфраструктуру Telegram;
полностью локальный интерфейс — CLI/JSONL/loopback HTTP.

Историческая оценка 80 ответов предыдущего core37e выбрала Q8/B: полностью правильны 5/20 против
3/20 baseline Q8; галлюцинаций 2/20 против 5/20. Ускорения не получилось:
54.75 → 56.29 s. [Измерения и ресурсы](day29-optimization/results/comparison.md).
RAG заметно уменьшил выдуманные факты, но полнота и смысловая поддержка цитат
остаются ограничениями; успешный HTTP ответ не означает правильный ответ.
Эти числа не измеряют текущий Agent: новые ответы и оценки хранятся в
`day28-local-rag/results/quality-v2/` с отдельными SHA исходников.

Старые результаты: `day28–30/results/history-domovoy-docs/`. Неудачные первые
прогоны статей также сохранены отдельно; они не смешиваются с финальной матрицей.
Поставка исключает закрытые .env/runtime/venv по [.gitignore](.gitignore);
оригинальные статьи находятся в data/papers, внешние GGUF остаются в MODEL_DIR.

[План](PLAN.md) · [Приёмка](ACCEPTANCE.md) · [Видеоинструкция](VIDEO.md).
