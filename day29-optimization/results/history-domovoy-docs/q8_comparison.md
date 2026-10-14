# Q8: промежуточное сравнение настроек

Новый полный A/B rerun после исправления истории Agent. Q4 условия C/D ещё не измерены; эти данные не заменяют полную матрицу.

| Метрика | A baseline Q8 | B optimized Q8 |
|---|---:|---:|
| Correct из 10 (repeat0) | 7 | 8 |
| Галлюцинации из 10 | 1 | 0 |
| Mean total ms (20 turns) | 17808.94 | 15890.4 |
| Generation tokens/s | 41.83 | 42.31 |
| Sampled peak RSS bytes | 3810848768 | 3827486720 |
| Actual cached tokens | 0 | 0 |

A run `A-1791931097876872033`, B run `B-1791931493539589446`.
Core SHA `f1a41f303db90a8efbae7c593bca221e7b211391c28cd7ec61e617517132eabf`.

Один server slot, seeded identical questions, warmup исключён, prompt cache off. Время измерено фактически; фоновая загрузка Q4 может влиять на IO/host memory. Peak RSS не включает всей GPU shared memory; counters не складываются.
