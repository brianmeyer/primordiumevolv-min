from app.ollama_client import generate as ollama_gen, MODEL_ID as OLLAMA_MODEL_ID
from app.groq_client import generate as groq_gen, health as groq_health, available as groq_available


def call_engine(engine: str, prompt: str, system: str | None = None, options: dict | None = None):
    # Apply guardrails
    options = options or {}
    
    # Handle token limits based on engine
    if engine == "groq":
        # Groq uses max_tokens
        if "max_tokens" not in options:
            options["max_tokens"] = 4096  # Default cap for Groq
        else:
            options["max_tokens"] = min(options["max_tokens"], 8192)  # Hard cap
    else:
        # Ollama uses num_predict (not max_tokens)
        # Convert max_tokens to num_predict if present
        if "max_tokens" in options:
            options["num_predict"] = min(options.pop("max_tokens"), 2048)  # Match META_MAX_TOKENS
        elif "num_predict" not in options:
            options["num_predict"] = 2048  # Match META_MAX_TOKENS default
    
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

