# router/chat_rt.py — Chat endpoints
# Java equivalent: @RestController @RequestMapping("/api/chat")
#
# From chart.svg: ChatRouter → ChatOnDocs → ChatStep → ChatCore → LLMCall → StreamResponse

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from db.database import get_db
from models.schemas import ChatRequest, CreateSessionResponse
from services.chat_service import ChatService
from services.quick_parse_service import QuickParseService

router = APIRouter(tags=["Chat"])


@router.post("/create_session", response_model=CreateSessionResponse)
async def create_session(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new chat session. Java: @PostMapping("/session")"""
    return await ChatService(db).create_session(current_user["user_id"])


@router.post("/chat_on_docs")
async def chat_on_docs(
    body: ChatRequest,
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Stream AI response — returns SSE (Server-Sent Events).
    The frontend reads this as a ReadableStream.

    Flow from chart.svg:
        ChatOnDocs → ChatStep → RetrievalStep → RetrievalCore → RAGDealer → ESQuery
                                              → ChatCore → PromptConstruct → LLMCall → StreamResponse

    Java equivalent: @PostMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    """
    return StreamingResponse(
        ChatService(db).stream_chat(session_id, body.message, current_user["username"]),
        media_type="text/event-stream",
    )


@router.post("/quick_parse")
async def quick_parse(
    session_id: str = Query(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Quick-parse a file attached directly in chat.
    Text stored in Redis (2hr TTL), injected into prompt on next message.
    From chart.svg: QuickParse → QuickParseService → DocumentParsers → Redis
    """
    return await QuickParseService().parse_and_store(session_id, file)


@router.get("/sessions/{session_id}/documents")
async def get_session_documents(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return files currently attached to a session (from Redis)."""
    files = await QuickParseService().get_files(session_id)
    return {"documents": files, "has_documents": len(files) > 0}


@router.delete("/sessions/{session_id}/last_message")
async def delete_last_message(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete the most recent message in a session so it can be regenerated.
    Called by the frontend Refresh button before re-submitting the last question.
    """
    return await ChatService(db).delete_last_message(session_id)


@router.delete("/sessions/{session_id}/document/{filename:path}")
async def delete_session_document(
    session_id: str,
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Remove a quick-parsed file from the session's Redis store.
    Uses {filename:path} to handle filenames with dots (e.g. report.pdf).
    """
    return await QuickParseService().delete_document(session_id, filename)
