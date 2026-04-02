# router/history_rt.py — Session history & knowledge base endpoints
# Java equivalent: @RestController @RequestMapping("/api/history")
#
# From chart.svg: HistoryRouter → get_sessions / get_messages
#                 UploadFiles → DocumentService → FileParser → DeepDoc → ESIndexing

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from db.database import get_db
from models.schemas import GetSessionsResponse
from services.chat_service import ChatService
from services.document_service import DocumentService

router = APIRouter(tags=["History & Repository"])


# ── Session history ───────────────────────────────────────────────────────────

@router.get("/get_sessions", response_model=GetSessionsResponse)
async def get_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all sessions for the current user. Java: @GetMapping("/sessions")"""
    return await ChatService(db).get_sessions(current_user["user_id"])


@router.get("/get_messages")
async def get_messages(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get message history for a session. Java: @GetMapping("/session/{id}/messages")"""
    return await ChatService(db).get_messages(session_id)


# ── Knowledge base (repository) ───────────────────────────────────────────────

@router.post("/upload_files")
async def upload_files(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload documents to the knowledge base.
    Pipeline: FileParser → DeepDoc → ChunkProcessing → EmbeddingGen → ESIndexing

    Java equivalent:
        @PostMapping("/upload")
        public ResponseEntity<?> upload(@RequestParam MultipartFile[] files) { ... }
    """
    return await DocumentService(db).upload_files(files, current_user["username"])


@router.get("/get_files")
async def get_files(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all files in the knowledge base."""
    return await DocumentService(db).get_files(current_user["username"])


@router.delete("/delete_file")
async def delete_file(
    file_name: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a file from the knowledge base."""
    return await DocumentService(db).delete_file(file_name, current_user["username"])
