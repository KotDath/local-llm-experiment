# Сравнение настроек и квантований

| Метрика | A baseline Q8 | B optimized Q8 | C baseline Q4 | D optimized Q4 |
|---|---:|---:|---:|---:|
| Correct из 10 (repeat 0) | 7 | 8 | 7 | 7 |
| Галлюцинации из 10 | 1 | 0 | 0 | 0 |
| Correct из 10 (repeat 1) | 6 | 8 | 7 | 6 |
| Галлюцинации из 10 (repeat 1) | 2 | 0 | 0 | 1 |
| Одинаковый verdict в двух повторах /10 | 9 | 8 | 10 | 8 |
| Mean total ms (20 turns) | 17808.94 | 15890.40 | 12521.86 | 15887.41 |
| p95 ms (20 turns) | 32794.98 | 32807.93 | 24825.99 | 22223.62 |
| Max total ms (20 turns) | 39002.88 | 32859.02 | 28429.93 | 65941.83 |
| Delivery failures /20 | 0 | 0 | 0 | 1 |
| Turns with truncated generation /20 | 0 | 0 | 0 | 1 |
| Generation tokens/s | 41.83 | 42.31 | 54.03 | 52.75 |
| Sampled peak RSS bytes | 3810848768 | 3827486720 | 3788488704 | 3951362048 |
| Sampled peak PSS bytes | 3767215104 | 3783849984 | 3744506880 | 3907691520 |
| Sampled whole-host used RAM bytes | 82782318592 | 78131077120 | 63170437120 | 62489497600 |
| Sampled global GPU VRAM bytes | 1037172736 | 1033940992 | 1032040448 | 1042706432 |
| Sampled global GPU GTT bytes | 46924963840 | 46734921728 | 30565486592 | 30406225920 |
| Размер GGUF bytes | 39350213152 | 39350213152 | 23259486752 | 23259486752 |
| Model launch/readiness ms | 28069.91 | 30066.58 | 5014.65 | 5013.65 |

Настройки A/B сравнивают bundle temperature/output/context/prompt, не отдельную причину каждого изменения. A/C и B/D меняют только квантование одного model snapshot.

10 одинаковых вопросов ×2, один server slot, excluded warmup, seed42, cache_prompt:false. Известный frozen corpus/evaluation; ожидания не входят в prompt. Independent grades связаны с actual answer SHA.

Host abstention учитывается в total time, generation rate=N/A. Repairs включены в cost и отдельный call count. Частичный ответ не correct. Все failures/truncations сохранены.

cache_prompt:false отключает prompt/KV reuse между измеряемыми запросами, не OS file cache. Launch/readiness — фактическое отдельное наблюдение, без заявления о сопоставимом холодном дисковом старте.

Strix Halo использует shared memory. RSS/PSS/host memory/VRAM/GTT не складываются. Sampling ~200 ms: аппаратный абсолютный максимум не заявляется. Фоновая загрузка Q4 могла влиять на host RAM/IO; backend/slot/config контролировались. p95 из 20 небольших samples не является production SLA.

Выбрана Q8/B optimized: 16/20 correct, 0 найденных галлюцинаций и 0 delivery failures в этом наборе. Приоритет — полнота и надёжность ответа. Q4 меньше и быстрее в backend generation, однако C=14/20, D=13/20 с одним delivery failure и одной галлюцинацией. Это вывод по данному набору, не универсальное превосходство Q8.
