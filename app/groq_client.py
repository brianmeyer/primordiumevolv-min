import os, time, requests
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL_ID_ENV = os.getenv("GROQ_MODEL_ID")  # user override if set
_GROQ_BASE = "https://api.groq.com/openai/v1"


class GroqError(RuntimeError):
    pass


_cache = {"models": None, "fetched_at": 0.0}
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=2)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        _session = s
    return _session


def _headers():
    if not GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY not set")
    return {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}


def available() -> bool:
    return bool(GROQ_API_KEY)


def list_models(force: bool = False) -> List[Dict]:
    now = time.time()
    if _cache["models"] and not force and (now - _cache["fetched_at"] < 300):
        return _cache["models"]
    r = _get_session().get(f"{_GROQ_BASE}/models", headers=_headers(), timeout=20)
    r.raise_for_status()
    data = r.json()
    models = data.get("data", []) or data.get("models", [])
    _cache["models"], _cache["fetched_at"] = models, now
    return models


def pick_model(task_tokens: int = 512, prefer: Optional[List[str]] = None) -> str:
    """
    Choose a chat-capable model. Strategy:
    1) Respect GROQ_MODEL_ID if set and present.
    2) Else prefer names in 'prefer' (e.g., ["llama3-70b","llama3-8b","mixtral-8x7b"]) when found.
    3) Else choose the model with the largest context window.
    """
    models = list_models()
    names = [m.get("id") or m.get("name") for m in models if isinstance(m, dict)]
    # 1) env override
    if GROQ_MODEL_ID_ENV and GROQ_MODEL_ID_ENV in names:
        return GROQ_MODEL_ID_ENV
    # 2) prefer list
    prefer = prefer or ["llama3-70b", "llama3-8b", "mixtral-8x7b", "llama3"]
    for pref in prefer:
        candidates = [n for n in names if pref in n]
        if candidates:
            candidates.sort(key=lambda n: int(n.split("-")[-1]) if n.split("-")[-1].isdigit() else 0, reverse=True)
            return candidates[0]
    # 3) fallback by context length if metadata present
    best = None
    best_ctx = -1
    for m in models:
        mid = m.get("id") or m.get("name")
        ctx = m.get("context_length") or m.get("context") or 0
        if isinstance(ctx, str) and ctx.isdigit():
            ctx = int(ctx)
        if isinstance(ctx, int) and ctx > best_ctx:
            best_ctx, best = ctx, mid
    if best:
        return best
    # last resort
    if names:
        return names[0]
    raise GroqError("No Groq models available")


def health() -> dict:
    if not GROQ_API_KEY:
        return {"status": "down", "detail": "missing GROQ_API_KEY"}
    try:
        models = list_models(force=True)
        return {"status": "ok", "models": [m.get("id") or m.get("name") for m in models][:10]}
    except Exception as e:
        return {"status": "down", "detail": str(e)}


def chat_complete(messages: List[Dict], model_id: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
    if not GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY not set")
    model = model_id or pick_model()
    payload = {"model": model, "messages": messages, "stream": False}
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    r = _get_session().post(f"{_GROQ_BASE}/chat/completions", headers=_headers(), json=payload, timeout=90)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


def generate(prompt: str, system: str | None = None, options: dict | None = None) -> Tuple[str, str]:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    out = chat_complete(msgs, model_id=None, temperature=(options or {}).get("temperature"), max_tokens=(options or {}).get("max_tokens"))
    # return (output, resolved_model_id)
    return out, (GROQ_MODEL_ID_ENV or pick_model())
