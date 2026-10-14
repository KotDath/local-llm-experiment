# День 30 — приватный HTTP-сервис: ПК и шлюз VPS

Требования: реальный сетевой доступ к локальной модели, чат, несколько
одновременных запросов, rate limit и max context. VPS служит только шлюзом.

## Топология

На ПК: Tiel Coder, собственный Agent, embeddings, RAG и HTTP API.
На VPS: Caddy HTTPS, gateway.py на стандартной библиотеке Python и внутренний
SSH reverse-forward. Клиент → HTTPS /local-llm → VPS loopback 8781 → loopback 18780 → SSH → ПК loopback 8780 → llama.cpp 8772.
Модели, индекс и ML runtime на VPS не устанавливаются.

## Реализация и проверки

1. Запустить модель выбранного в дне 29 квантования с соответствующим контекстом
   на слот; API и Telegram должны использовать соответствующий профиль.
2. Защитить API bearer token. История изолирована по credential/session;
   `/sessions`, `/chat`, `/sessions/reset`, `/health` доступны по HTTP.
3. Проверять настоящий rendered prompt через backend template/tokenizer:
   prompt + output reserve не превышает 32768/6144 или 65536/8192 соответственно.
4. Ограничить тело 512 KiB, POST quota 20/min на credential, очередь 10,
   active inference 3, ожидание свободного слота 120 s. Один API process.
   Ошибки: auth401, body413, input/context422, rate429 с Retry-After,
   invalid upstream502, unavailable/queue503, timeout504.
5. Установить только изолированный gateway unit. Проверять SSH host key;
   private key и секреты остаются на ПК. Добавить отдельный Caddy route с
   validate/backup/reload; сохранить существующие TLS/ACME/OCR routes.
6. Выполнить HTTPS запросы с ПК и с VPS без клиентского SSH-forward: multi-turn RAG, отказ по неизвестному
   факту, обычный чат, reset. Связать request IDs и hashes с журналом ПК.
7. Проверить реальные серии 5 и 10 одновременных запросов, сохранив ответы,
   usage и время. HTTP200 отдельно от оценки смысловой правильности.
8. Проверить auth/body/context/rate и восстановление после окна quota;
   реальную границу нового context, overflow и возврат к работе.
9. Проверить остановку/восстановление собственного backend и туннеля.
   Synthetic upstream отдельно проверяет 502/504/queue timeout и освобождение
   locks/queue; такие тесты не являются доказательством качества LLM.
10. Проверить loopback listeners, отсутствие weights/index на VPS, запуск
    и остановку по README; не заявлять проверенный reboot ПК по unit examples.

Секреты не входят в исходники, результаты и видео. Telegram проходит через
инфраструктуру Telegram; полностью локальный режим доступен через CLI/HTTP,
без cloud и с выключенной веб-проверкой.

Инструкции: [README.md](README.md), [DEMO.md](DEMO.md).
Фактические результаты: `results/https_final.json`, `https_load.json`,
`https_limits.json`, `https_overflow.json`, `https_context_boundary.json`,
`failure_injection.json`. Старые проверки прежних лимитов архивированы;
текущий статус определяется новой [приёмкой](../ACCEPTANCE.md).

## Проверка улучшения качества v2

Предыдущие результаты core37e сохранены в `results/history-quality-v1/source`
и исходных raw logs. Новая версия использует hybrid dense/BM25 RRF, соседние
чанки, план частей вопроса, ID цитат, одну доработку и окончательную проверку.
Новый независимо подготовленный набор — 20 вопросов × два прохода; только
question попадает в Agent, expected facts не входят в prompt. Оценка связана
с SHA фактически выданного ответа. Цель: ≥80% correct и отсутствие
неподтверждённых фактов; достижение определяется независимой оценкой, а не HTTP200.
Фильтр лишних фактов проверен отдельным paired экспериментом и отклонён:
34/40 correct против36/40, два ухудшения, число неподтверждённых фактов то же3. Статус и итоговые ограничения: [QUALITY](../QUALITY.md).

Итог: основной вариант36/40 correct, три ответа с неподтверждёнными фактами;
цель ≥80% выполнена, цель0неподтверждённых фактов не достигнута.
Новых проверок после завершения этой серии не запускали. [Отчёт](../REPORT.md).
