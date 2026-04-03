# Stream Chat (RAG) Pipeline

## Overview

When a user sends a message in a chat session, the backend runs it through a 5-step pipeline before streaming a response. The goal is to find the most relevant document chunks the user has uploaded, inject them as context into the LLM prompt, and stream back a grounded answer.

```
User sends message
      ↓
[1] SaveQuestion     — persist user question to PostgreSQL immediately
      ↓
[2] EmbedQuestion    — question → 1024-dim vector (DashScope API)
      ↓
[3] ESQuery          — hybrid search: KNN (vector) + BM25 (keyword)
      ↓
[4] PromptConstruct  — inject retrieved chunks as numbered context
      ↓
[5] LLMStream        — DeepSeek streams answer tokens via SSE
      ↓
[6] SaveAnswer       — persist full answer + source refs to PostgreSQL
```

**Frontend receives:** a stream of SSE events (`data: {"content": "..."}`) followed by `data: [DONE]`.

---

## Two Separate API Clients

This service uses **two different AI providers** — one for embeddings, one for LLM chat. Both use the same OpenAI Python SDK, just with different `base_url` and `api_key`.

```python
# Embedding client — DashScope (Alibaba Cloud)
# Used in: _embed_question()
embedding_client = AsyncOpenAI(
    api_key=settings.EMBEDDING_API_KEY,
    base_url=settings.EMBEDDING_BASE_URL,   # https://dashscope.aliyuncs.com/compatible-mode/v1
)

# LLM chat client — DeepSeek (or OpenAI)
# Used in: stream_chat()
client = AsyncOpenAI(
    api_key=settings.DASHSCOPE_API_KEY,
    base_url=settings.DASHSCOPE_BASE_URL,   # https://api.deepseek.com
)
```

**Why two clients?**
Embeddings and chat are provided by different vendors. DashScope's `text-embedding-v4` model produces the vectors — so question embeddings must use the same model and API as document embeddings (set up in `document_service.py`). The LLM (DeepSeek) is used only for generating the final answer.

---

## Step 1: SaveQuestion

**What it does:** Persists the user's question to PostgreSQL immediately, before any AI calls.

**Why:** If the server crashes mid-stream, the question is already saved. The answer is updated later in Step 6.

```python
message_id = str(uuid.uuid4())
msg_row = Message(
    message_id=message_id,
    session_id=session_id,
    user_question=message,
    model_answer="",          # placeholder, filled in Step 6
)
self.db.add(msg_row)
await self.db.commit()
```

**Table:** `messages` in PostgreSQL/SQLite
**Code:** `chat_service.py` → `stream_chat()` Step 1

---

## Step 2: EmbedQuestion

**What it does:** Converts the user's question into a 1024-dimensional float vector using DashScope.

**Why:** To search Elasticsearch by semantic similarity, we need the question and document chunks to live in the same vector space. Both are embedded with the same model (`text-embedding-v4`), so their vectors are directly comparable.

```python
async def _embed_question(self, question: str) -> list[float]:
    response = await embedding_client.embeddings.create(
        model=settings.EMBEDDING_MODEL,    # text-embedding-v4
        input=question,
        dimensions=1024,
        encoding_format="float",
    )
    return response.data[0].embedding     # list of 1024 floats
```

**Analogy:** The question is placed into the same 1024-dimensional space as every uploaded document chunk. Finding relevant chunks = finding the nearest neighbours in that space.

**API:** DashScope — `text-embedding-v4`
**Code:** `chat_service.py` → `_embed_question()`

---

## Step 3: ESQuery — Hybrid Search

**What it does:** Searches Elasticsearch for the top-K most relevant chunks using two strategies simultaneously, then merges the results.

**Why two strategies?**

| Strategy | Finds | Misses |
|---|---|---|
| **KNN (vector)** | Semantically similar chunks ("revenue" ≈ "income") | Exact keyword matches with different phrasing |
| **BM25 (keyword)** | Chunks containing the exact words in the question | Conceptually similar but differently-worded chunks |

Combining both gives better recall than either alone.

```python
async def _retrieve_chunks(self, question: str, username: str, top_k: int = 5):
    question_vector = await self._embed_question(question)

    # Run both searches in parallel (asyncio.gather)
    knn_resp, bm25_resp = await asyncio.gather(
        es.search(index=settings.ES_INDEX, body={
            "knn": {
                "field":          "embedding",
                "query_vector":   question_vector,
                "k":              top_k,
                "num_candidates": top_k * 5,
                "filter":         {"term": {"username": username}},  # user isolation
            },
            "_source": ["text", "filename", "chunk_index"],
            "size": top_k,
        }),
        es.search(index=settings.ES_INDEX, body={
            "query": {
                "bool": {
                    "must":   {"match": {"text": question}},
                    "filter": {"term": {"username": username}},      # user isolation
                }
            },
            "_source": ["text", "filename", "chunk_index"],
            "size": top_k,
        }),
    )
```

**User isolation:** Both queries filter by `username` so users can only retrieve chunks from their own uploaded documents.

### Merging KNN + BM25 Results

ES's built-in RRF (Reciprocal Rank Fusion) requires a paid license. We implement manual deduplication instead:

```python
seen_ids: dict[str, dict] = {}
for hit in knn_resp["hits"]["hits"] + bm25_resp["hits"]["hits"]:
    doc_id = hit["_id"]
    score  = hit["_score"] or 0.0
    if doc_id not in seen_ids or score > seen_ids[doc_id]["score"]:
        seen_ids[doc_id] = {
            "text":        hit["_source"]["text"],
            "filename":    hit["_source"]["filename"],
            "chunk_index": hit["_source"]["chunk_index"],
            "score":       score,
        }

# Sort by score descending, return top_k
chunks = sorted(seen_ids.values(), key=lambda x: x["score"], reverse=True)[:top_k]
```

**Result:** A list of up to 5 chunks: `[{ text, filename, chunk_index, score }, ...]`

**Code:** `chat_service.py` → `_retrieve_chunks()`

---

## Step 4: PromptConstruct

**What it does:** Builds the `messages` array to send to the LLM, injecting retrieved chunks as numbered context.

**Why:** The LLM has no access to the user's files directly. We paste the relevant text into the prompt so it can answer based on actual document content. This is the core of RAG.

```python
def _build_prompt(self, question: str, chunks: list[dict]) -> list[dict]:
    if not chunks:
        # No documents uploaded — plain chat fallback
        return [{"role": "user", "content": question}]

    # Format chunks as numbered references
    context_text = "\n\n".join(
        f"[{i+1}] (from {c['filename']}):\n{c['text']}"
        for i, c in enumerate(chunks)
    )

    system_prompt = (
        "You are a helpful assistant. Answer the user's question based on "
        "the provided context documents. If the answer is not in the context, "
        f"say so honestly.\n\nContext:\n{context_text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": question},
    ]
```

**Example prompt sent to DeepSeek:**
```
[system]
You are a helpful assistant. Answer the user's question based on the
provided context documents. If the answer is not in the context, say so honestly.

Context:
[1] (from report.pdf):
Machine learning is a subset of artificial intelligence...

[2] (from notes.txt):
Gradient descent is an optimisation algorithm...

[user]
What is gradient descent?
```

**Fallback:** If the user hasn't uploaded any documents, `chunks` is empty and the question is sent as plain chat with no system prompt.

**Code:** `chat_service.py` → `_build_prompt()`

---

## Step 5: LLMStream

**What it does:** Sends the constructed prompt to DeepSeek and streams tokens back to the frontend as SSE events.

**Why streaming?** Streaming lets the frontend display words as they arrive rather than waiting for the full response. The user sees the answer being typed in real time.

```python
full_answer = ""
try:
    stream = await client.chat.completions.create(
        model=settings.LLM_MODEL,     # deepseek-chat
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            full_answer += token
            yield f"data: {json.dumps({'content': token})}\n\n"   # SSE format
except Exception as e:
    error_msg = f"[LLM Error: {e}]"
    full_answer = error_msg
    yield f"data: {json.dumps({'content': error_msg})}\n\n"
```

**SSE format:** Each event is `data: <json>\n\n`. The frontend splits on `\n\n` and parses each JSON.

**Example events sent to frontend:**
```
data: {"content": "Gradient"}
data: {"content": " descent"}
data: {"content": " is"}
...
data: [DONE]
```

**API:** DeepSeek — `deepseek-chat` model via `https://api.deepseek.com`
**Code:** `chat_service.py` → `stream_chat()` Steps 4–5

---

## Step 6: SaveAnswer

**What it does:** After streaming completes, saves the full answer and the source chunk references to PostgreSQL.

**Why:** The full answer is now available (`full_answer` was built by concatenating all tokens). We also save which document chunks were used as sources, so the frontend can display citations.

```python
msg_row.model_answer = full_answer
msg_row.documents = json.dumps([
    {"filename": c["filename"], "chunk_index": c["chunk_index"]}
    for c in chunks
])
await self.db.commit()

yield "data: [DONE]\n\n"
```

**`Message.documents`** is a JSON string like:
```json
[
  {"filename": "report.pdf", "chunk_index": 0},
  {"filename": "report.pdf", "chunk_index": 3}
]
```

This powers the source citation UI — the frontend knows exactly which document chunks were used to generate the answer.

**Code:** `chat_service.py` → `stream_chat()` Step 5

---

## Full Flow Summary

```
User: "What is gradient descent?"
          │
          ▼
[1] SaveQuestion → messages table: { question: "What is gradient descent?", answer: "" }
          │
          ▼
[2] EmbedQuestion → DashScope → [0.023, -0.041, 0.017, ...] (1024 floats)
          │
          ▼
[3] ESQuery:
    ┌─── KNN search (vector similarity) ─────────────────────────────────┐
    │    top-5 chunks where embedding ≈ question_vector                  │
    │    filtered by username="alice"                                     │
    └─────────────────────────────────────────────────────────────────────┘
    ┌─── BM25 search (keyword match) ─────────────────────────────────────┐
    │    top-5 chunks where text matches "gradient descent"               │
    │    filtered by username="alice"                                     │
    └─────────────────────────────────────────────────────────────────────┘
    Merge: deduplicate by ES _id, keep highest score, sort, return top-5
          │
          ▼
[4] PromptConstruct →
    system: "Context:\n[1] (from report.pdf):\nGradient descent is..."
    user:   "What is gradient descent?"
          │
          ▼
[5] LLMStream → DeepSeek → SSE stream:
    data: {"content": "Gradient"}
    data: {"content": " descent is..."}
    ...
    data: [DONE]
          │
          ▼
[6] SaveAnswer → messages table: { answer: "Gradient descent is...", documents: "[...]" }
```

---

## Configuration

Set in `.env` (two separate providers):

```env
# LLM: DeepSeek (chat)
DASHSCOPE_API_KEY=sk-...         # DeepSeek API key
DASHSCOPE_BASE_URL=https://api.deepseek.com
LLM_PROVIDER=dashscope
LLM_MODEL=deepseek-chat

# Embedding: DashScope (Alibaba Cloud)
EMBEDDING_API_KEY=sk-...         # DashScope API key (different from above)
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
```

---

## Testing Commands

### Prerequisites

```bash
# Start Elasticsearch
docker start es   # if already created
# or
docker run -d --name es \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -p 9200:9200 \
  elasticsearch:8.11.3

# Start backend
cd backend
python3 -m uvicorn app_main:app --port 8000
```

### 1. Register and login

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123"}'

TOKEN=$(curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### 2. Upload a document

```bash
curl -X POST "http://localhost:8000/upload_files" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/path/to/your/document.pdf"
```

### 3. Create a session

```bash
SESSION=$(curl -s -X POST http://localhost:8000/create_session \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "Session: $SESSION"
```

### 4. Send a chat message and stream the response

```bash
curl -N "http://localhost:8000/chat_on_docs?session_id=$SESSION" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is gradient descent?"}'
```

Expected output (streaming SSE):
```
data: {"content": "Gradient"}
data: {"content": " descent"}
data: {"content": " is an optimisation algorithm..."}
...
data: [DONE]
```

### 5. Verify the message was saved to the database

```bash
curl "http://localhost:8000/get_messages?session_id=$SESSION" \
  -H "Authorization: Bearer $TOKEN"
```

Expected response includes:
```json
[{
  "user_question": "What is gradient descent?",
  "model_answer": "Gradient descent is an optimisation algorithm...",
  "documents": "[{\"filename\": \"document.pdf\", \"chunk_index\": 2}]"
}]
```

### 6. Verify chunks are in Elasticsearch

```bash
# See what chunks were indexed for this user
curl "http://localhost:9200/deepsearch/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {"term": {"username": "alice"}},
    "_source": ["filename", "chunk_index", "text"],
    "size": 5
  }'
```

### 7. Test plain chat (no documents uploaded)

Create a new session as a fresh user with no uploads, then send a message. The system falls back to plain LLM chat with no system prompt injection.

---

## Where Data Lives After a Chat Turn

```
User asks "What is gradient descent?"
    │
    ├── PostgreSQL: messages table
    │     └── { session_id, user_question: "...", model_answer: "...",
    │           documents: '[{"filename": "ml.pdf", "chunk_index": 3}]' }
    │
    └── (read-only during chat) Elasticsearch: deepsearch index
          ├── { text: "Gradient descent is...", embedding: [...], filename: "ml.pdf" }
          └── ... (indexed during upload, searched during chat)
```

**Code:** `services/chat_service.py`
