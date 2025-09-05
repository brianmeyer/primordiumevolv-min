import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.ollama_client import generate, health, validate_model, MODEL_ID
from app.tools.web_search import search as web_search
from app.tools.rag import build_or_update_index, query as rag_query
from app.tools import todo as todo
from app.evolve.loop import evolve
from app.models import (
    ChatRequest, EvolveRequest, WebSearchRequest,
    RagQueryRequest, TodoAddRequest, TodoIdRequest
)
from app.middleware import RateLimiter

load_dotenv()
PORT = int(os.getenv("PORT", "8000"))
RATE = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
CORS_ALLOW = [x for x in os.getenv("CORS_ALLOW", "http://localhost:3000,http://localhost:8000").split(",") if x]

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limit middleware
rate_limiter = RateLimiter(per_min=RATE)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    return await rate_limiter(request, call_next)

# Static UI
STATIC_DIR = os.path.join(os.path.dirname(__file__), "ui")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# Health
@app.get("/api/health")
async def health_ep():
    return JSONResponse(health())

# Validate model at startup
@app.on_event("startup")
async def _startup():
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    try:
        validate_model(MODEL_ID)
    except Exception as e:
        # Keep app up but report unhealthy
        print(f"[warn] Model validation failed: {e}")

# Chat
@app.post("/api/chat")
async def chat_ep(body: ChatRequest):
    try:
        out = generate(body.prompt, system=body.system)
        return JSONResponse({"response": out})
    except Exception as e:
        return JSONResponse({"error": "chat_failed", "detail": str(e)}, status_code=500)

# Evolve
@app.post("/api/evolve")
async def evolve_ep(body: EvolveRequest):
    try:
        res = evolve(body.task, body.assertions, body.n)
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": "evolve_failed", "detail": str(e)}, status_code=500)

# Web search
@app.post("/api/web/search")
async def web_search_ep(body: WebSearchRequest):
    try:
        return JSONResponse({"results": web_search(body.query, body.top_k)})
    except Exception as e:
        return JSONResponse({"error": "search_failed", "detail": str(e)}, status_code=502)

# RAG
@app.post("/api/rag/build")
async def rag_build_ep():
    try:
        build_or_update_index("data")
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"error": "rag_build_failed", "detail": str(e)}, status_code=500)

@app.post("/api/rag/query")
async def rag_query_ep(body: RagQueryRequest):
    try:
        return JSONResponse({"results": rag_query(body.q, body.k)})
    except Exception as e:
        return JSONResponse({"error": "rag_query_failed", "detail": str(e)}, status_code=500)

# TODO
@app.post("/api/todo/add")
async def todo_add(body: TodoAddRequest):
    try:
        todo.add(body.text)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"error": "todo_add_failed", "detail": str(e)}, status_code=500)

@app.get("/api/todo/list")
async def todo_list():
    try:
        return JSONResponse({"todos": todo.list_all()})
    except Exception as e:
        return JSONResponse({"error": "todo_list_failed", "detail": str(e)}, status_code=500)

@app.post("/api/todo/complete")
async def todo_complete(body: TodoIdRequest):
    try:
        todo.complete(int(body.id))
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"error": "todo_complete_failed", "detail": str(e)}, status_code=500)

@app.post("/api/todo/delete")
async def todo_delete(body: TodoIdRequest):
    try:
        todo.delete(int(body.id))
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"error": "todo_delete_failed", "detail": str(e)}, status_code=500)