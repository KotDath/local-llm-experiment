# Выводы дня 30: фактическая сеть и ограничения

Домашний inference server — ПК AMD Strix Halo. VPS выполняет только stdlib
gateway на loopback 8781; remote SSH forward 18780 ведёт к PC API 8780.
Ни weights, ни RAG index, ни inference runtime на VPS не размещались.
Существующие Caddy и legal-redaction gateway 8765 сохранены.

- Настоящий `/chat` исполнялся с VPS; ответ «Париж» имеет PC request ID и usage.
- Дополнительно проверен client SSH forward: PC client → VPS → PC model.
- Две связанные реплики, reset и новый ответ прошли через сеть (remote_network.json).
- 5/5 и 10/10 конкурентных запросов дали HTTP200 и actual LLM outputs/usage.
- Auth: 401; >64KiB:413; превышенный context:422. Prompt boundary 6656+1536=8192
  принят, counted tokens6656 точно совпадают с backend usage, ответ «готово».
- 20 authenticated oversized-context запросов дали422, 21-й429/Retry-After;
  после окна получен настоящий HTTP200 ответ. Лимит не отключался для нагрузки.
- 15 параллельных длинных запросов: 13 HTTP200, 2 управляемых503 busy.
- Реально остановленная модель дала503; реальный обрыв reverse SSH tunnel
  с VPS дал503 pc_tunnel_unavailable. После восстановления remote dialogue
  снова завершилсяHTTP200; ошибки не заменялись cached fake response.
- 502 malformed upstream и504 timeout проверены отдельной failure injection;
  эти synthetic responses не выдаются за model quality evidence. Queue locks
  после ошибок освобождаются; неверные session_id отвергаются422.
- Agent socket audit в web/cloud off видел только127.0.0.1:8765 и8772;
  tokenizer gateway запущен offline/telemetry off, actual embedding fingerprint совпал.

PC сервисы работают как запущенные процессы; VPS gateway установлен/включён
systemd. PC reboot auto-start не проверялся, для него предоставлены unit examples.
Внешних публичных Ollama/llama.cpp endpoints не создано. Telegram остаётся
каналом инфраструктуры Telegram, поэтому локальный CLI/HTTP предпочтителен
для полностью локального взаимодействия.

## Финальный повтор после выбора модели

Выбрана **Q8/B optimized** из `configs/selected.json`: temperature 0.1,
max output 1536, context 8192. На ПК восстановлены три слота по 8192, API и
бот. Финальная версия Agent/RAG совпадает с исходниками всех 80 измерений
A–D (source SHA `f1a41f303db90a8efbae7c593bca221e7b211391c28cd7ec61e617517132eabf`).

`remote_final.json` содержит семь настоящих ответов с VPS: четыре RAG-реплики
и три plain-реплики с проверкой истории/reset. Все семь дали HTTP 200 и точно
сопоставлены с журналом API на ПК по request ID, вопросу, usage, времени и числу
вызовов. Readiness модели/индекса и совпадение слотов подтверждены.
Независимые доказательства: `final_remote_review_independent.json` и
`final_pc_request_receipts.json`.

Повторная нагрузка после восстановления выбранной модели: **5/5 и 10/10**
HTTP 200, реальные usage и корректные ответы «Париж», «Токио», «Рим», «Земля».
Повтор ограничений подтвердил 401, 413, 422, двадцать 422 перед 429 с
Retry-After 55; после окна — HTTP 200 с реальным ответом «Париж».
Текущие файлы — `remote_load.json` и `remote_limits.json`; ранние измерения
сохранены в `before_final_restart/`.

## Ограничение качества RAG

В финальном сетевом диалоге все четыре требуемых ответа/отказа верны по
существу, но **полностью документально поддержаны 3/4**. Первый ответ правильно
называет три слоя памяти, затем добавляет утверждение об отключении long-term
с цитатой про фильтр дат arXiv, а изоляцию рабочего слоя формулирует шире
источника. Эти дефекты сохранены в raw и независимой оценке. ID и буквальные
цитаты валидны, однако выбранная цитата не обязательно подтверждает смысл.
Предыдущий независимый локальный диалог 4/4 — отдельный запуск; он не заменяет
оценку этого финального сетевого ответа. Гарантия отсутствия галлюцинаций не заявляется.
