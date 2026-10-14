# Выводы приватного сервиса и нового Agent82

Сервис **https://95.215.56.217/local-llm** использует проверяемыйTLS и bearer
API key. Клиентский SSH-forward выключен; клиенту нужны Python3 и закрытый
API_URL/API_TOKEN. НаПК собственныйAgent, API, TielCoderQ8, embeddings иRAG.
НаVPS Caddy+stdlib gateway; weights/индекс/MLruntime туда не устанавливались.

Внутренний reverseSSH соединяет loopbackVPS с loopbackAPIПК через исходящее
соединениеПК. Сохраняет синхронныйChat API без входящего портаПК. Вsetup-ocr
очередь+HTTPS polling; такая схема потребовала бы job/poll protocol длячата.
NAT не проверялся. СуществующиеTLS/ACME/OCR routes сохранены.

## Свежий завершённый HTTPS диалог

`quality_v2_https_network.json` и `quality_v2_https_final.json`:10запросов,
29реальныхLLM calls. Независимый join с журналомПК подтвердил request IDs,
source82,usage/time; history/reset/context/provenance корректны. Q8optimized,
context32768/output6144, триnative/API slots согласованы.

Основные RAG вопросы отвечены правильно4/4; полностью подтверждены выбранными
цитатами2/4. Фактических галлюцинаций не выявлено. Первая реплика цитирует
оборванное recall-queue предложение; сравнение использует слабую цитату для
FIFO/recursive summary. Self-review эти пробелы не заметил. RAGзанимает84–228с.
[Независимая оценка и receipts](quality_v2_https_audit.json).

Независимая основная серия Agent82 дала36/40 correct, три неподтверждённых факта.
Дополнительный focusfilter отклонён из-за34/40 идвухухудшений. Эти40вопросов
не являются тестом сети или нагрузкой. [Качество](quality-v2/comparison.md).

## Сохранённые технические доказательства предыдущего запуска

`https_load.json`:5/5 и10/10 concurrent requests дали200 среальной генерацией.
`https_limits.json`:401auth,413body,422context,429/Retry-After, восстановление200.
`https_context_boundary.json`:26624prompt+6144reserve=32768 принято,26625отклонено
доgeneration. `https_overflow.json`:9/15 получили200,6контролируемый503.
Реальная остановка/восстановление model/tunnel:503→200. Synthetic failurepaths
отдельно проверяют502/504/queue503/освобождениеlocks. Это результаты прежнего
core37e; после улучшения не выполнена новаяload/limits/outage серия.
[Полные прежние выводы](conclusions_quality_v1.md).

Q8/B выбран в исторической матрице80ответов core37e; текущаясерия не выбирала
зановоquant. Автозапуск послеrebootПК не проверялся: systemdexamples требуют
установки. По просьбе пользователя после окончания текущих прогонов новых
проверок нет. Секреты/.env/runtime/venv/weights исключены изGit.
[Видеоинструкция](../DEMO.md), [общийотчёт](../../REPORT.md).
