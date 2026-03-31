# models/schemas.py — Pydantic request/response schemas
# Java equivalent: DTOs (Data Transfer Objects) / @RequestBody classes

from pydantic import BaseModel


# ── User ──────────────────────────────────────────────────────────────────────
class UserLoginRequest(BaseModel):
    username: str
    password: str

class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserRegisterRequest(BaseModel):
    username: str
    password: str


# ── Session ───────────────────────────────────────────────────────────────────
class SessionItem(BaseModel):
    session_id: str
    session_name: str
    created_at: str

class GetSessionsResponse(BaseModel):
    sessions: list[SessionItem]

class CreateSessionResponse(BaseModel):
    session_id: str


# ── Chat ──────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

class MessageItem(BaseModel):
    message_id: str
    session_id: str
    user_question: str
    model_answer: str
    think: str | None = None
    documents: str | None = None
    recommended_questions: str | None = None
    created_at: str


# ── Repository ────────────────────────────────────────────────────────────────
class FileItem(BaseModel):
    file_name: str
    file_size: int
    updated_at: str
    chunk_count: int = 0
    status: str = "success"
