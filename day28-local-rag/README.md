# День 28: локальный RAG по научным статьям

> Обновление качества v2 завершено: основной вариант36/40 correct, три ответа с неподтверждёнными фактами. Текущий Agent использует hybrid RRF,
> контекст соседних чанков, обязательные части ответа и цитаты по ID.
> Старые таблицы относятся к core37e; новый набор20×2 хранится отдельно в results/quality-v2.
> Код старой версии: results/history-quality-v1/source. Статус: [QUALITY](../QUALITY.md).


База содержит **полные MemGPT, MemoryBank и Generative Agents**, оригинальные PDF
и оригинальный индекс недели 6 из 182 чанков. Документация Domovoy в поиск не входит.
[Provenance](PROVENANCE.md), [рубрика](eval/articles_rubric.md).

## Предпосылки

Нужны установленная Ollama с qwen3-embedding:0.6b, llama.cpp Vulkan и внешние
Tiel Q8/Q4 GGUF. Путь по умолчанию: /home/kotdath/omp/personal/amd-strix-halo-toolboxes/models/tiel-coder/.
BGE GGUF: /home/kotdath/.local/share/domovoy-rag/models/bge-reranker-v2-m3-f16.gguf.
Веса не копируются в эти директории и на VPS. Нужны Python 3.12 и установленный
`uv`; setup.sh создаёт собственную .venv и загружает закреплённые tokenizers
в пользовательский HF cache. Подготовка требует сети; inference использует
локальный cache. Ollama должна быть запущена на 127.0.0.1:11434.

```bash
cd day28-local-rag
test -f .env || cp .env.example .env
chmod 600 .env
./setup.sh
```

В отдельных терминалах из этой директории (если matching сервисы уже работают,
повторно их не запускайте):

```bash
./run_model.sh
./local_models/run_bge.sh
RAG_RERANK_MODEL_PATH=/home/kotdath/.local/share/domovoy-rag/models/bge-reranker-v2-m3-f16.gguf \
 .venv/bin/python -m uvicorn app:app --app-dir local_models --host 127.0.0.1 --port 8765 --no-access-log
```

Для baseline нужен CTX_PER_SLOT=65536; optimized 32768. Общий context включает
system/history/excerpts и output reserve 8192/6144. Лимиты увеличены в четыре раза.
Embeddings имеют отдельный input лимит 8192, reranker query 1024; их нельзя считать
равными генеративному context. CLI/RAG исходники не импортируются из соседних версий.

## Общение и проверка

```bash
.venv/bin/python cli.py ask 'Как MemGPT организует основную и внешнюю память?' --rag --json
.venv/bin/python cli.py chat --rag
.venv/bin/python cli.py ask 'Как MemoryBank ищет релевантные воспоминания?' --rag --rerank --json
.venv/bin/python protocol.py
.venv/bin/python bot.py --rag
.venv/bin/python index.py check
.venv/bin/python index.py rebuild --output data/index/rebuilt.jsonl
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python verify_rag.py
```

В chat доступны /reset и /exit. JSONL protocol позволяет автономно проверять
Agent/session без Telegram. `Model` — собственный HTTP-клиент с методами
`complete(messages, profile)` и `count_prompt(messages)`, а `Agent` хранит
состояние и управляет RAG. `chat.py` оставлен как совместимый alias Agent. Цитаты содержат название, версию, URL и точные
страницы PDF; raw sources.quote сохраняет исходные символы и UTF-16 offsets.

Retrieval: Qwen embedding → NumPy cosine + собственный BM25 → weighted RRF
(dense 1.0, lexical 0.35) → optional BGE (не больше 20 кандидатов) → четыре
опорных чанка. Каждый дополняется соседями ±1 из канонического текста; виртуальное
окно сохраняет native chunk IDs, revision, UTF-16 offsets и страницы. Для явно
названных статей применяется source filter; сравнения балансируют фрагменты
между статьями. Оригинальные 182 embeddings/чанка не изменяются. Generic topic
prefix отключён: он ухудшал ранжирование конкретных формул.

Agent планирует 1–4 части вопроса и переводит retrieval queries для английских
статей. Одна генерация обязана вернуть все P1/P2/...; короткие E001/... ID
восстанавливаются программой в точные цитаты. Затем Tiel проверяет утверждения
и полноту относительно исходного вопроса. При замечаниях допускается один
дополнительный поиск/доработка и окончательная проверка; неподдержанные
утверждения удаляются отдельно. История помогает разрешить follow-up, но
не становится документальным источником. Все calls, actual finish_reason,
usage, каталоги цитат, review inputs и timings сохраняются. Буквальное совпадение
цитаты и self-review не гарантируют смысловой поддержки: её проверяют независимо.

## Сравнение и актуальность

Новая проверка качества v2 использует отдельно подготовленные 20 вопросов и
два прохода. Для своего повторения выберите **новый** output; готовые файлы
не перезаписываются. Скрипт сохраняет source snapshot, raw calls, runtime и
ошибки. Наличие expected facts в JSONL не означает их передачу модели:
`quality_eval.py` передаёт Agent только поле question.

```bash
.venv/bin/python quality_eval.py --questions eval/quality_v2_questions.jsonl \
 --repeat 2 --output results/quality-repeat/heldout_answers.jsonl
.venv/bin/python compare_cloud.py --output results/cloud-repeat/cloud_answers.jsonl
```

Для сводки нового повторения сначала нужны независимые оценки всех 40 ответов
с actual answer SHA в `heldout_grades_independent.json` рядом с answers.
Прежние grades подходят только к прежним actual answers.

```bash
.venv/bin/python summarize_quality.py --directory results/quality-repeat
```

Сохранённые результаты текущего улучшения лежат в `results/quality-v2/`.
Дополнительный paired эксперимент фильтра использует готовые генерации и
реальный дополнительный вызов; его нельзя называть новым полным прогоном.
Текущий live сервис и paired policy сравниваются по source SHA.

Ниже — команды отдельной исторической матрицы M0/M1/M2. Запуск с текущими
исходниками создаст новые ответы; он не воспроизведёт автоматически старые
числа core37e. Известная рубрика этого набора не является новым скрытым тестом.

Для сопоставимого нового evaluation остановите только свой backend и
запустите `PARALLEL=1 CTX_PER_SLOT=32768 ./run_model.sh`; gateway/BGE остаются
активны. Сохранённые результаты поставки можно изучать без нового inference.
Перед повтором архивируйте прежние `results/golden_rag_answers.jsonl` и
`results/cloud_answers.jsonl` в отдельную папку с датой: evaluation **добавляет**
строки, а summarize требует ровно 10 вопросов на режим. Не удаляйте старые доказательства.

```bash
.venv/bin/python evaluate_rag.py --set dev --modes M1
.venv/bin/python evaluate_rag.py --modes M0,M1,M2
.venv/bin/python compare_cloud.py --output results/cloud-new/cloud_answers.jsonl
```

После нового запуска нужна новая независимая оценка по
`eval/articles_rubric.md`: сохранить grades с SHA фактически полученных ответов
в `results/golden_grades_independent.json` и `results/cloud_grades_independent.json`.
Прежние оценки нельзя присоединять к новым ответам. Только после этого:

```bash
.venv/bin/python summarize_rag.py
.venv/bin/python verify.py
```

Исторические режимы core37e: M0 — Tiel без RAG, M1 — dense RAG, M2 — RAG+BGE.
В текущем v2 режим с RAG использует hybrid retrieval; старые числа не описывают его. compare_cloud.py требует
DEEPSEEK_API_KEY из окружения и проверяет точный deepseek-flash через /models.
Используется тот же собственный Agent, retrieval и проверка; только три
проверенных публичных статьи, без пользовательской/TGистории. Cloud JSON mode
не равен локальному schema decoder; токенизатор и контекст провайдера отличаются.
APIusage истинный; Tieltemplate используется только как общий reference budget.
Облако и веб никогда не являются автоматическим fallback обычного агента.

verify.py проверяет hash закреплённого PDF и последнюю версию arXiv. Это проверка байтов/
ревизии, не научной истинности. Обычные CLI/Agent запросы имеют web off;
`cli.py ... --web` включает проверку для их источников. Отдельный запуск
`verify.py` явно обращается к arXiv и сам по себе не является offline проверкой.

В историческом сравнении core37e M1 также взят из Q8optimized первого прохода дня29,
второй проход даёт stability. Это те же зафиксированные вопросы/индекс/профиль/backend с одним слотом.
Результаты и ошибки: [выводы](results/conclusions.md). Старые docs/первые article
runs сохранены в history-domovoy-docs и articles_initial_without_coverage_review.
Остановка: Ctrl+C для собственных model/gateway/CLI/bot процессов.
[Видео](DEMO.md).
