# День 27: отдельный агент, CLI и Telegram

Agent (`agent.py`) владеет сессией, историей и исполнением Chat API запросов.
CLI, JSONL-протокол и Telegram — независимые адаптеры к этой сущности.
Модель локальная; SDK агента, LangChain и cloud fallback отсутствуют.

## CLI без Telegram

```bash
cd day27-application
test -f .env || cp .env.example .env
chmod 600 .env
./run_model.sh
```

Если модель уже запущена одной из версий, второй launcher не нужен.
В другом терминале:

```bash
cd day27-application
python3.12 cli.py ask 'Какая столица Франции?' --json
python3.12 cli.py chat
python3.12 protocol.py
```

Для повторяемой проверки вне Telegram выполните `python3.12 verify_day27.py`: реальные
ответы добавляются в `results/cli_dialogues.jsonl`; run IDs отличают новые строки
от сохранённых. Новые ответы требуют новой независимой смысловой оценки,
прежний review относится к своему исходному запуску.

`/reset` очищает историю, `/exit` завершает чат. В JSONL-протоколе:

```json
{"id":1,"method":"session.create","params":{}}
{"id":2,"method":"agent.message","params":{"session_id":"ID_ИЗ_ОТВЕТА","message":"Меня зовут Алексей."}}
{"id":3,"method":"agent.message","params":{"session_id":"ID_ИЗ_ОТВЕТА","message":"Как меня зовут?"}}
{"id":4,"method":"session.reset","params":{"session_id":"ID_ИЗ_ОТВЕТА"}}
```

Строки отправляются одному открытому процессу; пример ID надо заменить.
Ошибочный JSON возвращает ошибку, процесс продолжает принимать следующие строки.

## Telegram на ПК

В закрытом `.env` укажите `TG_BOT_TOKEN` и `TG_ALLOWED_IDS` (user IDs через запятую).
Текущие значения уже подготовлены локально после входящего `/start`, но не
входят в поставку. Убедитесь, что не запущен другой poller того же бота.

```bash
python3.12 bot.py --inspect
python3.12 bot.py
```

Поддерживаются `/start`, `/reset`, обычные сообщения. Ответы длиннее лимита
разбиваются на части. Бот отвечает только allowlist-пользователям. При имеющемся
webhook polling не запускается молча. Токен не передавайте в argv.
`--inspect` выводит идентификаторы пользователей: используйте вне записи видео.

## Проверка и остановка

`results/agent_review_independent.json` и `protocol_independent.jsonl` содержат
независимую проверку двух сессий: разные Agent IDs, история, reset и закрытие.
Каждый ответ имеет actual usage и request trace. Простого CLI достаточно для
проверки задания без Telegram. Живой транспорт Telegram проверяется отдельно.
Ctrl+C останавливает CLI/бота/launcher в соответствующем терминале.

Генерация локальная, но Telegram передаёт сообщения через свою инфраструктуру.
Для полностью локального взаимодействия используйте CLI или JSONL.

После увеличения лимитов optimized по умолчанию: context 32768 / output 6144;
baseline 65536/8192. Для baseline запустите CTX_PER_SLOT=65536 ./run_model.sh
и выберите `cli.py ... --profile baseline`; один launcher не меняет профиль Agent.
Прямой verify_day26.py (версия 26) использует context 32768/output 6144/temp1.
Лимиты относятся к общему context, резерв ответа входит в него. Последние
реальные проверки: results/articles_recheck.log; сырые ответы сохранены.
Код не скрывает фактические ошибки модели, в том числе арифметические.
