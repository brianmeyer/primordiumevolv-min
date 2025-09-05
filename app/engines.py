from app.ollama_client import generate as ollama_gen, MODEL_ID as OLLAMA_MODEL_ID
from app.groq_client import generate as groq_gen, health as groq_health, available as groq_available


def call_engine(engine: str, prompt: str, system: str | None = None, options: dict | None = None):
    # Apply guardrails
    options = options or {}
    
    # Cap max_tokens to prevent runaway generation
    if "max_tokens" not in options:
        options["max_tokens"] = 4096  # Default cap
    else:
        options["max_tokens"] = min(options["max_tokens"], 8192)  # Hard cap
    
    # Ensure reasonable temperature bounds
    if "temperature" in options:
        options["temperature"] = max(0.0, min(2.0, options["temperature"]))
    
    if engine == "groq":
        out, model_id = groq_gen(prompt, system=system, options=options)
        return out, f"groq:{model_id}"
    out = ollama_gen(prompt, system=system, options=options)
    return out, OLLAMA_MODEL_ID


def health():
    return {"groq": groq_health(), "ollama": {"status": "ok"}}

