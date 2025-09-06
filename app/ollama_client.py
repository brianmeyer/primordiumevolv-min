import os, requests
from functools import lru_cache
from dotenv import load_dotenv
from typing import List
import requests.adapters

load_dotenv()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_ID = os.getenv("MODEL_ID", "qwen3:4b")

# Connection pooling for better performance
_session = None

def _get_session():
    """Get reusable requests session with connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=2
        )
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    return _session

class OllamaError(RuntimeError):
    pass

def _get(url: str):
    session = _get_session()
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def _post(url: str, payload: dict):
    session = _get_session()
    # Reduce timeout to avoid long hangs when Ollama is unreachable
    r = session.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

@lru_cache(maxsize=1, typed=False)
def models_list() -> List[str]:
    try:
        data = _get(f"{OLLAMA_HOST}/api/tags")
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception as e:
        raise OllamaError(f"Failed to query Ollama tags: {e}")

def validate_model(model_id: str) -> str:
    available = models_list()
    if model_id not in available:
        raise OllamaError(f"Model '{model_id}' not found. Available: {', '.join(available) or 'none'}")
    return model_id

def health() -> dict:
    try:
        _ = models_list()
        return {"status": "ok", "model": MODEL_ID}
    except Exception as e:
        return {"status": "down", "detail": str(e)}

def generate(prompt: str, system: str | None = None, options: dict | None = None) -> str:
    payload = {"model": MODEL_ID, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system
    if options:
        payload["options"] = options
    try:
        out = _post(f"{OLLAMA_HOST}/api/generate", payload)
        return out.get("response", "")
    except Exception as e:
        raise OllamaError(f"Ollama generate failed: {e}")

def stream_generate(prompt: str, system: str | None = None, options: dict | None = None):
    payload = {"model": MODEL_ID, "prompt": prompt, "stream": True}
    if system:
        payload["system"] = system
    if options:
        payload["options"] = options
    session = _get_session()
    try:
        with session.post(f"{OLLAMA_HOST}/api/generate", json=payload, stream=True, timeout=600) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = requests.json.loads(line)  # type: ignore
                except Exception:
                    import json as _json
                    data = _json.loads(line)
                token = data.get("response")
                if token:
                    yield token
            return
    except Exception as e:
        raise OllamaError(f"Ollama stream failed: {e}")

def chat(messages: list[dict]) -> str:
    try:
        out = _post(f"{OLLAMA_HOST}/api/chat", {"model": MODEL_ID, "messages": messages, "stream": False})
        return out.get("message", {}).get("content", "")
    except Exception as e:
        raise OllamaError(f"Ollama chat failed: {e}")
