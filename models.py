from pydantic import BaseModel, Field
from typing import List, Optional

# Input/Output models for tools

class AddInput(BaseModel):
    a: int
    b: int

class AddOutput(BaseModel):
    result: int

class SqrtInput(BaseModel):
    a: int

class SqrtOutput(BaseModel):
    result: float

class StringsToIntsInput(BaseModel):
    string: str

class StringsToIntsOutput(BaseModel):
    ascii_values: List[int]

class ExpSumInput(BaseModel):
    int_list: List[int] = Field(alias="numbers")

class ExpSumOutput(BaseModel):
    result: float

class PythonCodeInput(BaseModel):
    code: str

class PythonCodeOutput(BaseModel):
    result: str

class UrlInput(BaseModel):
    url: str

class FilePathInput(BaseModel):
    file_path: str

class MarkdownInput(BaseModel):
    text: str

class MarkdownOutput(BaseModel):
    markdown: str

class ChunkListOutput(BaseModel):
    chunks: List[str]

class ShellCommandInput(BaseModel):
    command: str

# Telegram Models
class TelegramMessageOutput(BaseModel):
    message: str
    chat_id: str
    message_id: int

class TelegramSendInput(BaseModel):
    chat_id: str
    text: str

# Google Sheets/Drive Models
class CreateSheetInput(BaseModel):
    title: str

class CreateSheetOutput(BaseModel):
    sheet_id: str
    sheet_url: str

class AddDataInput(BaseModel):
    sheet_id: str
    data: List[List[str]]  # 2D array
    range: str = "A1"

class ShareSheetInput(BaseModel):
    sheet_id: str
    email: str
    role: str = "writer"  # writer, reader, owner

class SheetLinkInput(BaseModel):
    sheet_id: str

class SheetLinkOutput(BaseModel):
    link: str

# Gmail Models
class SendEmailInput(BaseModel):
    to: str
    subject: str
    body: str
    link: Optional[str] = None

class SendEmailOutput(BaseModel):
    message_id: str
    success: bool


