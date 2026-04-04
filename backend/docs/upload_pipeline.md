# Upload Files Pipeline

## Overview

When a user uploads a document (PDF, DOCX, TXT), the backend runs it through a 5-step pipeline before it can be used in RAG-powered chat. The goal is to transform a raw file into searchable, semantically-indexed chunks that DeepSeek can use as context when answering questions.

```
User uploads file
      ↓
[1] FileParser       — read bytes → plain text
      ↓
[2] ChunkProcessing  — split text → overlapping chunks
      ↓
[3] EmbeddingGen     — each chunk → 1024-dim vector (DashScope API)
      ↓
[4] ESIndexing       — chunks + vectors → Elasticsearch
      ↓
[5] SaveToDB         — file metadata → PostgreSQL
```

---

## Step 1: FileParser

**What it does:** Reads the uploaded file bytes and converts them to plain text.

**Why:** Everything downstream works with plain text. We need to extract readable content from binary formats like PDF and DOCX.

**Supported formats:**
| Extension | Library | Method |
|-----------|---------|--------|
| `.pdf` | `pdfplumber` | Extracts text page by page |
| `.docx` | `python-docx` | Extracts text paragraph by paragraph |
| `.txt`, `.md` | built-in | Decode bytes as UTF-8 |

**File storage:** The raw file is also saved to disk at `backend/storage/files/{username}/{filename}` for later reference or re-processing.

**Code:** `document_service.py` → `_parse_file()`, `_save_file()`

---

## Step 2: ChunkProcessing

**What it does:** Splits the full document text into smaller overlapping chunks by word count.

**Why:** LLMs have a context window limit — you can't feed an entire 100-page PDF into a prompt. Chunking breaks the document into pieces that fit. Overlap ensures that sentences spanning a chunk boundary aren't lost.

**Parameters:**
- `chunk_size = 500` words per chunk
- `overlap = 50` words shared between adjacent chunks
- `step = chunk_size - overlap = 450` words between chunk start positions

**Example** (simplified with chunk_size=5, overlap=2):
```
words  = [w0, w1, w2, w3, w4, w5, w6, w7]
chunk0 = [w0, w1, w2, w3, w4]
chunk1 = [w3, w4, w5, w6, w7]   ← w3, w4 are the overlap
```

**Each chunk carries metadata:**
```python
{
  "text":        "first 500 words...",
  "filename":    "report.pdf",
  "username":    "alice",
  "chunk_index": 0        # position in the document
}
```

**Code:** `document_service.py` → `_chunk_text()`

---

## Step 3: EmbeddingGen

**What it does:** Calls the DashScope embedding API to convert each chunk's text into a 1024-dimensional vector (a list of 1024 floats).

**Why:** Vectors capture the *semantic meaning* of text. Two chunks about the same topic will have similar vectors even if they use different words. This enables semantic search — finding relevant chunks by meaning, not just keyword matching.

**Analogy:** Think of each chunk being placed in a 1024-dimensional space. Similar concepts cluster together. When a user asks a question, we embed the question too and find the nearest chunks in that space.

**API used:** DashScope (Alibaba Cloud) — `text-embedding-v4` model
**Endpoint:** `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
**Batch size:** 10 per request (DashScope limit)

**Output added to each chunk:**
```python
{
  "text": "...",
  "embedding": [0.0099, -0.0359, 0.0071, ...]   # 1024 floats
}
```

**Code:** `document_service.py` → `_embed_chunks()`

---

## Step 4: ESIndexing

**What it does:** Stores all chunks (text + embedding) into Elasticsearch using the bulk API.

**Why Elasticsearch?** ES is a search engine optimised for two things we need:
1. **Full-text search (BM25)** — find chunks containing specific keywords
2. **Vector/KNN search** — find chunks semantically similar to a query vector

Both are used together in HybridRanking during RAG retrieval.

**ES Index mapping** (defined in `db/es_client.py`):
```json
{
  "text":        { "type": "text" },         ← full-text search
  "filename":    { "type": "keyword" },      ← exact filter
  "username":    { "type": "keyword" },      ← scope per user
  "chunk_index": { "type": "integer" },
  "embedding":   {
    "type":       "dense_vector",
    "dims":       1024,
    "index":      true,
    "similarity": "cosine"                   ← for KNN search
  }
}
```

**Difference between ES and PostgreSQL:**
| | PostgreSQL | Elasticsearch |
|---|---|---|
| Stores | Users, Sessions, Messages, Upload metadata | Document chunks + vectors |
| Query language | SQL | JSON Query DSL |
| Good at | Transactions, relationships | Full-text + vector search |

**Code:** `document_service.py` → `_index_chunks()`, `db/es_client.py`

---

## Step 5: SaveToDB (PostgreSQL)

**What it does:** Saves one metadata record per uploaded file to the `uploads` table in PostgreSQL.

**Why, if we already have ES?** ES stores many chunks per file — it's not convenient for "list all files this user uploaded". PostgreSQL stores one clean record per file, powering the knowledge base file list in the UI.

**UploadTable schema** (`models/upload.py`):
```
id          INTEGER  PRIMARY KEY
filename    STRING   "report.pdf"
username    STRING   "alice"
file_size   INTEGER  245120  (bytes)
chunk_count INTEGER  48
status      STRING   "indexed"
created_at  DATETIME auto
```

**Powers these endpoints:**
- `GET /get_files` — list all files for the current user
- `DELETE /delete_file` — removes from ES + PostgreSQL + disk

**Code:** `document_service.py` → `_save_to_db()`, `get_files()`, `delete_file()`

---

## Where Data Lives After Upload

```
report.pdf uploaded by alice
    │
    ├── disk:         backend/storage/files/alice/report.pdf
    │
    ├── Elasticsearch: deepsearch index
    │     ├── { text: "chunk 0...", embedding: [...], filename: "report.pdf", username: "alice" }
    │     ├── { text: "chunk 1...", embedding: [...], filename: "report.pdf", username: "alice" }
    │     └── ... (one document per chunk)
    │
    └── PostgreSQL: uploads table
          └── { filename: "report.pdf", username: "alice", file_size: 245120, chunk_count: 48, status: "indexed" }
```

---

## How This Connects to RAG Chat

When alice asks "What was the Q3 revenue?":

```
1. Embed the question → question_vector (1024 floats)
2. Search ES:  find top-5 chunks where embedding ≈ question_vector
3. Build prompt:
     "Use the following context to answer the question.
      Context: [chunk1 text] [chunk2 text] ...
      Question: What was the Q3 revenue?"
4. Send to DeepSeek → stream answer back to frontend
```

This is the RAG pipeline (Step 2 in `stream_chat`) — not yet implemented, coming next.

---

## Testing Commands

### Prerequisites
```bash
# Start Elasticsearch
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

### 2. Upload a file
```bash
curl -X POST "http://localhost:8000/upload_files" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/path/to/your/document.pdf"
```

Expected response:
```json
{
  "status": "success",
  "files": [{
    "file_name": "document.pdf",
    "file_size": 245120,
    "characters": 48320,
    "chunk_count": 12,
    "status": "indexed"
  }]
}
```

### 3. List uploaded files
```bash
curl http://localhost:8000/get_files \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Verify chunks are in Elasticsearch
```bash
curl "http://localhost:9200/deepsearch/_search" \
  -H "Content-Type: application/json" \
  -d '{"query":{"match_all":{}},"_source":["filename","username","chunk_index","text"],"size":5}'
```

### 5. Delete a file
```bash
curl -X DELETE "http://localhost:8000/delete_file?file_name=document.pdf" \
  -H "Authorization: Bearer $TOKEN"
```

This removes the file from ES, PostgreSQL, and disk simultaneously.
