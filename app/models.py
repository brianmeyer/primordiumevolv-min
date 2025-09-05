from pydantic import BaseModel, Field, constr, conint
from typing import List, Optional

class ChatRequest(BaseModel):
    prompt: constr(strip_whitespace=True, min_length=1)
    system: Optional[constr(strip_whitespace=True, min_length=1)] = None

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