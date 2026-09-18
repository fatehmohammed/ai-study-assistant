from pydantic import BaseModel


class HistoryMessage(BaseModel):
    role: str
    text: str


class AskRequest(BaseModel):
    query: str
    source_filter: str | None = None
    history: list[HistoryMessage] = []


class QuizRequest(BaseModel):
    source_filter: str | None = None
    difficulty: str = "Medium"
    topic: str | None = None
    chunk_index: int | None = None
    question_index: int | None = None


class EvidenceChunk(BaseModel):
    source: str
    score: float
    text: str


class QuizQuestion(BaseModel):
    question: str
    options: dict[str, str]
    correct: str
    explanation: str
    source: str
    difficulty: str
    topic: str
    question_type: str = "recall"
    evidence: list[EvidenceChunk] = []


class SummarizeRequest(BaseModel):
    source_filter: str | None = None
    force: bool = False


class SourceResult(BaseModel):
    source: str
    score: float
    preview: str


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[SourceResult]


class IndexResponse(BaseModel):
    status: str
    source: str
    chunks: int
    message: str


class HealthResponse(BaseModel):
    status: str
    chunks_indexed: int
    sources: dict[str, int]
