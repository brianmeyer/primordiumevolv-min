import os
from fastapi import FastAPI, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import StreamingResponse
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from dotenv import load_dotenv
from app.ollama_client import generate, health, validate_model, MODEL_ID, stream_generate
from app.tools.web_search import search as web_search
from app.tools.rag import build_or_update_index, query as rag_query
from app.evolve.loop import evolve
from app.models import (
    ChatRequest, EvolveRequest, WebSearchRequest,
    RagQueryRequest, TodoAddRequest, TodoIdRequest,
    SessionCreateRequest, MessageAppendRequest, MemoryQueryRequest,
    MetaRunRequest, HumanRatingRequest
)
from app import memory
from app.middleware import RateLimiter
from app.meta.runner import meta_run
from app.meta import store
from app.errors import (
    ModelError, MemoryError, RAGError, MetaError, ValidationError,
    handle_exception
)
import json
import os
import time
from glob import glob

load_dotenv()
PORT = int(os.getenv("PORT", "8000"))
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "1024"))
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

# GZip responses for large JSON payloads
app.add_middleware(GZipMiddleware, minimum_size=1024)

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

@app.get("/api/health/ollama")
async def ollama_health_ep():
    return JSONResponse(health())

@app.get("/api/health/groq")
async def groq_health_ep():
    try:
        from app.engines import health as h
        return JSONResponse(h())
    except Exception as e:
        return handle_exception(e, "groq_health_failed")

@app.get("/api/health/groq_models")
async def groq_models():
    try:
        from app.groq_client import list_models, available
        if not available():
            return JSONResponse({"status": "down", "detail": "missing GROQ_API_KEY"})
        ms = list_models(force=True)
        return JSONResponse({"status": "ok", "models": [m.get("id") or m.get("name") for m in ms]})
    except Exception as e:
        return JSONResponse({"error": "groq_models_failed", "detail": str(e)}, status_code=500)

@app.get("/api/meta/stream")
async def meta_stream(run_id: int):
    """Server-Sent Events stream for a run's live updates."""
    import anyio
    import json as _json
    from app import realtime as _rt

    q = _rt.subscribe(run_id)

    async def event_generator():
        try:
            while True:
                try:
                    evt = await anyio.to_thread.run_sync(q.get, True, 20)
                    yield f"data: {_json.dumps(evt)}\n\n"
                except Exception:
                    # keep-alive comment every ~20s
                    yield ": keep-alive\n\n"
        finally:
            _rt.unsubscribe(run_id, q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
    # Background warmups (non-blocking)
    try:
        import threading
        def _warm_embeddings():
            try:
                from app.embeddings import get_model
                get_model()
            except Exception:
                pass
        def _warm_groq():
            try:
                from app.groq_client import available, list_models
                if available():
                    list_models(force=True)
            except Exception:
                pass
        threading.Thread(target=_warm_embeddings, daemon=True).start()
        threading.Thread(target=_warm_groq, daemon=True).start()
    except Exception:
        pass

# Chat with memory integration
@app.post("/api/chat")
async def chat_ep(body: ChatRequest):
    try:
        # Save user message
        memory.append_message(body.session_id, "user", body.prompt)
        
        # Optionally enrich with memory context
        context = ""
        try:
            relevant_messages = memory.query_memory(body.prompt, k=3)
            if relevant_messages:
                context = "\n\nRelevant context from past conversations:\n"
                for msg in relevant_messages[:2]:  # Limit to top 2 to avoid token bloat
                    context += f"- {msg['role']}: {msg['content'][:100]}...\n"
        except Exception as mem_e:
            # Continue without context but log memory failure
            print(f"[warn] Memory query failed in chat: {mem_e}")
        
        # Generate response (no local token cap; rely on model defaults)
        enriched_prompt = body.prompt + context
        try:
            out = generate(enriched_prompt, system=body.system)
        except Exception as model_e:
            raise ModelError(f"Generation failed: {str(model_e)}", MODEL_ID)
        
        # Save assistant response
        memory.append_message(body.session_id, "assistant", out)
        
        return JSONResponse({"response": out})
    except Exception as e:
        return handle_exception(e, "chat_failed")

# Streaming chat (SSE)
@app.get("/api/chat/stream")
async def chat_stream(prompt: str, session_id: int, system: Optional[str] = None):
    try:
        # Save user message
        memory.append_message(session_id, "user", prompt)

        # Optional memory context
        context = ""
        try:
            relevant = memory.query_memory(prompt, k=3)
            if relevant:
                context = "\n\nRelevant context from past conversations:\n" + "\n".join(
                    [f"- {m['role']}: {m['content'][:100]}..." for m in relevant[:2]]
                )
        except Exception:
            pass

        enriched = prompt + context
        max_tokens = None

        # Adaptive temperature for stream
        try:
            from app.meta import store as meta_store
            stats = meta_store.get_chat_temp_stats()
        except Exception:
            stats = {}
        import random
        candidates = [0.3, 0.7, 1.0]
        eps = 0.2
        if stats:
            if random.random() < eps:
                chosen_temp = random.choice(candidates)
            else:
                by_avg = sorted(candidates, key=lambda t: stats.get(t, {}).get("avg_reward", 0.0), reverse=True)
                chosen_temp = by_avg[0]
        else:
            chosen_temp = 0.7

        async def _gen():
            full = []
            try:
                for token in stream_generate(enriched, system=system, options={"temperature": chosen_temp}):
                    full.append(token)
                    yield f"data: {{\"token\": {json.dumps(token)} }}\n\n"
                # Save assistant message
                try:
                    mid = memory.append_message_meta(session_id, "assistant", "".join(full), param_temp=chosen_temp)
                except Exception:
                    mid = None
                yield f"data: {{\"done\": true, \"message_id\": {json.dumps(mid)}, \"params\": {{\"temperature\": {chosen_temp} }} }}\n\n"
            except Exception as e:
                yield f"data: {{\"error\": {json.dumps(str(e))} }}\n\n"

        return StreamingResponse(_gen(), media_type="text/event-stream")
    except Exception as e:
        return handle_exception(e, "chat_stream_failed")

# Evolve
@app.post("/api/evolve")
async def evolve_ep(body: EvolveRequest):
    try:
        res = evolve(body.task, body.assertions, body.n)
        return JSONResponse(res)
    except Exception as e:
        return handle_exception(e, "evolve_failed")

# Web search
@app.post("/api/web/search")
async def web_search_ep(body: WebSearchRequest):
    try:
        return JSONResponse({"results": web_search(body.query, body.top_k)})
    except Exception as e:
        return handle_exception(e, "search_failed")

# RAG
@app.post("/api/rag/build")
async def rag_build_ep():
    try:
        build_or_update_index("data")
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return handle_exception(RAGError(f"Index build failed: {str(e)}", "build"))

@app.post("/api/rag/query")
async def rag_query_ep(body: RagQueryRequest):
    try:
        return JSONResponse({"results": rag_query(body.q, body.k)})
    except Exception as e:
        return handle_exception(e, "rag_query_failed")


# Session management
@app.post("/api/session/create")
async def create_session_ep(body: SessionCreateRequest):
    try:
        session_id = memory.create_session(body.title)
        return JSONResponse({"id": session_id})
    except Exception as e:
        return handle_exception(e, "session_create_failed")

@app.get("/api/session/list")
async def list_sessions_ep():
    try:
        sessions = memory.list_sessions()
        return JSONResponse({"sessions": sessions})
    except Exception as e:
        return handle_exception(e, "session_list_failed")

@app.get("/api/session/{session_id}/messages")
async def get_session_messages_ep(session_id: int):
    try:
        messages = memory.list_messages(session_id)
        return JSONResponse({"messages": messages})
    except Exception as e:
        return handle_exception(e, "session_messages_failed")

@app.post("/api/session/{session_id}/append")
async def append_message_ep(session_id: int, body: MessageAppendRequest):
    try:
        message_id = memory.append_message(session_id, body.role, body.content)
        return JSONResponse({"id": message_id})
    except Exception as e:
        return handle_exception(e, "message_append_failed")

# Memory management
@app.post("/api/memory/build")
async def build_memory_ep():
    try:
        memory.build_index()
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return handle_exception(e, "memory_build_failed")

@app.post("/api/memory/query")
async def query_memory_ep(body: MemoryQueryRequest):
    try:
        results = memory.query_memory(body.q, body.k)
        return JSONResponse({"results": results})
    except Exception as e:
        return JSONResponse({"error": "memory_query_failed", "detail": str(e)}, status_code=500)

# Meta-evolution
@app.post("/api/meta/run")
async def meta_run_ep(body: MetaRunRequest):
    try:
        res = meta_run(
            body.task_class, 
            body.task, 
            body.assertions, 
            body.session_id,
            n=body.n, 
            memory_k=body.memory_k, 
            rag_k=body.rag_k,
            operators=body.operators,
            eps=body.eps,
            use_bandit=body.use_bandit,
            bandit_algorithm=body.bandit_algorithm,
            framework_mask=body.framework_mask,
            force_engine=body.force_engine,
            compare_with_groq=body.compare_with_groq,
            judge_mode=body.judge_mode,
            judge_include_rationale=body.judge_include_rationale,
        )
        return JSONResponse(res)
    except Exception as e:
        return handle_exception(e, "meta_run_failed")

@app.post("/api/meta/run_async")
async def meta_run_async_ep(body: MetaRunRequest, request: Request):
    try:
        # Create run immediately and return ID
        run_id = store.save_run_start(body.task_class, body.task, body.assertions or [])
        # Capture optional user preferences from raw body and persist to run config
        try:
            raw = await request.json()
            prefs = (raw or {}).get("user_prefs")
            if prefs:
                cfg = {"user_prefs": prefs}
                store.update_run_config(run_id, cfg)
        except Exception:
            pass

        import threading

        def _worker():
            try:
                meta_run(
                    body.task_class,
                    body.task,
                    body.assertions or [],
                    body.session_id,
                    n=body.n,
                    memory_k=body.memory_k,
                    rag_k=body.rag_k,
                    operators=body.operators,
                    eps=body.eps,
                    use_bandit=body.use_bandit,
                    bandit_algorithm=body.bandit_algorithm,
                    framework_mask=body.framework_mask,
                    force_engine=body.force_engine,
                    compare_with_groq=body.compare_with_groq,
                    judge_mode=body.judge_mode,
                    judge_include_rationale=body.judge_include_rationale,
                    pre_run_id=run_id,
                )
            except Exception as e:
                print(f"[meta_run_async] worker failed: {e}")

        threading.Thread(target=_worker, daemon=True).start()
        return JSONResponse({"status": "started", "run_id": run_id})
    except Exception as e:
        return handle_exception(e, "meta_run_async_failed")

@app.get("/api/meta/stats")
async def meta_stats():
    try:
        # Ensure meta DB schema exists even before first run
        store.init_db()
        import time
        operator_stats_dict = store.list_operator_stats()
        # Convert dict to list for easier frontend consumption and sanitize infinite values
        def sanitize_float(val):
            if val == float('-inf') or val == float('inf') or val != val:  # NaN check
                return 0.0
            return val
        
        operator_stats_list = [
            {"name": name, "n": stats["n"], "avg_reward": sanitize_float(stats["avg_reward"])}
            for name, stats in operator_stats_dict.items()
        ]
        # Sanitize recent_runs data too
        recent_runs = store.recent_runs(None, 30)
        for run in recent_runs:
            if 'best_score' in run and run['best_score'] is not None:
                run['best_score'] = sanitize_float(run['best_score'])
        
        return JSONResponse({
            "operator_stats": operator_stats_list,
            "recent_runs": recent_runs,
            "now": time.time()
        })
    except Exception as e:
        return handle_exception(e, "meta_stats_failed")

@app.get("/api/meta/recipes")
async def meta_recipes(task_class: Optional[str] = Query(default=None)):
    try:
        recipes = store.recipes_by_class((task_class or "").strip().lower() if task_class else "", 10)
        return JSONResponse({"recipes": recipes})
    except Exception as e:
        return handle_exception(e, "meta_recipes_failed")

@app.get("/api/meta/trend")
async def meta_trend(task_class: Optional[str] = Query(default=None)):
    try:
        normalized_task_class = (task_class or "").strip().lower() if task_class else None
        trend_data = store.recent_runs(normalized_task_class, 50)
        return JSONResponse({"trend": trend_data})
    except Exception as e:
        return handle_exception(e, "meta_trend_failed")

@app.get("/api/meta/runs/{run_id}")
async def get_meta_run(run_id: int):
    """Get detailed information about a specific meta-evolution run."""
    try:
        # Get run details from database
        c = store._conn()
        cursor = c.execute(
            "SELECT task_class, task, started_at, finished_at, best_score, operator_names_json FROM runs WHERE id = ?",
            (run_id,)
        )
        run_data = cursor.fetchone()
        if not run_data:
            return JSONResponse({"error": "run_not_found"}, status_code=404)
        
        # Get variants for this run
        cursor = c.execute(
            "SELECT id, operator_name, score, execution_time_ms, created_at, model_id FROM variants WHERE run_id = ? ORDER BY created_at",
            (run_id,)
        )
        variants = cursor.fetchall()
        c.close()
        
        return JSONResponse({
            "run_id": run_id,
            "task_class": run_data[0],
            "task": run_data[1],
            "started_at": run_data[2],
            "finished_at": run_data[3],
            "best_score": run_data[4],
            "operator_sequence": json.loads(run_data[5]) if run_data[5] else [],
            "variants": [
                {
                    "id": v[0],
                    "operator": v[1],
                    "score": v[2],
                    "duration_ms": v[3],
                    "timestamp": v[4],
                    "model_id": v[5]
                } for v in variants
            ]
        })
    except Exception as e:
        return handle_exception(e, "get_meta_run_failed")

@app.get("/api/meta/variants/{variant_id}")
async def get_variant_output(variant_id: int):
    """Get the full output for a specific variant."""
    try:
        c = store._conn()
        cursor = c.execute(
            "SELECT output FROM variants WHERE id = ?",
            (variant_id,)
        )
        variant_data = cursor.fetchone()
        c.close()
        
        if not variant_data:
            return JSONResponse({"error": "variant_not_found"}, status_code=404)
        
        return JSONResponse({
            "variant_id": variant_id,
            "output": variant_data[0]
        })
    except Exception as e:
        return handle_exception(e, "get_variant_output_failed")

@app.get("/api/meta/logs")
async def get_meta_logs(limit: int = Query(default=50, le=200)):
    """Get recent structured log entries."""
    try:
        import glob
        log_files = glob.glob("logs/*.json")
        log_entries = []
        
        for log_file in sorted(log_files, reverse=True)[:limit]:
            try:
                with open(log_file, "r") as f:
                    log_data = json.load(f)
                    log_entries.append({
                        "file": os.path.basename(log_file),
                        "artifact_type": log_data.get("artifact_type"),
                        "timestamp": log_data.get("timestamp"),
                        "data": log_data.get("data")
                    })
            except Exception:
                continue
        
        return JSONResponse({"logs": log_entries})
    except Exception as e:
        return handle_exception(e, "get_meta_logs_failed")

@app.get("/api/meta/operators/stats")
async def get_operator_performance():
    """Get detailed operator performance statistics."""
    try:
        stats = store.list_operator_stats()
        # Enhance with timing data
        enhanced_stats = []
        for name, data in stats.items():
            enhanced_stats.append({
                "name": name,
                "selections": data["n"],
                "avg_reward": data["avg_reward"],
                "total_time_ms": data.get("total_time_ms", 0),
                "avg_time_ms": data.get("total_time_ms", 0) / max(1, data["n"]),
                "last_used_at": data.get("last_used_at", 0)
            })
        
        # Sort by average reward descending
        enhanced_stats.sort(key=lambda x: x["avg_reward"], reverse=True)
        
        return JSONResponse({"operator_stats": enhanced_stats})
    except Exception as e:
        return handle_exception(e, "get_operator_performance_failed")

@app.post("/api/meta/eval")
async def meta_eval(
    request: Request
):
    """
    Runs each line of eval JSONL via meta_run and returns summary + per-item results.
    """
    try:
        # Get query parameters
        params = request.query_params
        session_id = int(params.get("session_id"))
        set_path = params.get("set_path", "").strip()
        framework_mask = params.get("framework_mask", "").strip()
        use_bandit = params.get("use_bandit", "true").lower() == "true"
        n = int(params.get("n", "12"))
        memory_k = int(params.get("memory_k", "3"))
        rag_k = int(params.get("rag_k", "3"))
        
        if not set_path.startswith("eval/"):
            return JSONResponse({"error": "bad_path", "detail": "set_path must be under eval/."}, status_code=400)
        if not os.path.exists(set_path):
            return JSONResponse({"error": "not_found", "detail": set_path}, status_code=404)

        # Parse framework mask
        framework_mask_list = None
        if framework_mask:
            framework_mask_list = framework_mask.split(",")

        results = []
        with open(set_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): 
                    continue
                item = json.loads(line)
                task_class = (item.get("task_class", "") or "").strip()
                task = (item.get("task", "") or "").strip()
                assertions = item.get("assertions") or []
                test_cmd = item.get("test_cmd")
                test_weight = float(item.get("test_weight", 0.7 if test_cmd else 0.0))

                res = meta_run(
                    task_class=task_class,
                    task=task,
                    assertions=assertions,
                    session_id=session_id,
                    n=n,
                    memory_k=memory_k,
                    rag_k=rag_k,
                    operators=None,
                    framework_mask=framework_mask_list,
                    use_bandit=use_bandit,
                    test_cmd=test_cmd,
                    test_weight=test_weight
                )
                results.append({
                    "task_class": task_class,
                    "task": task[:120],
                    "best_score": res.get("best_score"),
                    "best_recipe": res.get("best_recipe"),
                })

        # basic summary
        scores = [r["best_score"] for r in results if isinstance(r.get("best_score"), (int, float))]
        summary = {
            "count": len(results),
            "mean_best_score": (sum(scores) / len(scores)) if scores else None,
            "min_best_score": min(scores) if scores else None,
            "max_best_score": max(scores) if scores else None,
            "ts": time.time()
        }
        return JSONResponse({"summary": summary, "results": results})
    except Exception as e:
        return handle_exception(e, "meta_eval_failed")

@app.post("/api/meta/rate")
async def human_rate_variant(body: HumanRatingRequest):
    """Submit human feedback rating for a variant response."""
    try:
        rating_id = store.save_human_rating(
            variant_id=body.variant_id,
            human_score=body.human_score,
            feedback=body.feedback
        )
        return JSONResponse({
            "status": "success",
            "rating_id": rating_id,
            "message": "Rating saved successfully"
        })
    except Exception as e:
        return handle_exception(e, "human_rating_failed")

@app.get("/api/meta/analytics")
async def get_analytics():
    """Get comprehensive analytics showing system improvement over time."""
    try:
        analytics = store.get_analytics_overview()
        
        # Clean up any remaining infinite values before JSON serialization
        import json
        import math
        
        def clean_value(obj):
            if isinstance(obj, dict):
                return {k: clean_value(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_value(item) for item in obj]
            elif isinstance(obj, float):
                if math.isinf(obj) or math.isnan(obj):
                    return None
                return obj
            else:
                return obj
        
        cleaned_analytics = clean_value(analytics)
        # Augment with rating analytics
        try:
            c = store._conn()
            cur = c.execute("SELECT id, config_json FROM runs WHERE finished_at IS NOT NULL")
            prompted_run_ids = []
            for run_id, cfg in cur.fetchall():
                try:
                    cfg_obj = json.loads(cfg) if cfg else {}
                    mode = ((cfg_obj or {}).get("user_prefs") or {}).get("ratings_mode", "prompted")
                    if mode != "off":
                        prompted_run_ids.append(run_id)
                except Exception:
                    prompted_run_ids.append(run_id)
            # Count variants for prompted runs
            shown = 0
            if prompted_run_ids:
                q_marks = ",".join(["?"]*len(prompted_run_ids))
                vcur = c.execute(f"SELECT COUNT(*) FROM variants WHERE run_id IN ({q_marks})", tuple(prompted_run_ids))
                shown = int(vcur.fetchone()[0] or 0)
            rcur = c.execute("SELECT COUNT(*) FROM human_ratings")
            received = int(rcur.fetchone()[0] or 0)
            skipped = max(0, shown - received)
            cleaned_analytics["human_ratings"] = {"ratings_shown": shown, "ratings_received": received, "ratings_skipped": skipped}
            c.close()
        except Exception:
            pass
        return JSONResponse(cleaned_analytics)
    except Exception as e:
        return handle_exception(e, "analytics_failed")

@app.post("/api/meta/reset")
async def reset_learning():
    """Clear all operator learning statistics to start fresh."""
    try:
        result = store.clear_operator_stats()
        return JSONResponse(result)
    except Exception as e:
        return handle_exception(e, "reset_learning_failed")

# ---- Golden Set ----

@app.get("/api/golden/list")
async def golden_list():
    try:
        base = os.path.join(os.path.dirname(__file__), "..", "storage", "golden")
        items = []
        for path in sorted(glob(os.path.join(base, "*.json"))):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                items.append({
                    "id": data.get("id") or os.path.splitext(os.path.basename(path))[0],
                    "task_class": data.get("task_class"),
                    "flags": data.get("flags", {}),
                })
            except Exception:
                continue
        return JSONResponse({"items": items})
    except Exception as e:
        return handle_exception(e, "golden_list_failed")

@app.post("/api/golden/run")
async def golden_run(request: Request):
    try:
        body = await request.json()
        ids = (body or {}).get("ids")  # optional subset
        base = os.path.join(os.path.dirname(__file__), "..", "storage", "golden")
        files = sorted(glob(os.path.join(base, "*.json")))
        per_item = []
        import random
        ts = int(time.time())
        for path in files:
            with open(path, "r") as f:
                item = json.load(f)
            slug = item.get("id") or os.path.splitext(os.path.basename(path))[0]
            if ids and slug not in ids:
                continue
            # Guardrails: deterministic, web off, rag pinned
            seed = int(item.get("seed", 123))
            random.seed(seed)
            task_class = item.get("task_class", "code")
            task = item.get("task", "")
            assertions = item.get("assertions") or []
            flags = item.get("flags") or {}
            n = 8
            res = meta_run(
                task_class=task_class,
                task=task,
                assertions=assertions,
                session_id=None,
                n=n,
                memory_k=int(flags.get("memory_k", 0)),
                rag_k=int(flags.get("rag_k", 0)),
                operators=None,
                framework_mask=["SEAL", "SAMPLING"] + (["WEB"] if flags.get("web") else []),
                use_bandit=True,
                test_cmd=None,
                test_weight=0.0,
                force_engine="ollama",
                compare_with_groq=False,
                judge_mode="off",
                judge_include_rationale=True,
            )
            per_item.append({
                "id": slug,
                "outcome_reward": res.get("metrics", {}).get("best_total_reward", None),
                "process_reward": None,
                "cost_penalty": None,
                "total_reward": res.get("best_total_reward")
            })
        # Aggregate
        valid = [p for p in per_item if isinstance(p.get("total_reward"), (int, float))]
        avg_total_reward = sum(p["total_reward"] for p in valid) / len(valid) if valid else None
        artifacts_dir = os.path.join("runs", str(ts))
        os.makedirs(artifacts_dir, exist_ok=True)
        kpis = {"per_item": per_item, "aggregate": {"avg_total_reward": avg_total_reward, "steps_to_best": None, "avg_cost_ratio": None}}
        with open(os.path.join(artifacts_dir, "golden_kpis.json"), "w") as f:
            json.dump(kpis, f, indent=2)
        return JSONResponse(kpis)
    except Exception as e:
        return handle_exception(e, "golden_run_failed")

# ---- Phase 4: criticize–edit–test loop ----

@app.post("/api/meta/phase4/run")
async def phase4_run():
    try:
        ts = int(time.time())
        artifacts_dir = os.path.join("runs", str(ts))
        os.makedirs(artifacts_dir, exist_ok=True)
        # Critic note (placeholder)
        critic_note = "Evaluate reward alignment and operator diversity; propose minimal tweaks to scoring weights if KPIs regress."
        # Run Golden Set before/after (no-op edit in this implementation; scaffold for future patches)
        before = await golden_run(Request({'type': 'http'}))  # Not strictly used; compute fresh below
        # Re-run golden set
        base = os.path.join(os.path.dirname(__file__), "..", "storage", "golden")
        files = sorted(glob(os.path.join(base, "*.json")))
        per_item = []
        import random
        for path in files[:3]:  # at least 3 items
            with open(path, "r") as f:
                item = json.load(f)
            random.seed(int(item.get("seed", 123)))
            res = meta_run(
                task_class=item.get("task_class", "code"),
                task=item.get("task", ""),
                assertions=item.get("assertions") or [],
                session_id=None,
                n=6,
                memory_k=0,
                rag_k=int((item.get("flags") or {}).get("rag_k", 0)),
                operators=None,
                framework_mask=["SEAL", "SAMPLING"],
                use_bandit=True,
                test_cmd=None,
                test_weight=0.0,
                force_engine="ollama",
                compare_with_groq=False,
                judge_mode="off",
                judge_include_rationale=True,
            )
            per_item.append(res.get("best_total_reward") or 0.0)
        after_avg = sum(per_item)/len(per_item) if per_item else 0.0
        before_avg = after_avg  # no-op edit baseline
        delta = after_avg - before_avg
        decision = (delta >= 0.05)
        code_loop = {
            "critic_note": critic_note,
            "patch_summary": "no-op (scaffold)",
            "golden_kpis_before_after": {"before_avg_total_reward": before_avg, "after_avg_total_reward": after_avg, "delta": delta},
            "decision": decision
        }
        with open(os.path.join(artifacts_dir, "code_loop.json"), "w") as f:
            json.dump(code_loop, f, indent=2)
        return JSONResponse(code_loop)
    except Exception as e:
        return handle_exception(e, "phase4_failed")
