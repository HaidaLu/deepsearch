# services/quick_parse_service.py — In-chat file upload (session-scoped, temporary)
#
# Unlike upload_files (knowledge base), quick_parse:
#   - Does NOT embed or index into Elasticsearch
#   - Stores the full extracted text in Redis (2hr TTL)
#   - Scoped to a single session — text is injected directly into the prompt
#
# Redis key layout:
#   quick:{session_id}:text      → full extracted text (string)
#   quick:{session_id}:files     → JSON list of file metadata

import io
import json
import logging
from datetime import datetime, timezone

from fastapi import UploadFile

from db.redis_client import redis

logger = logging.getLogger(__name__)

TTL_SECONDS = 2 * 60 * 60  # 2 hours


class QuickParseService:

    # ── File parsers (reuse same logic as document_service) ───────────────────

    def _parse_file(self, filename: str, data: bytes) -> str:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext == "pdf":
            return self._parse_pdf(data)
        elif ext == "docx":
            return self._parse_docx(data)
        else:
            return data.decode("utf-8", errors="replace")

    def _parse_pdf(self, data: bytes) -> str:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
        return "\n".join(parts)

    def _parse_docx(self, data: bytes) -> str:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # ── Redis helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _text_key(session_id: str) -> str:
        return f"quick:{session_id}:text"

    @staticmethod
    def _files_key(session_id: str) -> str:
        return f"quick:{session_id}:files"

    # ── Public API ────────────────────────────────────────────────────────────

    async def parse_and_store(self, session_id: str, file: UploadFile) -> dict:
        """
        Parse a file and append its text to this session's Redis store.
        Multiple files can be uploaded; each is appended with a header separator.
        """
        data = await file.read()
        text = self._parse_file(file.filename, data)

        # Append text under a file header so the LLM can distinguish sources
        existing = await redis.get(self._text_key(session_id)) or ""
        separator = f"\n\n--- {file.filename} ---\n"
        combined = existing + separator + text

        await redis.setex(self._text_key(session_id), TTL_SECONDS, combined)

        # Update file metadata list
        raw = await redis.get(self._files_key(session_id))
        files = json.loads(raw) if raw else []
        now = datetime.now(timezone.utc).isoformat()
        files.append({
            "id":            len(files) + 1,
            "session_id":    session_id,
            "document_name": file.filename,
            "document_type": file.filename.rsplit(".", 1)[-1].lower(),
            "file_size":     len(data),
            "created_at":    now,
            "updated_at":    now,
            "upload_time":   now,
        })
        await redis.setex(self._files_key(session_id), TTL_SECONDS, json.dumps(files))

        logger.info("quick_parse: stored %s for session %s (%d chars)",
                    file.filename, session_id, len(text))
        return {
            "status":     "success",
            "filename":   file.filename,
            "characters": len(text),
        }

    async def get_text(self, session_id: str) -> str:
        """Return the full combined text for this session (empty string if none)."""
        return await redis.get(self._text_key(session_id)) or ""

    async def get_files(self, session_id: str) -> list[dict]:
        """Return metadata for all files attached to this session."""
        raw = await redis.get(self._files_key(session_id))
        return json.loads(raw) if raw else []
