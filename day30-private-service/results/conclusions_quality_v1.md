# Фактические выводы дня 30

Сервис доступен по **https://95.215.56.217/local-llm** с bearer API key.
TLS проверяется штатным CA хранилищем и по IP. Клиентский SSH-forward выключен;
реальные запросы выполнены напрямую по HTTPS с ПК и с VPS. На ПК работают
Agent, Tiel Coder Q8/B, Ollama embeddings и RAG; VPS обслуживает только
Caddy HTTPS, stdlib gateway и внутренний reverse SSH. Индекс и GGUF на VPS
не копировались. `vps_audit.json` проверяет процессы, listeners и собственный
каталог развёртывания, а не все файлы чужой VPS.

SSH внутри предоставляет VPS доступ к private loopback API ПК через исходящее
соединение ПК. Это сохраняет синхронный Chat API и не требует входящего порта
на ПК. В setup-ocr очередь обслуживается исходящим HTTPS polling worker;
для чата выбран внутренний туннель, чтобы не вводить job/poll протокол.
NAT на ПК не проверялся. Клиенту нужен только Python и API_URL/API_TOKEN.
Caddy deploy проверил конфигурацию, сохранил TLS/ACME/OCR fallback и backup;
его доказательства — `https_deployment.json`.

## Реальные HTTPS проверки

- `https_network.json`: history, отдельная session и reset; три actual calls.
- `https_load.json`: 5/5 и 10/10 одновременных запросов завершились HTTP200,
  настоящие outputs, usage и полное HTTP время сохранены.
- `https_limits.json`: auth401, тело больше 512KiB →413, context422;
  первые 20 oversized-context POST дали422, следующий429 с Retry-After 26;
  после окна quota новый ответ «Париж» доставлен HTTP200.
- `https_context_boundary.json`: prompt 26624 + reserve 6144 = context 32768
  принят, actual backend usage 26624 и новый ответ сохранены; prompt 26625
  отклонён 422 до generation. Тела 53 KB не упираются в body limit.
- `https_overflow.json`: 15 реальных длинных запросов; 9 HTTP200,
  2 HTTP503 busy и 4 queue_wait_timeout через 120 s. Это управляемые отказы,
  не заявление о 15/15 успешных ответах.
- `https_final.json`: 4 RAG и 3 plain/history/reset ответа доставлены HTTP200.
  Независимо полностью grounded оценены2/4 RAG: function chaining и отказ
  выдумывать Galaxy A54 p95. У первой реплики слабая поддержка transfer/sections
  выбранными цитатами; сравнение после follow-up подменяет chaining на eviction
  и оставляет citation gap. Новых фактических галлюцинаций в этом диалоге
  не найдено, но полнота и поддержка цитат остаются дефектами.

Request IDs, question hashes, usage и total time независимая проверка связывает
с журналом HTTP API на ПК (raw model traces сохранены в ответах): `https_receipts_audit_independent.json` и
`https_pc_request_receipts_independent.json`. HTTP200 отдельно от семантики.

## Отказы и восстановление

Реальная остановка и восстановление собственной модели и внутреннего туннеля
подтверждены: `https_actual_model_outage.json` →503 model_unavailable,
`https_actual_model_recovery.json` →200 с новой генерацией «Париж»;
`https_tunnel_outage.json` →503 pc_tunnel_unavailable,
`https_tunnel_recovery.json` →200 с новой генерацией «Токио». Восстановлены
тот же Q8/B, context 32768 и 3 slots. `final_runtime_check.json` подтверждает
ready/RAG ready, пустую очередь и живые model/API/bot/tunnel.
`failure_injection.json` отдельно проверяет synthetic 502/504/422/queue503
и освобождение locks/semaphore. Эти fixtures не выдаются за настоящую LLM.

Выбран Q8/B по 80 ответам дня29: 5/20 полностью correct, 2/20 фактических
галлюцинаций. Context 32768/output 6144 и 3 native slots совпадают с API health.
Параметры не гарантируют безошибочного RAG. Gateway unit включён на VPS;
автозапуск после reboot ПК не проверялся, service examples требуют установки.
Секреты, закрытый клиентский env, runtime и веса исключены из поставки Git.
Видеоинструкция: [DEMO](../DEMO.md); готовый mp4 не входит в эту поставку.
