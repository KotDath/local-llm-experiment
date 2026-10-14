# Локальные embeddings и reranking

Запускайте из корня этой самостоятельной директории дня. Flutter, Dart и
исходники Domovoy для запуска не нужны. Код gateway заимствован из недели 6;
происхождение и hashes описаны в `../PROVENANCE.md`.

Нужны Python 3.12, `uv`, запущенная Ollama на 127.0.0.1:11434 и
`qwen3-embedding:0.6b`. При первоначальной подготовке `./setup.sh` устанавливает
фиксированные зависимости из requirements.txt и выполняет
local_models/prepare_tokenizers.py. После подготовки tokenizer inference
использует `local_files_only=True` и не скачивает модели. Веса BGE остаются
во внешнем каталоге.

В двух отдельных терминалах из корня дня:

```bash
./local_models/run_bge.sh
```

```bash
RAG_RERANK_MODEL_PATH=/home/kotdath/.local/share/domovoy-rag/models/bge-reranker-v2-m3-f16.gguf \
 .venv/bin/python -m uvicorn app:app --app-dir local_models \
 --host 127.0.0.1 --port 8765 --no-access-log
```

Не запускайте повторно сервисы на занятых портах. run_bge.sh принимает
LLAMA_ROOT и BGE_MODEL через окружение; gateway получает тот же GGUF через
RAG_RERANK_MODEL_PATH. На другой машине замените оба пути согласованно.
Ctrl+C останавливает собственный процесс соответствующего терминала.

Gateway /health declares embedding fingerprint, 1024D и tokenizer identity.
Query получает Qwen instruction, passage — пустой prefix; vectors нормируются,
Ollama truncate:false. Замена model digest приводит к fingerprint drift и требует
явной пересборки индекса. Tokenizer revisions закреплены в models.lock.json.

BGE F16: SHA256
`0c5784a1f3402d93c42deb0593aaeb38edb08a511d30cde18af84ab64a164a8a`,
llama.cpp build `b10679-50f068fff`, rank pooling, loopback8766,8192 tokens/pair.
Query максимум1024tokens; raw logits не являются cosine или вероятностями.
Gateway проверяет weights/backend identity, реальные token IDs и pair usage;
ошибки/несовместимый backend показываются явно. /v1/reranker/health доступен
только при рабочем локальном BGE. Tokenizer сам по себе не является reranking.

Калибровка из старого Domovoy корпуса не используется для трёх статей.
Текущие tests/evaluate_rag.py и команды воспроизведения описаны в ../README.md.
