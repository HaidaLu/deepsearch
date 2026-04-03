# services/chat_service.py — Chat business logic
# Java equivalent: @Service ChatService
#
# From chart.svg:
#   ChatCore → LLMCall → (OpenAI / DashScope)
#            → RetrievalStep → RetrievalCore → RAGDealer → ESQuery → HybridRanking
#            → PromptConstruct → StreamResponse
#            → SaveToDB → PostgreSQL

import asyncio
import json
import uuid
from typing import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.es_client import es
from models.message import Message
from models.session import Session

# Embedding client — same setup as document_service, reused for question embedding
embedding_client = AsyncOpenAI(
    api_key=settings.EMBEDDING_API_KEY or settings.DASHSCOPE_API_KEY,
    base_url=settings.EMBEDDING_BASE_URL,
)

# Both OpenAI and DashScope/DeepSeek use the same SDK — just different base_url
if settings.LLM_PROVIDER == "openai":
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
else:
    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
    )


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(self, user_id: int) -> dict:
        session_id = str(uuid.uuid4())
        new_session = Session(session_id=session_id, user_id=user_id)
        self.db.add(new_session)
        await self.db.commit()
        return {"session_id": session_id}

    async def get_sessions(self, user_id: int) -> dict:
        result = await self.db.execute(
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.created_at.desc())
        )
        sessions = result.scalars().all()
        return {
            "sessions": [
                {
                    "session_id": s.session_id,
                    "session_name": s.session_name,
                    "created_at": s.created_at.isoformat(),
                }
                for s in sessions
            ]
        }

    async def get_messages(self, session_id: str) -> list:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        messages = result.scalars().all()
        return [
            {
                "message_id": m.message_id,
                "session_id": m.session_id,
                "user_question": m.user_question,
                "model_answer": m.model_answer,
                "think": m.think,
                "documents": m.documents,
                "recommended_questions": m.recommended_questions,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]

    # ── RAG Step 1: EmbedQuestion ─────────────────────────────────────────────

    async def _embed_question(self, question: str) -> list[float]:
        """
        Convert the user's question into a 1024-dim vector using DashScope.
        Same model as document embedding so vectors are in the same space
        and similarity comparison works correctly.

        Java equivalent: embeddingService.embed(String question)
        """
        response = await embedding_client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=question,
            dimensions=1024,
            encoding_format="float",
        )
        return response.data[0].embedding

    # ── RAG Step 2: ESQuery — Hybrid Search ───────────────────────────────────

    async def _retrieve_chunks(self, question: str, username: str, top_k: int = 5) -> list[dict]:
        """
        Hybrid search: KNN (vector) + BM25 (keyword) combined.

        - KNN finds chunks semantically similar to the question vector
        - BM25 finds chunks containing the same keywords
        - Both are filtered by username so users only see their own documents
        - Results are merged and deduplicated by ES's RRF (Reciprocal Rank Fusion)

        Java equivalent: elasticsearchRepository.hybridSearch(questionVector, questionText, username)

        Returns list of: { text, filename, chunk_index, score }
        """
        question_vector = await self._embed_question(question)

        # Run KNN (vector) and BM25 (keyword) searches in parallel
        knn_resp, bm25_resp = await asyncio.gather(
            es.search(
                index=settings.ES_INDEX,
                body={
                    "knn": {
                        "field":          "embedding",
                        "query_vector":   question_vector,
                        "k":              top_k,
                        "num_candidates": top_k * 5,
                        "filter":         {"term": {"username": username}},
                    },
                    "_source": ["text", "filename", "chunk_index"],
                    "size": top_k,
                },
            ),
            es.search(
                index=settings.ES_INDEX,
                body={
                    "query": {
                        "bool": {
                            "must":   {"match": {"text": question}},
                            "filter": {"term": {"username": username}},
                        }
                    },
                    "_source": ["text", "filename", "chunk_index"],
                    "size": top_k,
                },
            ),
        )

        # Merge results: deduplicate by ES doc _id, keep highest score
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
        return chunks

    # ── RAG Step 3: PromptConstruct ───────────────────────────────────────────

    def _build_prompt(self, question: str, chunks: list[dict]) -> list[dict]:
        """
        Build the messages array for the LLM call.

        If chunks were retrieved, inject them as context in a system message.
        If no chunks found (user hasn't uploaded any docs), fall back to plain chat.

        Returns OpenAI-format messages: [{"role": ..., "content": ...}, ...]

        Java equivalent: PromptBuilder.build(String question, List<Chunk> context)
        """
        if not chunks:
            # No documents uploaded — plain chat fallback
            return [{"role": "user", "content": question}]

        # Format each chunk as a numbered reference
        context_text = "\n\n".join(
            f"[{i+1}] (from {c['filename']}):\n{c['text']}"
            for i, c in enumerate(chunks)
        )

        system_prompt = (
            "You are a helpful assistant. Answer the user's question based on "
            "the provided context documents. If the answer is not in the context, "
            "say so honestly.\n\n"
            f"Context:\n{context_text}"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": question},
        ]

    async def stream_chat(
        self, session_id: str, message: str, username: str
    ) -> AsyncGenerator[str, None]:
        """
        Chat pipeline (no RAG yet) — yields SSE chunks to the frontend.

        Steps:
          1. Save user question to DB immediately
          2. TODO: RetrievalStep (RAG) — skipped for now
          3. Call OpenAI and stream tokens back
          4. Save full answer to DB
        """
        # ── Step 1: Save user question to DB ─────────────────────────────────
        message_id = str(uuid.uuid4())
        msg_row = Message(
            message_id=message_id,
            session_id=session_id,
            user_question=message,
            model_answer="",
        )
        self.db.add(msg_row)
        await self.db.commit()

        # ── Step 2: Retrieve relevant chunks from Elasticsearch ──────────────
        chunks = await self._retrieve_chunks(message, username)

        # ── Step 3: Build prompt with retrieved context ───────────────────────
        messages = self._build_prompt(message, chunks)

        # ── Step 4: Call LLM + stream tokens back to frontend ─────────────────
        full_answer = ""
        try:
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    full_answer += token
                    yield f"data: {json.dumps({'content': token})}\n\n"
        except Exception as e:
            error_msg = f"[LLM Error: {e}]"
            full_answer = error_msg
            yield f"data: {json.dumps({'content': error_msg})}\n\n"

        # ── Step 5: Save full answer + source references to DB ───────────────
        msg_row.model_answer = full_answer
        msg_row.documents = json.dumps([
            {"filename": c["filename"], "chunk_index": c["chunk_index"]}
            for c in chunks
        ])
        await self.db.commit()

        yield "data: [DONE]\n\n"

    async def quick_parse(self, session_id: str) -> dict:
        # TODO: QuickParse → QuickParseService → DocumentParsers → Redis
        return {"status": "success"}

    async def get_session_documents(self, session_id: str) -> dict:
        # TODO: query UploadTable filtered by session_id
        return {"documents": [], "has_documents": False}
