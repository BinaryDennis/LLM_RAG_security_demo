from pydantic import BaseModel


class DocumentInput(BaseModel):
    title: str
    source_url: str
    version: str
    visibility: str
    text: str
