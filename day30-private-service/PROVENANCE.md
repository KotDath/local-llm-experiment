# Корпус статей и воспроизводимость

Три PDF из domovoy/challenge:eval/rag/arxiv_sources.json:
MemGPT2310.08560v2 (13pages), MemoryBank2305.10250v3 (11),
Generative Agents2304.03442v2 (22). Копии data/papers/*.pdf; полные byteSHA,
размеры, canonical textSHA, версии и UTF16page_starts — data/corpus/manifest.json.
Canonicaltext взят из originalnative индекса; контрольные символы извлечения и
математические surrogatecharacters сохранены. PDFtextlayer не равен пониманию
изображений/графиков: страницы и формулы дополнительно проверены при подготовке рубрики.

Индекс data/week6/fixed.jsonl **байт-в-байт** из финального native запуска дня25:
/home/kotdath/.local/share/domovoy/ru.kotdath.domovoy/rag-jsonl-v1/122700692ddbd074c4cfe16684108b9c44b5755810f1c8f929b475c948f36065/generation-81036b31677ccca900fd097527d17a3e.jsonl.
SHA256 ba0e9524fb2947802b4121f99944b40b65f936995feafcad77742fe55b4690f3;
generation29297553d6b1cd8636c4024a587544c8320b17bcfb0582d35216f54703e203eb;
182chunks (48MemGPT/33MemoryBank/101GenerativeAgents), fixed384/64,1024D.
Связан с evidence/day25/dialogues-pro-disclosed.jsonl.config.json.
Python проверяет footer, documents/revisions, finite normalizedvectors, UTF16spans
и page bounds. Read-only enrichment добавляет title/version/PDFsha/page mapping,
не меняет сохранённые vectors/IDs/generation. Freshrebuild создаёт собственную
generation; сохраняет канонические тексты и страницы, проверяет оригинальныеPDFSHA.

Embeddings: Ollamaqwen3-embedding:0.6b; index-compatible fingerprintdf2af910c83efd01d39f7ba4012e24bdc1ba98281ad65efff841fd025148279d.
BGE/tokenizer/model revisions и runtimehash в local_models/models.lock.json.
Tokenizer cache local_files_only/offline. Originallocal model gateway из challenge
адаптирован; Agent/RAG/search/grounding написаны на Python без agent SDK.

Dev8 и контрольные10вопросов подготовлены отдельно по полнымPDF. Эталонные
facts/quotes/pages находятся только в eval и используются проверяющим.
Knowncontrol и первоначальные failedruns раскрыты; hidden generalization не заявляется.
Точная цитата и page mapping проверяются программой, смысл — независимой оценкой.
