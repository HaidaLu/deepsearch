# services/document_service.py — Knowledge base / document business logic
# Java equivalent: @Service DocumentService
#
# From chart.svg:
#   UploadFiles → DocumentService → FileParser → DeepDoc → MultiParsers
#              → ChunkProcessing → EmbeddingGen → ESIndexing → Elasticsearch

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_files(self, files: list[UploadFile], username: str) -> dict:
        """
        Full pipeline per file:
          1. FileParser    — detect file type (PDF, DOCX, Excel, PPT, HTML, MD, TXT)
          2. DeepDoc       — OCR + layout/table recognition for PDFs
          3. ChunkProcessing — split into chunks
          4. EmbeddingGen  — call EmbeddingAPI to generate vectors
          5. ESIndexing    — index chunks + vectors into Elasticsearch
          6. SaveToDB      — record metadata in UploadTable / KBTable (PostgreSQL)
        """
        # TODO: implement pipeline
        return {"status": "success", "uploaded": [f.filename for f in files]}

    async def get_files(self, username: str) -> list:
        # TODO: query UploadTable filtered by username
        return []

    async def delete_file(self, file_name: str, username: str) -> dict:
        # TODO: remove from Elasticsearch index + UploadTable + FileStorage
        return {"status": "success"}
