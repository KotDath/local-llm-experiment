# Демонстрация дня 29

Ориентир: 4:00–6:00. Полный benchmark значительно дольше; показать полный
сохранённый лог и таблицу, затем один живой пример.

1. Показать baseline65536/8192/temp1 и optimized 32768/6144/temp0.1,
   разные task prompts и общий citation validator/review.
2. Показать два GGUF, закреплённый snapshot, SHA и проверку metadata.
3. Открыть `results/comparison.md` и `benchmark.csv`: все A–D, два повтора,
   correct/partial, галлюцинации, время, tokens/s и память.
4. Объяснить A/B как изменение настроек вместе; A/C и B/D — квантование.
   Показать фактический выбор `configs/selected.json` и его основание.

После остановки своих API/бота/backend, в отдельном терминале:

```bash
QUANT=Q8 PARALLEL=1 CTX_PER_SLOT=65536 ./run_model.sh
```

Во втором терминале из этой же директории:

```bash
.venv/bin/python cli.py ask 'Как MemGPT организует основную и внешнюю память?' --rag --profile baseline --json
```

Для optimized остановить backend и перезапустить с правильным контекстом:

```bash
QUANT=Q8 PARALLEL=1 CTX_PER_SLOT=32768 ./run_model.sh
```

Затем повторить тот же вопрос с `--profile optimized`. Две демонстрационные
реплики не заменяют контролируемую матрицу. После видео восстановить quant,
context и profile по `configs/selected.json`, затем API/бота.
RSS/PSS/host RAM/VRAM/GTT на Strix Halo не складывать. Не скрывать partial,
ожидание и ограничения малой выборки. Секреты в кадр не выводить.

Обновлениеv2: показать results/quality-v2/comparison.md (36/40correct,
три неподтверждённых факта, отклонённый filter34/40). Все старые A–D и
load/limits/outage назвать измерениями прежнего core37e; свежие HTTPSдиалоги
core82 в quality_v2_https_network/final и независимомaudit дня30. Полная
selected-quote support там2/4 при правильных основныхответах4/4.
Cloudfinal7/10 измерен надругом наборе; прямого сравненияпроцентов не делать.
Подробный отчёт: [REPORT](../REPORT.md).
