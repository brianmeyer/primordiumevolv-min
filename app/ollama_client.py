import os, requests
from dotenv import load_dotenv
from typing import List

load_dotenv()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_ID = os.getenv("MODEL_ID", "qwen3:4b")

class OllamaError(RuntimeError):
    pass

def _get(url: str):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def _post(url: str, payload: dict):
    r = requests.post(url, json=payload, timeout=600)
    r.raise_for_status()
    return r.json()

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

def chat(messages: list[dict]) -> str:
    try:
        out = _post(f"{OLLAMA_HOST}/api/chat", {"model": MODEL_ID, "messages": messages, "stream": False})
        return out.get("message", {}).get("content", "")
    except Exception as e:
        raise OllamaError(f"Ollama chat failed: {e}")