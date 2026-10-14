# Итоговое видео: дни 26–30

Видео записывает фактическую работу пяти самостоятельных snapshots.
Основная демонстрация — CLI/HTTP/JSONL, Telegram показывается дополнительно.
Этот файл — инструкция записи, не утверждение о наличии готового видеофайла.

| Ориентир | Что показать | Доказательство |
|---|---|---|
| 0:00–1:00 | Q8 launcher, local health, три разных запроса | day26 results/actual responses; арифметическую ошибку назвать честно |
| 1:00–2:00 | Agent entity, direct Chat API, Telegram и JSONL sessions | day27 protocol/independent receipts |
| 2:00–4:00 | Import недели 6, retrieval/quotes, неизвестный вопрос, web check | day28 source generation, actual local/cloud quality table |
| 4:00–6:00 | Baseline/optimized, Q8/Q4 и одинаковые вопросы | day29 config hashes, CSV, independent grades, resources |
| 6:00–8:00 | Клиент HTTPS → VPS → внутренний SSH → PC API/model, limits, concurrency | day30 https network/load/limits/recovery reports |

Не ускорять ролик так, чтобы исчезли ошибки/ожидания, влияющие на вывод.
Если реальные ответы/сетевые тесты требуют дольше, увеличить длительность и
обновить таймкоды. Benchmark целиком длиннее видеослота: показать сохранённый
полный лог и один живой повтор одинакового вопроса.

Перед записью:

1. Выбрать одну активную model/API/bot instance; не создавать порт conflicts.
2. Проверить local health, BGE/gateway health и внутренний SSH tunnel;
   клиентский SSH-forward не запускать.
3. Проверить выбранный model/profile соответствует финальному сравнению.
4. Подготовить терминалы ПК и VPS и файлы результатов.
5. Скрыть `.env`, private keys, bearer headers, TG user IDs и credentials.

В рассказе различать factual correctness, completeness, literal citations и
семантическую поддержку claims. Веб-проверка — hash/revision документа на сайте,
а не универсальная проверка истинности. Synthetic 502/504 fault injection
показывать отдельно от реальных inference и VPS load requests.

Подробные команды: `day*/DEMO.md` и `day*/README.md`.

## Обновление качества

Показать [REPORT.md](REPORT.md) и day28/results/quality-v2/comparison.md:
36/40correct, три ответа с неподтверждёнными фактами. Фильтр34/40 отклонён.
Старую таблицуA–D назвать историческим core37e; набор20×2 отличается отстарых10×2.
Свежие HTTPдиалоги:quality_v2_https_network/final иaudit — основные ответы4/4,
полная поддержка цитат2/4. Cloudfinal7/10 относится кдругому набору;
не заявлять прямое сравнение процентов90/70. Сохранённые результаты отличать
от живой демонстрации. Новых проверок при подготовке этого отчёта не запускали.
