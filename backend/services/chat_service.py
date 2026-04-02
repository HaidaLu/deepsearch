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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.message import Message
from models.session import Session


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
        Core RAG pipeline — yields SSE chunks so the frontend can stream the response.

        Steps (from chart.svg):
          1. RetrievalStep  → query Elasticsearch via RAGDealer + HybridRanking
          2. PromptConstruct → build prompt with retrieved context
          3. LLMCall         → call OpenAI / DashScope, stream tokens
          4. SaveToDB        → persist question + answer to MessageTable
        """
        # TODO: implement full RAG pipeline
        # Placeholder: yield a single SSE message
        payload = json.dumps({"content": "Hello! Backend streaming not yet implemented."})
        yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"

    async def quick_parse(self, session_id: str) -> dict:
        # TODO: QuickParse → QuickParseService → DocumentParsers → Redis
        return {"status": "success"}

    async def get_session_documents(self, session_id: str) -> dict:
        # TODO: query UploadTable filtered by session_id
        return {"documents": [], "has_documents": False}
