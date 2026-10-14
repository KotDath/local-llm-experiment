# День 26: локальная LLM

Самостоятельная версия: Tiel Coder Q8, llama.cpp HTTP Chat API, отдельный
`Agent` и CLI/JSONL интерфейсы. Внешних agent SDK нет.

## Запуск

Нужны Python 3.12+ и существующая сборка llama.cpp. Веса остаются вне репозитория.
Default пути launcher соответствуют этому ПК; на другой машине задайте
`LLAMA_ROOT` и `MODEL_DIR`. Порт модели 8772, только loopback.

```bash
cd day26-local-llm
test -f .env || cp .env.example .env
chmod 600 .env
./run_model.sh
```

В другом терминале:

```bash
cd day26-local-llm
python3.12 cli.py health
python3.12 cli.py ask 'Какая столица Франции?'
python3.12 cli.py chat
python3.12 verify_day26.py
```

verify_day26.py добавляет новые три ответа в `results/day26.jsonl`; записи
разделяются полем run. Сохранённые оценки относятся к своим ответам, новый
повтор нужно оценить отдельно. `MODEL_TIMEOUT=600` в окружении увеличивает
таймаут клиента, если используемый локальный .env ещё задаёт прежние 180 s.

В чате `/reset` очищает историю, `/exit` завершает CLI. Для машинного вывода
добавьте `--json`. Слишком большой контекст отклоняется, backend timeout
показывается явно. CLI не переключается на облачную модель.

## Агент и протокол

`agent.py` владеет историей и исполняет запрос через `model.py`:
`POST /v1/chat/completions`. `chat.py` — имя адаптера для интерфейсов.
`protocol.py` принимает JSONL на stdin и возвращает JSONL на stdout.

```bash
printf '%s\n' '{"id":1,"method":"capabilities"}' \
 '{"id":2,"method":"session.create","params":{}}' | python3.12 protocol.py
```

Методы: `session.create`, `agent.message`, `session.reset`, `session.close`.
Для сообщения передайте `params.session_id` из ответа create и `params.message`.
Тот же процесс должен оставаться открыт для последующих запросов.

## Проверенные результаты

`results/day26.jsonl` содержит реальные три запроса и backend usage/timings.
`results/articles_recheck_review_independent.json` — проверка повторного запуска
после увеличения лимитов. `independent_review.json` и `cli_independent.jsonl`
сохраняют прежнюю независимую проверку и не доказывают новые лимиты.
Хеш Q8 совпал с закреплённой ревизией:
`8384abe448e6159b1d43249be9c51f68fe5771e962bb39e3ee89ad1215385310`.
Модель работает локально и отвечает; факт/силлогизм корректны, в прямой
проверке задачи с зависимостями temperature 1 ошиблась (9 ч вместо 8). Ошибка не скрыта и не заменена
заранее подготовленным ответом. Подробности — [выводы](results/conclusions.md).

## Остановка

Ctrl+C в терминале launcher останавливает только этот процесс модели.
Не запускайте вторую копию на занятом порте. Версии 27–30 могут использовать
уже работающий backend; каждая содержит собственный launcher.

После увеличения лимитов optimized по умолчанию: context 32768 / output 6144;
baseline 65536/8192. Для baseline запустите CTX_PER_SLOT=65536 ./run_model.sh
и выберите `cli.py ... --profile baseline`; один launcher не меняет профиль Agent.
Прямой verify_day26.py (версия 26) использует context 32768/output 6144/temp1.
Лимиты относятся к общему context, резерв ответа входит в него. Последние
реальные проверки: results/articles_recheck.log; сырые ответы сохранены.
Код не скрывает фактические ошибки модели, в том числе арифметические.
