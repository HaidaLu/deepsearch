# services/document_service.py — Knowledge base / document business logic
# Java equivalent: @Service DocumentService
#
# From chart.svg:
#   UploadFiles → DocumentService → FileParser → DeepDoc → MultiParsers
#              → ChunkProcessing → EmbeddingGen → ESIndexing → Elasticsearch

import io
import logging
from pathlib import Path

import pdfplumber
import docx
from fastapi import UploadFile
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.es_client import es
from models.upload import Upload

logger = logging.getLogger(__name__)

# Files are saved under backend/storage/files/{username}/
STORAGE_ROOT = Path(__file__).parent.parent / "storage" / "files"

# Embedding client — uses DashScope (OpenAI-compatible), same SDK different base_url
embedding_client = AsyncOpenAI(
    api_key=settings.EMBEDDING_API_KEY or settings.DASHSCOPE_API_KEY,
    base_url=settings.EMBEDDING_BASE_URL,
)


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Task 1: FileParser ────────────────────────────────────────────────────

    async def upload_files(self, files: list[UploadFile], username: str) -> dict:
        """
        Full pipeline per file:
          1. FileParser    — save to disk + parse to plain text  ← implemented
          2. ChunkProcessing — split into chunks                  ← TODO
          3. EmbeddingGen  — generate vectors                    ← TODO
          4. ESIndexing    — index into Elasticsearch             ← TODO
          5. SaveToDB      — record metadata in UploadTable       ← TODO
        """
        results = []

        for file in files:
            logger.info(f"Processing file: {file.filename} for user: {username}")
            raw_bytes = await file.read()

            # Step 1a: Save file to disk
            save_path = self._save_file(raw_bytes, file.filename, username)

            # Step 1b: Parse to plain text
            text = self._parse_file(raw_bytes, file.filename)

            logger.info(f"Parsed {file.filename}: {len(text)} characters")

            # Step 2: Split text into chunks
            chunks = self._chunk_text(text, file.filename, username)

            # Step 3: Generate embeddings for all chunks
            chunks_with_embeddings = await self._embed_chunks(chunks)

            # Step 4: Index chunks + embeddings into Elasticsearch
            await self._index_chunks(chunks_with_embeddings)

            # Step 5: Save file metadata to PostgreSQL
            await self._save_to_db(file.filename, len(raw_bytes), len(chunks_with_embeddings), username)

            results.append({
                "file_name": file.filename,
                "file_size": len(raw_bytes),
                "characters": len(text),
                "chunk_count": len(chunks_with_embeddings),
                "status": "indexed",
            })

        return {"status": "success", "files": results}

    def _save_file(self, raw_bytes: bytes, filename: str, username: str) -> Path:
        """Save uploaded file to storage/files/{username}/{filename}."""
        user_dir = STORAGE_ROOT / username
        user_dir.mkdir(parents=True, exist_ok=True)
        save_path = user_dir / filename
        save_path.write_bytes(raw_bytes)
        logger.info(f"Saved file to: {save_path}")
        return save_path

    def _parse_file(self, raw_bytes: bytes, filename: str) -> str:
        """
        Parse file bytes to plain text based on extension.
        Supported: PDF, DOCX, TXT
        Java equivalent: FileParser strategy pattern
        """
        ext = Path(filename).suffix.lower()

        if ext == ".pdf":
            return self._parse_pdf(raw_bytes)
        elif ext == ".docx":
            return self._parse_docx(raw_bytes)
        elif ext in (".txt", ".md"):
            return raw_bytes.decode("utf-8", errors="ignore")
        else:
            logger.warning(f"Unsupported file type: {ext}, treating as plain text")
            return raw_bytes.decode("utf-8", errors="ignore")

    def _parse_pdf(self, raw_bytes: bytes) -> str:
        """Extract text from all pages of a PDF using pdfplumber."""
        text_parts = []
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)

    def _parse_docx(self, raw_bytes: bytes) -> str:
        """Extract text from all paragraphs of a DOCX file."""
        doc = docx.Document(io.BytesIO(raw_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    # ── Task 2: ChunkProcessing ───────────────────────────────────────────────

    def _chunk_text(
        self,
        text: str,
        filename: str,
        username: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[dict]:
        """
        Split plain text into overlapping chunks by word count.

        Each chunk is a dict with metadata needed for ESIndexing:
          - text:        the chunk content
          - filename:    source document name
          - username:    owner (used as ES namespace)
          - chunk_index: position in the document (0-based)

        Java equivalent: TextSplitter.split(text, chunkSize, overlap)

        Example with chunk_size=5, overlap=2:
          words = [w0, w1, w2, w3, w4, w5, w6]
          chunk0 = w0..w4
          chunk1 = w3..w7  (step = chunk_size - overlap = 3)
        """
        words = text.split()
        if not words:
            return []

        step = chunk_size - overlap
        chunks = []
        for i in range(0, len(words), step):
            chunk_words = words[i: i + chunk_size]
            chunk_text = " ".join(chunk_words)
            chunks.append({
                "text": chunk_text,
                "filename": filename,
                "username": username,
                "chunk_index": len(chunks),
            })

        logger.info(f"Chunked '{filename}' into {len(chunks)} chunks (size={chunk_size}, overlap={overlap})")
        return chunks

    # ── Task 3: EmbeddingGen ──────────────────────────────────────────────────

    async def _embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """
        Call the embedding API to generate a vector for each chunk.
        Adds an 'embedding' key (list of floats) to each chunk dict.

        Uses batch requests (up to 25 at a time) to stay within API limits.
        Java equivalent: EmbeddingService.embed(List<String> texts)
        """
        BATCH_SIZE = 10  # DashScope limit per request
        texts = [c["text"] for c in chunks]

        all_embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i: i + BATCH_SIZE]
            response = await embedding_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=batch,
                dimensions=1024,
                encoding_format="float",
            )
            # response.data is sorted by index
            batch_vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            all_embeddings.extend(batch_vectors)

        for chunk, vector in zip(chunks, all_embeddings):
            chunk["embedding"] = vector

        logger.info(f"Generated {len(all_embeddings)} embeddings (dim={len(all_embeddings[0]) if all_embeddings else 0})")
        return chunks

    # ── Task 4: ESIndexing ────────────────────────────────────────────────────

    async def _index_chunks(self, chunks: list[dict]) -> None:
        """
        Bulk-index all chunks into Elasticsearch.

        Each document stored in ES:
          { text, filename, username, chunk_index, embedding }

        Uses the bulk API for efficiency — one HTTP request for all chunks
        instead of one per chunk.

        Java equivalent: elasticsearchRepository.saveAll(List<ChunkDocument>)
        """
        if not chunks:
            return

        # Build bulk request body — ES bulk format alternates action + document
        operations = []
        for chunk in chunks:
            # Action line: tells ES to index this document
            operations.append({"index": {"_index": settings.ES_INDEX}})
            # Document line
            operations.append({
                "text":        chunk["text"],
                "filename":    chunk["filename"],
                "username":    chunk["username"],
                "chunk_index": chunk["chunk_index"],
                "embedding":   chunk["embedding"],
            })

        response = await es.bulk(operations=operations)

        if response.get("errors"):
            # Log any individual failures without failing the whole request
            failed = [item for item in response["items"] if "error" in item.get("index", {})]
            logger.warning(f"ES bulk index had {len(failed)} failures: {failed[:2]}")
        else:
            logger.info(f"Indexed {len(chunks)} chunks into ES index '{settings.ES_INDEX}'")

    # ── Task 5: SaveToDB ──────────────────────────────────────────────────────

    async def _save_to_db(self, filename: str, file_size: int, chunk_count: int, username: str) -> None:
        """Save upload metadata to PostgreSQL UploadTable."""
        record = Upload(
            filename=filename,
            username=username,
            file_size=file_size,
            chunk_count=chunk_count,
            status="indexed",
        )
        self.db.add(record)
        await self.db.commit()
        logger.info(f"Saved upload record: {filename} ({chunk_count} chunks) for {username}")

    async def get_files(self, username: str) -> list:
        """List all uploaded files for a user. Powers the knowledge base sidebar."""
        from sqlalchemy import select
        result = await self.db.execute(
            select(Upload)
            .where(Upload.username == username)
            .order_by(Upload.created_at.desc())
        )
        uploads = result.scalars().all()
        return [
            {
                "file_name":   u.filename,
                "file_size":   u.file_size,
                "chunk_count": u.chunk_count,
                "status":      u.status,
                "created_at":  u.created_at.isoformat(),
            }
            for u in uploads
        ]

    async def delete_file(self, file_name: str, username: str) -> dict:
        """
        Delete a file from:
          1. Elasticsearch (all chunks for this file + user)
          2. PostgreSQL UploadTable
          3. Disk storage
        """
        from sqlalchemy import select, delete

        # 1. Delete all ES chunks for this file
        await es.delete_by_query(
            index=settings.ES_INDEX,
            body={"query": {"bool": {"must": [
                {"term": {"filename": file_name}},
                {"term": {"username": username}},
            ]}}},
        )
        logger.info(f"Deleted ES chunks for {file_name} / {username}")

        # 2. Delete from PostgreSQL
        await self.db.execute(
            delete(Upload)
            .where(Upload.filename == file_name)
            .where(Upload.username == username)
        )
        await self.db.commit()

        # 3. Delete from disk
        file_path = STORAGE_ROOT / username / file_name
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted file from disk: {file_path}")

        return {"status": "success"}
