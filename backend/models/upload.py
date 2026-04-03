# models/upload.py — UploadTable entity
# Java equivalent: @Entity UploadRecord

from sqlalchemy import Column, DateTime, Integer, String, func

from db.database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id          = Column(Integer, primary_key=True, index=True)
    filename    = Column(String, nullable=False)
    username    = Column(String, nullable=False, index=True)
    file_size   = Column(Integer, nullable=False)       # bytes
    chunk_count = Column(Integer, default=0)
    status      = Column(String, default="indexed")     # indexed / failed
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
