"""
Structured error handling for PrimordiumEvolv.
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException
from fastapi.responses import JSONResponse
import traceback
import time

class AppError(Exception):
    """Base application error with structured details."""
    
    def __init__(self, 
                 error_type: str, 
                 detail: str, 
                 status_code: int = 500, 
                 context: Optional[Dict[str, Any]] = None):
        self.error_type = error_type
        self.detail = detail
        self.status_code = status_code
        self.context = context or {}
        self.timestamp = time.time()
        super().__init__(detail)

class ModelError(AppError):
    """Ollama model-related errors."""
    def __init__(self, detail: str, model_id: str = None):
        super().__init__("model_error", detail, 502, {"model_id": model_id})

class MemoryError(AppError):
    """Memory/embedding-related errors."""
    def __init__(self, detail: str, operation: str = None):
        super().__init__("memory_error", detail, 500, {"operation": operation})

class RAGError(AppError):
    """RAG/indexing-related errors."""
    def __init__(self, detail: str, operation: str = None):
        super().__init__("rag_error", detail, 500, {"operation": operation})

class MetaError(AppError):
    """Meta-evolution-related errors."""
    def __init__(self, detail: str, run_id: int = None, operator: str = None):
        super().__init__("meta_error", detail, 500, {"run_id": run_id, "operator": operator})

class ValidationError(AppError):
    """Input validation errors."""
    def __init__(self, detail: str, field: str = None):
        super().__init__("validation_error", detail, 400, {"field": field})

def error_response(error: AppError, include_traceback: bool = False) -> JSONResponse:
    """Generate structured error response."""
    response_data = {
        "error": error.error_type,
        "detail": error.detail,
        "timestamp": error.timestamp,
        "context": error.context
    }
    
    if include_traceback:
        response_data["traceback"] = traceback.format_exc()
    
    return JSONResponse(response_data, status_code=error.status_code)

def handle_exception(e: Exception, fallback_type: str = "internal_error") -> JSONResponse:
    """Handle generic exceptions with structured response."""
    if isinstance(e, AppError):
        return error_response(e)
    
    # Convert generic exception to structured error
    error = AppError(
        fallback_type,
        str(e),
        status_code=500,
        context={"exception_type": type(e).__name__}
    )
    return error_response(error)