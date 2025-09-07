from pydantic import BaseModel, Field, constr, conint
from typing import List, Optional

class ChatRequest(BaseModel):
    prompt: constr(strip_whitespace=True, min_length=1)
    system: Optional[constr(strip_whitespace=True, min_length=1)] = None
    session_id: conint(ge=1)

class EvolveRequest(BaseModel):
    task: constr(strip_whitespace=True, min_length=1)
    assertions: Optional[List[constr(strip_whitespace=True, min_length=1)]] = None
    n: conint(ge=1, le=12) = 5

class WebSearchRequest(BaseModel):
    query: constr(strip_whitespace=True, min_length=2)
    top_k: conint(ge=1, le=10) = 5

class RagQueryRequest(BaseModel):
    q: constr(strip_whitespace=True, min_length=2)
    k: conint(ge=1, le=10) = 5

class TodoAddRequest(BaseModel):
    text: constr(strip_whitespace=True, min_length=1)

class TodoIdRequest(BaseModel):
    id: conint(ge=1)

class SessionCreateRequest(BaseModel):
    title: Optional[constr(strip_whitespace=True, min_length=1)] = "New session"

class MessageAppendRequest(BaseModel):
    role: constr(strip_whitespace=True, min_length=1)
    content: constr(strip_whitespace=True, min_length=1)

class MemoryQueryRequest(BaseModel):
    q: constr(strip_whitespace=True, min_length=1)
    k: conint(ge=1, le=20) = 5

class MetaRunRequest(BaseModel):
    session_id: Optional[conint(ge=1)] = None
    task_class: constr(strip_whitespace=True, min_length=2)
    task: constr(strip_whitespace=True, min_length=2)
    assertions: Optional[List[constr(strip_whitespace=True, min_length=1)]] = None
    n: conint(ge=1, le=24) = 12
    memory_k: conint(ge=0, le=10) = 3
    rag_k: conint(ge=0, le=10) = 3
    operators: Optional[List[constr(strip_whitespace=True, min_length=2)]] = None
    use_bandit: bool = True
    bandit_algorithm: Optional[constr(strip_whitespace=True)] = "ucb"  # "epsilon_greedy", "ucb"
    framework_mask: Optional[List[constr(strip_whitespace=True, min_length=2)]] = None
    eps: float = Field(default=0.1, ge=0.0, le=1.0)
    force_engine: Optional[constr(strip_whitespace=True, min_length=3)] = None  # "ollama" or "groq"
    compare_with_groq: Optional[bool] = False
    judge_mode: Optional[constr(strip_whitespace=True, min_length=2)] = "off"   # "off" | "pairwise_groq"
    judge_include_rationale: bool = True

class HumanRatingRequest(BaseModel):
    variant_id: conint(ge=1)
    human_score: conint(ge=1, le=10)  # UI sends 1-10 int directly
    feedback: Optional[constr(strip_whitespace=True)] = None
