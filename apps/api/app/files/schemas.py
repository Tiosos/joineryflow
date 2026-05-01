from pydantic import BaseModel


class FileBlobOut(BaseModel):
    file_blob_id: int
    sha256: str
    mime: str
    byte_size: int
    original_filename: str
    deduped: bool
