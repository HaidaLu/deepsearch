# services/quick_parse_service.py — In-chat file upload (session-scoped, temporary)
#
# Unlike upload_files (knowledge base), quick_parse:
#   - Does NOT embed or index into Elasticsearch
#   - Stores the full extracted text in Redis (2hr TTL)
#   - Scoped to a single session — text is injected directly into the prompt
#
# Redis key layout:
#   quick:{session_id}:files       → JSON list[dict] of file metadata
#   quick:{session_id}:texts       → JSON dict[filename, text] per-file extracted text
#
# Storing text per file (rather than one concatenated blob) allows clean deletion:
# removing a file just pops it from the dict and rebuilds get_text() on the fly.

import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile

from db.redis_client import redis
from services.file_parser import parse_file

logger = logging.getLogger(__name__)

TTL_SECONDS = 2 * 60 * 60  # 2 hours


class QuickParseService:

    # ── Redis key helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _files_key(session_id: str) -> str:
        return f"quick:{session_id}:files"

    @staticmethod
    def _texts_key(session_id: str) -> str:
        return f"quick:{session_id}:texts"

    # ── Public API ────────────────────────────────────────────────────────────

    async def parse_and_store(self, session_id: str, file: UploadFile) -> dict:
        """
        Parse a file and store its text in Redis under this session.
        Multiple files are stored per-file so each can be deleted independently.
        """
        data = await file.read()
        text = parse_file(file.filename, data)

        # Per-file text dict: {filename: extracted_text}
        raw_texts = await redis.get(self._texts_key(session_id))
        texts: dict[str, str] = json.loads(raw_texts) if raw_texts else {}
        texts[file.filename] = text
        await redis.setex(self._texts_key(session_id), TTL_SECONDS, json.dumps(texts))

        # File metadata list
        raw_files = await redis.get(self._files_key(session_id))
        files: list[dict] = json.loads(raw_files) if raw_files else []
        # Replace existing entry for same filename, or append
        files = [f for f in files if f["document_name"] != file.filename]
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

    async def delete_document(self, session_id: str, filename: str) -> dict:
        """Remove a single file from this session's Redis store."""
        # Remove from texts dict
        raw_texts = await redis.get(self._texts_key(session_id))
        if raw_texts:
            texts: dict[str, str] = json.loads(raw_texts)
            if filename not in texts:
                raise HTTPException(status_code=404, detail="Document not found in session")
            texts.pop(filename)
            await redis.setex(self._texts_key(session_id), TTL_SECONDS, json.dumps(texts))
        else:
            raise HTTPException(status_code=404, detail="No documents found for this session")

        # Remove from files metadata list
        raw_files = await redis.get(self._files_key(session_id))
        if raw_files:
            files: list[dict] = json.loads(raw_files)
            files = [f for f in files if f["document_name"] != filename]
            await redis.setex(self._files_key(session_id), TTL_SECONDS, json.dumps(files))

        logger.info("quick_parse: deleted %s from session %s", filename, session_id)
        return {"status": "success"}

    async def get_text(self, session_id: str) -> str:
        """
        Return combined text for all files in this session.
        Each file section is headed with '--- filename ---' for LLM context.
        """
        raw = await redis.get(self._texts_key(session_id))
        if not raw:
            return ""
        texts: dict[str, str] = json.loads(raw)
        parts = [f"--- {name} ---\n{text}" for name, text in texts.items()]
        return "\n\n".join(parts)

    async def get_files(self, session_id: str) -> list[dict]:
        """Return metadata for all files attached to this session."""
        raw = await redis.get(self._files_key(session_id))
        return json.loads(raw) if raw else []
