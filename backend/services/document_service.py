# services/document_service.py — Knowledge base / document business logic
# Java equivalent: @Service DocumentService
#
# From chart.svg:
#   UploadFiles → DocumentService → FileParser → ChunkProcessing
#              → EmbeddingGen → ESIndexing → Elasticsearch
#              → SaveToDB → PostgreSQL

import logging
import os

from fastapi import UploadFile
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.es_client import es
from models.upload import Upload
from services.file_parser import parse_file, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "storage", "files")

embedding_client = AsyncOpenAI(
    api_key=settings.EMBEDDING_API_KEY or settings.DASHSCOPE_API_KEY,
    base_url=settings.EMBEDDING_BASE_URL,
)


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Step 1: FileParser ────────────────────────────────────────────────────

    def _save_file(self, username: str, filename: str, data: bytes) -> None:
        user_dir = os.path.join(STORAGE_DIR, username)
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, filename), "wb") as f:
            f.write(data)

    # ── Step 2: ChunkProcessing ───────────────────────────────────────────────

    def _chunk_text(self, text: str, filename: str, username: str,
                    chunk_size: int = 500, overlap: int = 50) -> list[dict]:
        words = text.split()
        step = chunk_size - overlap
        chunks = []
        for i, start in enumerate(range(0, len(words), step)):
            chunk_words = words[start:start + chunk_size]
            if not chunk_words:
                break
            chunks.append({
                "text":        " ".join(chunk_words),
                "filename":    filename,
                "username":    username,
                "chunk_index": i,
            })
        return chunks

    # ── Step 3: EmbeddingGen ──────────────────────────────────────────────────

    async def _embed_chunks(self, chunks: list[dict]) -> list[dict]:
        batch_size = 10  # DashScope limit
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            resp = await embedding_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=[c["text"] for c in batch],
                dimensions=1024,
                encoding_format="float",
            )
            for j, item in enumerate(resp.data):
                batch[j]["embedding"] = item.embedding
        return chunks

    # ── Step 4: ESIndexing ────────────────────────────────────────────────────

    async def _index_chunks(self, chunks: list[dict]) -> None:
        actions = []
        for chunk in chunks:
            actions.append({"index": {"_index": settings.ES_INDEX}})
            actions.append({
                "text":        chunk["text"],
                "filename":    chunk["filename"],
                "username":    chunk["username"],
                "chunk_index": chunk["chunk_index"],
                "embedding":   chunk["embedding"],
            })
        await es.bulk(body=actions)

    # ── Step 5: SaveToDB ──────────────────────────────────────────────────────

    async def _save_to_db(self, filename: str, username: str,
                          file_size: int, chunk_count: int) -> None:
        record = Upload(
            filename=filename,
            username=username,
            file_size=file_size,
            chunk_count=chunk_count,
            status="indexed",
        )
        self.db.add(record)
        await self.db.commit()

    # ── Public API ────────────────────────────────────────────────────────────

    async def upload_files(self, files: list[UploadFile], username: str) -> dict:
        results = []
        for file in files:
            ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
            if ext not in SUPPORTED_EXTENSIONS:
                results.append({
                    "file_name": file.filename,
                    "status":    "unsupported",
                    "error":     f"Unsupported file type: .{ext}",
                })
                continue

            data = await file.read()
            text = parse_file(file.filename, data)
            self._save_file(username, file.filename, data)

            chunks = self._chunk_text(text, file.filename, username)
            chunks = await self._embed_chunks(chunks)
            await self._index_chunks(chunks)
            await self._save_to_db(file.filename, username, len(data), len(chunks))

            results.append({
                "file_name":   file.filename,
                "file_size":   len(data),
                "characters":  len(text),
                "chunk_count": len(chunks),
                "status":      "indexed",
            })
            logger.info("Indexed %s: %d chunks", file.filename, len(chunks))

        return {"status": "success", "files": results}

    async def get_files(self, username: str) -> list:
        result = await self.db.execute(
            select(Upload)
            .where(Upload.username == username)
            .order_by(Upload.created_at.desc())
        )
        uploads = result.scalars().all()
        return [
            {
                "id":          u.id,
                "file_name":   u.filename,
                "file_size":   u.file_size,
                "chunk_count": u.chunk_count,
                "status":      u.status,
                "created_at":  u.created_at.isoformat(),
                "updated_at":  u.created_at.isoformat(),
            }
            for u in uploads
        ]

    async def delete_file(self, file_name: str, username: str) -> dict:
        # Remove from Elasticsearch
        await es.delete_by_query(
            index=settings.ES_INDEX,
            body={"query": {"bool": {"must": [
                {"term": {"filename": file_name}},
                {"term": {"username": username}},
            ]}}},
        )
        # Remove from PostgreSQL
        await self.db.execute(
            delete(Upload).where(
                Upload.filename == file_name,
                Upload.username == username,
            )
        )
        await self.db.commit()
        # Remove from disk
        path = os.path.join(STORAGE_DIR, username, file_name)
        if os.path.exists(path):
            os.remove(path)
        return {"status": "success"}
