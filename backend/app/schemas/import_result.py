from pydantic import BaseModel


class ImportResult(BaseModel):
    read: int
    imported: int
    skipped: int
    unknown_rfid_sessions: int
    unknown_rfid_numbers: list[str]
