import uuid

from pydantic import BaseModel, Field, field_validator


class DocumentInput(BaseModel):
    title: str
    source_url: str
    version: str
    visibility: str
    text: str


class QueryRequest(BaseModel):
    question: str = Field(max_length=2000)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class Citation(BaseModel):
    document_id: uuid.UUID
    title: str
    source_url: str
    chunk_id: uuid.UUID


class QueryResponse(BaseModel):
    answer: str | None
    citations: list[Citation]
    abstained: bool
    request_id: uuid.UUID
