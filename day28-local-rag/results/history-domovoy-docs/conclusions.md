# Выводы дня 28

Реальный индекс недели 6 импортирован: 12 документов / 128 chunks / 1024D.
Fingerprint установленной Qwen embedding модели совпал. Footer/hash/vector/UTF-16
checks прошли. Fresh rebuild произведён, 128 chunks, индекс повторно открыт;
при смене generation старая retrieval calibration отклоняется.

Полностью локальная цепочка Agent → retrieval → Tiel Coder → grounded output
работает через CLI/JSONL без Telegram. BGE реально выполняет classifier inference,
raw logits проверяются отдельным gateway. Web off не вызывает GitHub/cloud;
tokenizers работают local_files_only. Web on проверил README на GitHub: текст
совпадает с frozen hash, timestamp и blob SHA сохранены в web_check.json.

По независимой оценке: M0 2/10, M1 9/10, M2 6/10 полностью приемлемых ответов.
M1/M2 — 0 найденных factual hallucinations, но частичные ответы и ложные отказы
есть. M1 выбран default; reranking опциональный, превосходство не заявляется.
Отдельные dev/early raw-query ошибки сохранены; topic vocabulary настроен на dev,
пороги midpoint исключают привязку к точному float boundary.

Cloud deepseek-flash реально выполнен через HTTP с ключом shell: 7/10 delivered
приемлемых, две literal validation failures. Найдены два unsupported claim ответа
(один доставлен, один отвергнут validator); они включены в hallucination count.
Подробное сравнение/ограничения
в cloud_comparison.md, sourceSHA и semantic reasons в independent reports.

Constrained schema не заменяет semantic entailment/completeness: dev показывает
частичные многоаспектные ответы. Все ошибки сохранены, их нельзя выдавать за
безошибочную систему. Тесты повреждённого footer, ложной quote/ID и UTF-16 прошли.

Повторы Q02/Q03/Q10 сохранены в stability.json: correct/correct, correct/partial, appropriate_refusal/appropriate_refusal. Повторы заново выполнены после исправления истории на том же core SHA f1a41f303db90a8efbae7c593bca221e7b211391c28cd7ec61e617517132eabf. Два реальных повтора Q8optimized не гарантируют production reliability.

Естественный RAG dialogue проверен отдельно после исправления query resolution: исходные четыре вопроса дали 4/4 содержательно правильных ответа, шесть реальных локальных ChatAPI calls; небольшая языковая неточность turn3 сохранена. Два прежних неудачных прогона сохранены. История разрешает тему запроса, documentary evidence — только текущие документы. Stateless M0/M1/M2 данные выше получены до этого исправления; их input payload и retrieval при пустой history не изменились.

Stateless prompt validation сохранена в stateless_prompt_validation.json: все 10 вопросов/профилей/sent chunks совпали с новым B, primary prompt hash и token count совпали во всех девяти генерациях; Q10 — host refusal. Итоговый текст совпал только у Q10. Результаты M1 и B — разные реальные прогоны; полная битовая детерминированность и идентичность исторического server/sampler state не заявляются.
