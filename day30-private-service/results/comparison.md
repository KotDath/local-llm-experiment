# Сравнение настроек и квантований

| Метрика | A baseline Q8 | B optimized Q8 | C baseline Q4 | D optimized Q4 |
|---|---:|---:|---:|---:|
| Correct из 10 (repeat 0) | 1 | 3 | 2 | 2 |
| Галлюцинации из 10 | 4 | 1 | 1 | 0 |
| Correct из 10 (repeat 1) | 2 | 2 | 1 | 1 |
| Галлюцинации из 10 (repeat 1) | 1 | 1 | 0 | 0 |
| Одинаковый verdict в двух повторах /10 | 8 | 9 | 9 | 9 |
| Mean total ms (20 turns) | 54751.03 | 56294.63 | 43862.57 | 56586.44 |
| p95 ms (20 turns) | 89533.48 | 86109.08 | 65547.20 | 79965.48 |
| Max total ms (20 turns) | 95397.40 | 121148.26 | 69783.45 | 130640.43 |
| Delivery failures /20 | 0 | 0 | 0 | 0 |
| Turns with truncated generation /20 | 0 | 0 | 0 | 0 |
| Generation tokens/s | 42.41 | 42.31 | 53.74 | 43.35 |
| Sampled peak RSS bytes | 9206370304 | 9156849664 | 9198452736 | 9016754176 |
| Sampled peak PSS bytes | 9162723328 | 9113253888 | 9154893824 | 8973346816 |
| Sampled whole-host used RAM bytes | 85703979008 | 85260296192 | 71869263872 | 87782912000 |
| Sampled global GPU VRAM bytes | 1028673536 | 1028562944 | 1030492160 | 1048453120 |
| Sampled global GPU GTT bytes | 48298663936 | 47528919040 | 32305401856 | 33152417792 |
| Размер GGUF bytes | 39350213152 | 39350213152 | 23259486752 | 23259486752 |
| Model launch/readiness ms | 31075.95 | 32077.44 | 16039.89 | 4007.72 |

Настройки A/B сравнивают bundle temperature/output/context/prompt, не отдельную причину каждого изменения. A/C и B/D меняют только квантование одного model snapshot.

10 одинаковых вопросов ×2, один server slot, excluded warmup, seed42, cache_prompt:false. Известный frozen corpus/evaluation; ожидания не входят в prompt. Independent grades связаны с actual answer SHA.

Host abstention учитывается в total time, generation rate=N/A. Repairs включены в cost и отдельный call count. Частичный ответ не correct. Все failures/truncations сохранены.

cache_prompt:false отключает prompt/KV reuse между измеряемыми запросами, не OS file cache. Launch/readiness — фактическое отдельное наблюдение, без заявления о сопоставимом холодном дисковом старте.

Strix Halo использует shared memory. RSS/PSS/host memory/VRAM/GTT не складываются. Sampling ~200 ms: аппаратный абсолютный максимум не заявляется. Backend, slot и configuration контролировались; host/GPU счётчики включают фоновую нагрузку системы. p95 из 20 небольших samples не является production SLA.

Выбрана Q8/B optimized: 5/20 correct, 2 найденных галлюцинаций и 0 delivery failures в этом наборе. Основание: Сначала минимум ошибок доставки, затем максимум полностью correct из20, затем минимум фактических галлюцинаций; при равенстве — меньшее среднее полное время. Известный контрольный набор; скрытый тест обобщения не заявляется.
