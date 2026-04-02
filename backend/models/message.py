# models/message.py — Message database table
# Each row = one exchange (user question + model answer) in a session
# Java equivalent: @Entity @Table(name="messages")

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from db.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, unique=True, index=True, nullable=False)
    session_id = Column(String, ForeignKey("sessions.session_id"), nullable=False)
    user_question = Column(Text, nullable=False)
    model_answer = Column(Text, default="")
    think = Column(Text, nullable=True)           # chain-of-thought / reasoning
    documents = Column(Text, nullable=True)       # JSON string of cited chunks
    recommended_questions = Column(Text, nullable=True)  # JSON string of follow-ups
    created_at = Column(DateTime(timezone=True), server_default=func.now())
