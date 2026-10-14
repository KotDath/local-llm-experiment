# День 30: приватный агент на ПК через шлюз VPS

> Обновление качества v2 завершено: основной вариант36/40 correct, три ответа с неподтверждёнными фактами. Текущий Agent использует hybrid RRF,
> контекст соседних чанков, обязательные части ответа и цитаты по ID.
> Старые таблицы относятся к core37e; новый набор20×2 хранится отдельно в results/quality-v2.
> Код старой версии: results/history-quality-v1/source. Статус: [QUALITY](../QUALITY.md).


На ПК работают **Agent, Tiel Coder, embeddings и RAG**. На VPS установлен
Caddy HTTPS и `gateway.py`: стандартная библиотека Python, loopback proxy, без LLM,
weights, tokenizers и индекса. Telegram также запускается на ПК.

## Установка и запуск ПК

```bash
cd day30-private-service
test -f .env || cp .env.example .env
chmod 600 .env
./setup.sh
.venv/bin/python scripts/start_selected_model.py
./local_models/run_bge.sh
```

В отдельных терминалах:

```bash
RAG_RERANK_MODEL_PATH=/home/kotdath/.local/share/domovoy-rag/models/bge-reranker-v2-m3-f16.gguf \
 .venv/bin/python -m uvicorn app:app --app-dir local_models --host 127.0.0.1 --port 8765 --no-access-log
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8780 --no-access-log
```

`start_selected_model.py` берёт квантование и context из `configs/selected.json`
дня29. Это унаследованный выбор исторического core37e; новая серия Agent82
не выбирала quant заново. `QUANT=Q8 CTX_PER_SLOT=32768 ./run_model.sh`
запускает тот же профиль.

Для `setup.sh` нужны `uv` и Python 3.12; для body-limit probe — `curl`.
Нужны установленная Ollama с `qwen3-embedding:0.6b`, llama.cpp и внешние веса.
При уже запущенных matching сервисах не запускайте вторую копию на тех же портах.
Укажите случайный `API_TOKEN` в закрытом `.env`; файл chmod 600 и не входит в Git.

## VPS, HTTPS и внутренний туннель

На ПК нужны OpenSSH client (`ssh`, `ssh-keygen`) и `sshpass` для password bootstrap
и удалённых проверок. Bootstrap рассчитан на root SSH account VPS с systemd
и Python 3; доступ уже проверен с предоставленными credentials. Если используется
другой пользователь, системную установку нужно выполнить с правами root.

Для bootstrap используется отдельный закрытый env с `HOST_IP`, `SERVER_LOGIN`,
`SERVER_PASSWORD`, optional `SERVER_PORT`. На этом workspace это корневой
`prod.env`; его не нужно копировать на VPS и нельзя показывать на видео.

```bash
.venv/bin/python scripts/deploy_gateway.py /absolute/path/to/private-vps.env
```

Deploy устанавливает только `/opt/local-llm-experiment-gateway/gateway.py` и
изолированный systemd unit `local-llm-experiment-gateway.service`. Существующие
сервисы 8765 продолжают работать. Отдельный HTTPS deploy добавляет маршрут
`/local-llm/*` в существующий Caddy, сохраняя его TLS, ACME и OCR fallback. Создаётся собственная restricted SSH key
для reverse-forward (private key остаётся `runtime/tunnel_key` на ПК).
Verified VPS host key должен уже быть в known_hosts; проверка не отключается.

Экспортируйте **только** `HOST_IP`, `SERVER_LOGIN`, `SERVER_PORT` в окружение
терминала и запустите:

```bash
./scripts/start_tunnel.sh
```

Схема: VPS `127.0.0.1:8781` → VPS `127.0.0.1:18780` → SSH →
ПК `127.0.0.1:8780` → локальный Agent → llama.cpp `127.0.0.1:8772`.
Публичные LLM/Ollama endpoints не создаются. После запуска туннеля выполните:

```bash
.venv/bin/python scripts/deploy_https.py --env-file /absolute/path/to/private-vps.env
```

HTTPS deploy рассчитан на имеющийся Caddy VPS: проверяет структуру конфигурации,
валидирует новую, сохраняет backup и выполняет reload с откатом при ошибке.
Нельзя копировать его Caddyfile поверх произвольной чужой конфигурации.
Результат: `results/https_deployment.json`; клиентский файл
`runtime/https_client.env` содержит только API_URL/API_TOKEN, mode 600. Gateway использует Python 3.14
VPS, ML-часть — Python 3.12 на ПК.

## Чат с другого устройства

Текущий адрес: **https://95.215.56.217/local-llm**. Клиенту нужны Python 3 и
`cli.py`, `common.py`, `model.py` либо полный snapshot. Модель, SSH и доступ к
VPS account клиенту не нужны. Безопасно передайте ему только закрытый env:

```dotenv
API_URL=https://95.215.56.217/local-llm
API_TOKEN=YOUR_PRIVATE_API_KEY
```

```bash
chmod 600 client.env
python3 cli.py health --env-file client.env
python3 cli.py chat --env-file client.env
python3 cli.py ask 'Как MemGPT организует основную и внешнюю память?' \
 --env-file client.env --rag --json
```

Сертификат проверяется штатным хранилищем CA и по IP; отключение TLS verification
не требуется. Все маршруты защищены bearer token. `/reset` очищает текущую
историю, `/exit` завершает CLI. На ПК можно использовать созданный deploy файл
`runtime/https_client.env`. Не показывайте его содержимое в видео.

SSH нужен **только внутри**: ПК устанавливает исходящее защищённое соединение
к VPS, которое предоставляет шлюзу доступ к loopback API на ПК. Это сохраняет
синхронный Chat API без открытого входящего порта на ПК. Наличие NAT не
проверялось и не используется как доказанный аргумент. В `setup-ocr` применена
другая схема: очередь на VPS и исходящий HTTPS polling worker на ПК; она
подходит для фоновых OCR jobs, но потребовала бы job/poll протокола для чата.
Здесь клиент получает обычный HTTP ответ через HTTPS. `client_tunnel.sh`
остаётся необязательным административным fallback; он не нужен для чата.

Локальный URL: `http://127.0.0.1:8780`. Без API доступны CLI и `protocol.py`
JSONL для проверки Agent. `bot.py --rag` использует тот же Agent на ПК.

## HTTP API

Все маршруты требуют `Authorization: Bearer ...`.

| Маршрут | Запрос / результат |
|---|---|
| `GET /health` | readiness, effective context, slots, очередь |
| `POST /sessions` | `{}` → session_id |
| `POST /chat` | `{message, session_id?, rag?, rerank?, web?}` → actual agent trace/ответ |
| `POST /sessions/reset` | `{session_id}` → reset |

История хранится отдельно для каждого authenticated client/session. В RAG
follow-up отдельный локальный Chat API разрешает ссылки по истории перед
retrieval; прежние ответы не становятся документальными источниками. Все
LLM calls и их usage сохраняются в trace, включая query resolution и repair.
Context проверяется через настоящее render/template/tokenize, включая output reserve.
API не принимает произвольный model/upstream URL или cloud generation mode.
Web default off; для полностью локального режима не включайте `web`.

| Ограничение | Default |
|---|---|
| Authenticated POST quota | 20/min на credential, 429 + Retry-After |
| Body | 512 KiB, 413 |
| Context/slot | 32768 optimized / 65536 baseline по measured selection |
| Output reserve | 6144 optimized / 8192 baseline, входит в context budget |
| Active requests | 3, совпадает с launcher slots |
| Pending queue | 10; overflow → 503 busy; ожидание слота 120 s → 503 queue_wait_timeout |
| Session TTL / count | 1800 s / 100 |
| Ошибки | 422 input/context, 502 invalid upstream, 503 unavailable, 504 timeout |

Запускайте API одним process: multiple workers удваивают независимые quotas.
В запросах header-token не передавайте в command line; используйте env/private
файл и test scripts. `API_TEST_TOKENS` — отдельные credentials для повторяемых
проверок, с теми же правилами; удалите их после проверки при необходимости.

## Настоящие сетевые проверки

Перед тестами укажите в закрытом `.env` минимум пять разных случайных
credentials через запятую в `API_TEST_TOKENS` и перезапустите API на ПК.
Пример формата: `API_TEST_TOKENS=TOKEN1,TOKEN2,TOKEN3,TOKEN4,TOKEN5`;
эти placeholders заменяются собственными значениями. Основной `API_TOKEN`
остаётся отдельным credential для чата. Все тестовые credentials получают
одинаковые права и отдельные quota counters; это позволяет проверить нагрузку
и rate limit независимо.

```bash
# HTTP(S) запросы выполняются с ПК напрямую; SSH не используется клиентом.
.venv/bin/python scripts/remote_checks.py network --client local \
 --api-url https://95.215.56.217/local-llm --output-prefix https \
 --env-file /absolute/path/to/private-api.env
# Аналогично: load, limits, overflow, final. --client vps выполняет HTTP тест
# на VPS через административный SSH; само обращение к API идёт через HTTPS.
.venv/bin/python verify_context_boundary.py \
 --api-url https://95.215.56.217/local-llm \
 --env-file /absolute/path/to/private-api.env --output results/https_context_boundary.json
.venv/bin/python verify_failures.py
.venv/bin/python -m unittest discover -s tests -v
```

Финальные доказательства HTTPS: `https_network.json`, `https_load.json`,
`https_limits.json`, `https_final.json`, `https_overflow.json`,
`https_context_boundary.json` и отчёты `https_*outage/recovery.json`.
Режим `final` сохраняет четыре RAG-реплики и plain chat/reset; request IDs
сверяются с журналом HTTP API на ПК. HTTP 200 сам по себе не означает правильный
ответ. Для превышения body limit скрипт использует curl: он читает ранний 413
во время отправки тела; urllib может получить BrokenPipe при таком отказе.
Curl также проверяет TLS и получает секрет через stdin, не argv.

Для повторов дождитесь нового quota window; load/limits/overflow используют
разные entries API_TEST_TOKENS. `verify_failures.py` запускает изолированный
synthetic upstream для 502/504/queue wait и не проверяет качество модели.
Старые `remote_*.json` сохраняют фазу до HTTPS и не подменяют новые проверки.
[Выводы](results/conclusions.md) содержат фактические результаты и ограничения.

Для автоматической проверки остановки/восстановления текущих процессов:

```bash
.venv/bin/python scripts/check_recovery.py --env-file /absolute/path/to/private-vps.env \
 --api-url https://95.215.56.217/local-llm
```

Скрипт рассчитан на текущий запуск с `runtime/restored_processes.json`: проверяет
idle очередь, принадлежность model PID и единственность своего reverse tunnel.
Не создавайте этот файл произвольными PID. При обычном ручном запуске повторите
остановку и восстановление только в своих терминалах, как описано ниже.

## Остановка и восстановление

Ctrl+C останавливает запущенные в терминалах API/бота/model/tunnel.
Gateway: `systemctl stop local-llm-experiment-gateway.service` на VPS;
`systemctl start ...` восстанавливает relay. Loopback remote port закрывается
после остановки SSH. Установленный gateway unit включён после перезапуска VPS.
Шаблоны PC model/API/tunnel units находятся в `service/`; устанавливать их
с собственными путями и закрытым env. Пока PC процессы запущены в текущей
сессии, не заявляем проверенный автозапуск после reboot ПК.

## Результат выполнения

Выбрана Q8/B optimized по 80 реальным ответам дня 29; выбор записан в
`configs/selected.json`. HTTPS доступ проверен с выключенным клиентским SSH-forward. Фактические ответы, измерения и ограничения качества:
[выводы](results/conclusions.md). Для повторения используйте matching локальные
сервисы; предоставленные PC systemd examples не означают проверенный автозапуск
после перезагрузки. Видеоинструкция: [DEMO.md](DEMO.md).

Текущий RAG содержит три полные статьи и оригинальный индекс недели 6 из 182 чанков;
[provenance](PROVENANCE.md). Source/page/quote guards проверены. Baseline 65536/
8192, optimized 32768/6144; API использует профиль configs/selected.json.
Native context/slots должны совпасть с /health configured context/slots flags.
Ожидание в очереди ограничено 120 s (503 queue_wait_timeout); Model call 600 s,
client/gateway 1800 s. Это budgets ошибок, не обещание уложить любую длинную
очередь в SLA. Embeddings8192/reranker query 1024 — отдельные лимиты.
Самопроверка+однаrevision не гарантируют семантическую корректность.
