# services/chat_service.py — Chat business logic
# Java equivalent: @Service ChatService
#
# From chart.svg:
#   ChatCore → LLMCall → (OpenAI / DashScope)
#            → RetrievalStep → RetrievalCore → RAGDealer → ESQuery → HybridRanking
#            → PromptConstruct → StreamResponse
#            → SaveToDB → PostgreSQL

import json
import uuid
from typing import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.message import Message
from models.session import Session

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

        # ── Step 2: Retrieve relevant chunks (TODO — RAG pipeline) ───────────

        # ── Step 3: Call LLM + stream tokens back to frontend ─────────────────
        full_answer = ""
        try:
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": message}],
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

        # ── Step 4: Save full answer to DB ────────────────────────────────────
        msg_row.model_answer = full_answer
        await self.db.commit()

        yield "data: [DONE]\n\n"

    async def quick_parse(self, session_id: str) -> dict:
        # TODO: QuickParse → QuickParseService → DocumentParsers → Redis
        return {"status": "success"}

    async def get_session_documents(self, session_id: str) -> dict:
        # TODO: query UploadTable filtered by session_id
        return {"documents": [], "has_documents": False}
