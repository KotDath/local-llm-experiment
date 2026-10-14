# День 29: оптимизация RAG по статьям, Q8/Q4

> Обновление качества v2 завершено: основной вариант36/40 correct, три ответа с неподтверждёнными фактами. Текущий Agent использует hybrid RRF,
> контекст соседних чанков, обязательные части ответа и цитаты по ID.
> Старые таблицы относятся к core37e; новый набор20×2 хранится отдельно в results/quality-v2.
> Код старой версии: results/history-quality-v1/source. Статус: [QUALITY](../QUALITY.md).


Самостоятельная версия Agent/RAG. Полные три статьи и оригинальный индекс недели 6 находятся
в data; модель Tiel Coder 35B-A3B, две опубликованные квантования одного snapshot.

## Предпосылки

Нужны установленная Ollama с qwen3-embedding:0.6b, llama.cpp Vulkan и внешние
Tiel Q8/Q4 GGUF. Путь по умолчанию: /home/kotdath/omp/personal/amd-strix-halo-toolboxes/models/tiel-coder/.
BGE GGUF: /home/kotdath/.local/share/domovoy-rag/models/bge-reranker-v2-m3-f16.gguf.
Веса не копируются в эти директории и на VPS. Нужны Python 3.12 и установленный
`uv`; setup.sh создаёт собственную .venv и загружает закреплённые tokenizers
в пользовательский HF cache. Подготовка требует сети; inference использует
локальный cache. Ollama должна быть запущена на 127.0.0.1:11434.

```bash
cd day29-optimization
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

## Профили и матрица

| Case | Quant | Temperature | Context/slot | Max output | Prompt |
|---|---|---:|---:|---:|---|
| A | Q8 | 1.0 | 65536 | 8192 | baseline |
| B | Q8 | 0.1 | 32768 | 6144 | article optimized |
| C | Q4 | 1.0 | 65536 | 8192 | baseline |
| D | Q4 | 0.1 | 32768 | 6144 | article optimized |

Оба лимита context/output в четыре раза больше прежних. Общие source, retrieval algorithm, exact
citation validator и проверка полноты одинаковы. A/B сравнивают bundle
настроек/prompt. В историческом core37e A/C и B/D меняли quant при одинаковом
answer prompt/evidence; текущий planner может изменить downstream context,
поэтому новый прогон измеряет эффект quant на всём Agent. Prompt и пользовательские факты не дообучают веса.

Перед замером остановите свои demo API/бота/модель на 8772. Benchmark не убивает
чужие процессы. Ollama/BGE/embedding gateway остаются активными.

```bash
./download_q4.sh
.venv/bin/python verify_models.py
.venv/bin/python benchmark.py --case A
.venv/bin/python benchmark.py --case B
.venv/bin/python benchmark.py --case C
.venv/bin/python benchmark.py --case D
```

После нового запуска независимый проверяющий оценивает все 80 ответов по
`eval/articles_rubric.md` и сохраняет `results/benchmark_grades_A_independent.json`
(аналогично B/C/D), с actual run_id, id, repeat и answer_sha256. Затем:

```bash
.venv/bin/python grade_results.py --comparison-mode end-to-end
```

Загрузка Q4 закреплена в configs/models.json, resume HTTP ranges и полный SHA до переименования.
Опционально DOWNLOAD_BACKEND=xet; оба транспорта проверяют один pinnedSHA.
Установленные файлы уже проверены. Не сравнивайте latest с другой ревизией Q8.

Benchmark сам запускает backend: один слот, проверка фактического context 65536/32768,
настоящий generation warmup исключён и записан,10 одинаковых вопросов × 2 для четырёх условий = 80 измеряемых запросов.
Свежий Agent на каждый вопрос; seed42 и cache_prompt:false. Разрешение follow-up/
review/repair/revision — реальные вызовы и входят во время,usage и стоимости.
Failures/truncations/partial не отбрасываются. Profile и backend metadata и raw SHA сохранены.

Исторический core37e проверяется `grade_results.py --comparison-mode fixed-context`:
совпадают именно answer prompts и sent evidence, не только первый LLM call.
Для текущего planner используйте `--comparison-mode end-to-end`: входные вопросы,
source/model/config/corpus остаются контролируемыми, изменения plan/queries/
evidence/answer prompt записываются в `results/benchmark_controls.json`.
Это не изолированный тест квантования answer generation при фиксированном контексте.
Прогоны качества v2 не заменяют новую матрицу baseline/optimized/Q8/Q4: текущий
профиль унаследован из исторического выбора, нового выигрыша скорости не заявляем.

`benchmark.py` по-прежнему измеряет 10 вопросов × два прохода × четыре условия;
перед новым запуском сохраните старую results в отдельный архив. Матрица 20×2
из `quality_eval.py` отдельно проверяет только качество выбранного Q8/optimized.

`grade_results.py` требует новые независимые оценки по run/id/repeat/answerSHA;
после нового перезапуска старые оценки намеренно отвергаются. Рубрика в eval.
CSV/table/selection: [сравнение](results/comparison.md), [выводы](results/conclusions.md),
configs/selected.json. Скоростьbackend отдельно от полного времени запроса.
RSS/PSS/whole-host RAM/global VRAM/GTT — разные счётчики общей памяти Strix Halo,
не складывать. Sampling около 200 ms не является абсолютным аппаратным пиком. Отключение KV cache не выключает
файловый cache ОС; load/readiness не сравнивается как одинаковый холодный старт.

После benchmark запустите выбранную модель и нужный context, затем CLI:

```bash
QUANT=Q8 CTX_PER_SLOT=32768 ./run_model.sh
.venv/bin/python cli.py chat --rag --profile optimized
```

Если выбор другой, подставьте quant/context/profile из configs/selected.json.
Ctrl+C останавливает собственный процесс. [Видео](DEMO.md).
