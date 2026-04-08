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
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.es_client import es
from models.message import Message
from models.session import Session
from services.quick_parse_service import QuickParseService

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

    async def rename_session(self, session_id: str, name: str) -> dict:
        result = await self.db.execute(
            select(Session).where(Session.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")
        session.session_name = name
        await self.db.commit()
        return {"session_id": session_id, "session_name": name}

    async def delete_last_message(self, session_id: str) -> dict:
        """Delete the most recent message in a session (for answer regeneration)."""
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        message = result.scalar_one_or_none()
        if not message:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="No messages found for this session")
        await self.db.execute(
            delete(Message).where(Message.id == message.id)
        )
        await self.db.commit()
        return {"status": "success", "deleted_message_id": message.message_id}

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
        - Results are merged and deduplicated manually (RRF requires paid ES license)

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
        return sorted(seen_ids.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    # ── RAG Step 3: PromptConstruct ───────────────────────────────────────────

    def _build_prompt(
        self, question: str, chunks: list[dict], quick_text: str = ""
    ) -> list[dict]:
        """
        Build the messages array for the LLM call.

        Context sources (both optional):
          - chunks     : top-K relevant chunks retrieved from Elasticsearch (knowledge base)
          - quick_text : full text of files attached directly in this chat session (Redis)

        Falls back to plain chat if neither source has content.
        """
        kb_context = "\n\n".join(
            f"[{i+1}] (from {c['filename']}):\n{c['text']}"
            for i, c in enumerate(chunks)
        )

        sections = []
        if kb_context:
            sections.append(f"## Knowledge Base\n{kb_context}")
        if quick_text:
            sections.append(f"## Attached Files\n{quick_text}")

        if not sections:
            return [{"role": "user", "content": question}]

        system_prompt = (
            "You are a helpful assistant. Answer the user's question based on "
            "the provided context. If the answer is not in the context, say so honestly.\n\n"
            + "\n\n".join(sections)
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": question},
        ]

    # ── Post-answer: generate recommended follow-up questions ─────────────────

    async def _generate_recommended_questions(
        self, question: str, answer: str
    ) -> list[str]:
        """
        Ask the LLM for 3 short follow-up questions based on this Q&A exchange.
        Returns a list of up to 3 question strings.
        Best-effort: returns [] on any failure.
        """
        prompt = (
            "Based on this Q&A, generate exactly 3 short follow-up questions "
            "the user might want to ask next.\n"
            f"Question: {question}\n"
            f"Answer: {answer[:500]}\n\n"
            "Output ONLY a JSON array of 3 strings, no explanation:\n"
            '["Question 1?", "Question 2?", "Question 3?"]'
        )
        try:
            resp = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                temperature=0.7,
            )
            raw = resp.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            questions = json.loads(raw)
            if isinstance(questions, list):
                return [str(q) for q in questions[:3]]
        except Exception:
            pass
        return []

    # ── Post-answer: auto-name session from first question ────────────────────

    async def _maybe_name_session(self, session_id: str, question: str) -> None:
        """
        If this session still has the default name "New Conversation",
        generate a short title (max 6 words) from the first user question.
        Runs after the main answer streams — never blocks the chat.
        """
        result = await self.db.execute(
            select(Session).where(Session.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None or session.session_name != "New Conversation":
            return  # already named, skip

        prompt = (
            "Generate a very short title (max 6 words) for a chat conversation "
            f'that starts with this question: "{question}"\n\n'
            "Output only the title, no quotes, no punctuation at the end."
        )
        try:
            resp = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                temperature=0.5,
            )
            name = resp.choices[0].message.content.strip()[:80]
            if name:
                session.session_name = name
                await self.db.commit()
        except Exception:
            pass  # naming is best-effort, never raise

    # ── Main pipeline ─────────────────────────────────────────────────────────

    async def stream_chat(
        self, session_id: str, message: str, username: str
    ) -> AsyncGenerator[str, None]:
        """
        Full RAG pipeline — yields SSE chunks to the frontend.

        Steps:
          1. Save user question to DB immediately
          2. Retrieve relevant chunks (hybrid KNN + BM25 in ES)
          3. Build prompt with retrieved context
          4. Stream LLM answer token-by-token
          5. In parallel: generate recommended questions + auto-name session
          6. Save full answer + sources + recommended questions to DB
          7. Send metadata events (documents, recommended_questions) then [DONE]
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

        # ── Step 2: Retrieve ES chunks + quick_parse text in parallel ────────
        chunks, quick_text = await asyncio.gather(
            self._retrieve_chunks(message, username),
            QuickParseService().get_text(session_id),
        )

        # ── Step 3: Build prompt with both context sources ────────────────────
        messages = self._build_prompt(message, chunks, quick_text)

        # ── Step 4: Stream LLM answer to frontend ────────────────────────────
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

        # ── Step 5: Generate recommended questions + auto-name session ────────
        # Run both LLM calls in parallel — neither blocks the streamed answer
        rq, _ = await asyncio.gather(
            self._generate_recommended_questions(message, full_answer),
            self._maybe_name_session(session_id, message),
        )

        # ── Step 6: Persist full answer + sources + recommended questions ─────
        msg_row.model_answer = full_answer
        msg_row.documents = json.dumps([
            {"filename": c["filename"], "chunk_index": c["chunk_index"]}
            for c in chunks
        ])
        msg_row.recommended_questions = json.dumps(rq)
        await self.db.commit()

        # ── Step 7: Send metadata events then signal completion ───────────────
        if chunks:
            yield f"data: {json.dumps({'documents': [{'filename': c['filename'], 'chunk_index': c['chunk_index']} for c in chunks]})}\n\n"
        if rq:
            yield f"data: {json.dumps({'recommended_questions': rq})}\n\n"

        yield "data: [DONE]\n\n"

    async def quick_parse(self, session_id: str) -> dict:
        # TODO: QuickParse → QuickParseService → DocumentParsers → Redis
        return {"status": "success"}

    async def get_session_documents(self, session_id: str) -> dict:
        # TODO: query UploadTable filtered by session_id
        return {"documents": [], "has_documents": False}
