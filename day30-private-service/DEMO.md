# Демонстрация дня 30

Ориентир: 6:00–8:00; увеличить по фактической длительности.

1. Показать на ПК Q8/B, Agent/API и loopback порты. На VPS — Caddy,
   stdlib gateway и внутренний reverse SSH; модели и индекса на VPS нет.
2. На клиенте без SSH открыть интерактивный HTTPS чат:

```bash
python3 cli.py health --env-file runtime/https_client.env
python3 cli.py chat --env-file runtime/https_client.env --rag
```

Задать вопрос по MemGPT, уточнение и неизвестный факт. `/reset`, затем `/exit`.
Публичный URL: https://95.215.56.217/local-llm. Сертификат проверяется штатно.

3. Показать `results/https_final.json` и независимую связь request IDs с PC
   журналом; оценку смысла отделить от HTTP 200.
4. Показать `https_load.json`: 5 и 10 одновременных реальных запросов.
5. Показать `https_limits.json`: auth401, body413, context422,
   rate429/Retry-After и новый ответ после окна quota.
6. Показать точный boundary в `https_context_boundary.json`: prompt26624 +
   reserve6144 = context32768 принят; prompt26625 отклонён без generation.
7. Показать `https_overflow.json`, реальные `https_*outage/recovery.json`.
   При повторе останавливать только собственный model/tunnel и восстанавливать
   выбранную конфигурацию. Не останавливать чужие OCR/Caddy/Ollama сервисы.
8. Synthetic `failure_injection.json` для 502/504/queue wait503 назвать отдельно.

SSH внутри соединяет private loopback ПК с VPS, сохраняя синхронный Chat API.
Клиентский туннель не нужен. Ollama/llama.cpp endpoints не публикуются.
Скрыть .env, credentials, private keys, Telegram IDs и bearer headers.
Сохранённые результаты показывать как результаты запуска с датой.

Обновлениеv2: показать results/quality-v2/comparison.md (36/40correct,
три неподтверждённых факта, отклонённый filter34/40). Все старые A–D и
load/limits/outage назвать измерениями прежнего core37e; свежие HTTPSдиалоги
core82 в quality_v2_https_network/final и независимомaudit дня30. Полная
selected-quote support там2/4 при правильных основныхответах4/4.
Cloudfinal7/10 измерен надругом наборе; прямого сравненияпроцентов не делать.
Подробный отчёт: [REPORT](../REPORT.md).
