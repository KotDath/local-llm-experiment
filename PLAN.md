# План повторной проверки дней 26–30

Источник требований: `/home/kotdath/omp/personal/ai/tasks.md`.
Пять самостоятельных версий одной системы. Текущая правка использует настоящий
RAG по статьям challenge и увеличивает context/output в четыре раза.

1. **26:** запустить Tiel Coder на ПК, сохранить три ответа разной сложности.
2. **27:** отдельный собственный Agent поверх raw HTTP Chat API; проверить
   CLI/JSONL, историю/reset/isolation и Telegram adapter на ПК.
3. **28:** переиспользовать оригинальный трёхстатейный индекс недели 6;
   проверить PDF/hash/pages/UTF-16, local embeddings/search/rerank, цитаты,
   rebuild, локальное и облачное сравнение, качество/скорость/повторы.
   Веб-проверка arXiv включается отдельно.
4. **29:** baseline 65536/8192 и optimized 32768/6144, temperature 1/0.1,
   task prompt; Q8/Q4 одной закреплённой ревизии. Одинаковые 10 вопросов × 2
   в четырёх условиях, один слот, настоящий warmup, отключённый prompt cache,
   actual context assertion, raw usage/time/resources/errors. Независимые
   оценки по SHA ответов, автоматическая таблица и выбор по измерениям.
5. **30:** inference на ПК; VPS — HTTPS gateway и внутренний reverse SSH; клиенту SSH не нужен. Реальный HTTP chat,
   follow-up/reset с VPS, 5/10 concurrent requests, rate429/recovery,
   новая context boundary, body/auth/errors/overflow и восстановление.
   Выбранные profile/quant/context должны совпадать с runtime.

Подробные планы: [26](day26-local-llm/PLAN.md), [27](day27-application/PLAN.md),
[28](day28-local-rag/PLAN.md), [29](day29-optimization/PLAN.md), [30](day30-private-service/PLAN.md).

## Закреплённые материалы

- MemGPT 2310.08560v2: 13 страниц PDF.
- MemoryBank 2305.10250v3: 11 страниц PDF.
- Generative Agents 2304.03442v2: 22 страницы PDF.
- Индекс недели 6 / дня25: 182 чанка, 1024D; generation
  `29297553d6b1cd8636c4024a587544c8320b17bcfb0582d35216f54703e203eb`.
- Полные PDF, канонические тексты и проверенные hashes в каждой RAG-версии.
- Q8/Q4 snapshot `3afc5222473fc08c6130b2771ebd819fa0c4b484`;
  SHA и metadata в `configs/models.json`, `results/model_pair_metadata.json`.

Контрольный набор известен заранее. Предварительные ошибки и прерванные
прогоны сохранены отдельно; ожидаемые факты и рубрика не передаются Agent
или retrieval. Финальная матрица использует одну зафиксированную версию кода
и данных. Самопроверка модели не гарантирует полноту и поддержку цитат.

Поставка: исходники, инструкции, фактические выводы и сценарии видео.
Видео записывается отдельно пользователем. Статус: [ACCEPTANCE.md](ACCEPTANCE.md).
