# Приёмка дней 26–30

Новая проверка качества завершена:36/40 correct, три неподтверждённых факта.
[Текущий отчёт](REPORT.md). Таблица ниже включает исторические измеренияcore37e;
она не утверждает новый controlled benchmarkbaseline/Q4 дляcore82.

Новый корпус — три полные научные статьи; context/output увеличены в четыре раза.
Старые результаты Domovoy хранятся отдельно. Основание: `../tasks.md` и согласованные
дополнения пользователя; видеофайл записывается отдельно, здесь инструкции.

| Требование | Фактическое доказательство | Состояние |
|---|---|---|
| Пять самостоятельных версий, README/PLAN/DEMO | day26–30; общий VIDEO.md | Подготовлено |
| Собственный Agent, HTTP Chat API, без SDK/LangChain | agent.py/model.py/protocol.py | Выполнено |
| День26: локальная Tiel Coder, три разных запроса | articles_recheck.log/day26.jsonl, независимая оценка | Выполнено; арифметическая ошибка сохранена |
| День27: local приложение, history/reset/isolation | articles_recheck.log/cli_dialogues.jsonl | Выполнено через CLI/JSONL; Telegram transport отдельно |
| Индекс недели 6, три статьи и страницы PDF | day28/PROVENANCE.md, data/week6/fixed.jsonl | 182 чанка, оригинальные байты |
| Rebuild, UTF-16, pages, drift/citation guards | articles_rebuild.json/articles_core_tests.txt/rag_guards.json | Выполнено; 15 тестов прошли |
| День28: M0/M1/M2, качество/скорость/повторы | rag_comparison.csv, независимые grades, stability.json | Выполнено; M1 переиспользует тот же B/repeat0 |
| Облачное сравнение при доступном API | deepseek-flash, cloud_answers.jsonl/cloud_comparison.md | 10 фактических ответов; 5 failures цитат явно учтены |
| Optional freshness сайта | web_check.json | Три pinned PDF совпадают; версии проверены |
| День29: параметры, prompt, Q8/Q4 | results/model_pair_metadata.json | Выполнено; одна ревизия, разные quant |
| День29: одинаковые вопросы, ресурсы/качество | 80 ответов A–D ×2, benchmark.csv/comparison.md | Выполнено; независимые оценки; выбран Q8/B |
| День30: VPS gateway, LLM/RAG только ПК | vps_audit.json/https_deployment.json | Выполнено; HTTPS, внутренний reverse SSH |
| День30: сеть, чат/load5/load10 | https_network.json/https_load.json, PC receipts | Выполнено; клиентский SSH-forward выключен |
| День30: auth/body/context/rate | https_limits.json/https_context_boundary.json | 401/413/422/429 и восстановление200; точный новый boundary |
| День30: финальный RAG чат/overflow/отказы | https_final/overflow/outage/recovery.json | Выполнено; 9/15 overflow200, 6 контролируемых503; outage503/recovery200 |
| Выводы и видеоинструкции | results/conclusions.md, DEMO.md, VIDEO.md | Подготовлено; syntax/secret/runtime аудит пройден |

Историческое качествоcore37e оценивается отдельно от запуска: выбранная настройка дала 5/20
полностью правильных ответов на известном наборе. Self-review и буквальные
цитаты не гарантируют смысловую поддержку всех утверждений. Измеренного
ускорения baseline→optimized нет. Synthetic error-path тесты не выдаются за
реальную генерацию. Автозапуск после reboot ПК не проверялся.

Core82: новый набор20×2 дал36/40 correct,3неподтверждённых факта,0deliveryfailures.
Свежий HTTPS:4/4 основных RAGвопроса верны,2/4 fullygrounded; history/reset и
10requests/29LLMcalls подтверждены журналомПК. Focusfilter отклонён:34/40.
Deepseek-flash finalgolden10:7correct,2partial,1protocolfailure,0hallucinations.
Новых load/limits/quant/test серий после просьбы пользователя не запускали.
