# Демонстрация дня 28

Ориентир общего видео: 2:00–4:00; увеличить длительность по фактическим ответам.

```bash
.venv/bin/python index.py check
.venv/bin/python cli.py ask 'Как MemGPT организует основную и внешнюю память?' --rag --json
.venv/bin/python cli.py ask 'Как MemoryBank ищет релевантные воспоминания?' --rag --rerank --json
.venv/bin/python cli.py chat --rag
.venv/bin/python verify.py
```

Показать 182 чанка оригинального индекса недели 6, три полных PDF и provenance.
В JSON показать retrieved scores, переданный контекст, все вызовы Agent, ответ,
название/версию/страницы и точную цитату. Для follow-up спросить: «Чем это
отличается от механизма забывания в MemoryBank?»; после /reset — независимый вопрос.
Контрольный неизвестный факт: «Какой измеренный p95 MemGPT на Galaxy A54?».

Показать отдельные результаты M0/M1/M2 и DeepSeek, включая partial и ошибки;
наличие буквальной цитаты не доказывает поддержку утверждения. BGE score —
результат настоящего локального reranker. Web выключен по умолчанию; verify.py
проверяет pinned PDF hashes и latest arXiv version. Не выдавать это за проверку
истинности всех научных утверждений. Cloud comparison — явный отдельный запуск.

Не показывать .env, ключи, headers и Telegram IDs. Не выдавать сохранённый
benchmark за живой ответ; назвать дату и условия измерений.
