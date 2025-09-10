"""
Server-Sent Events (SSE) implementation for DGM system using FastAPI EventSourceResponse

This module provides real-time event streaming for the DGM system using FastAPI's
EventSourceResponse with a queue-based event delivery system.
"""

import json
import time
import queue
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

# Global event queue for SSE events
_q = queue.Queue(maxsize=1024)

# Global SSE manager instance
_sse_manager: Optional['SSEManager'] = None

# FastAPI router for SSE endpoints
router = APIRouter()


class SSEManager:
    """
    Simple SSE manager with stub implementation.
    
    TODO: Integrate with FastAPI EventSourceResponse for real SSE streaming
    when WebSocket/SSE infrastructure is available.
    """
    
    def __init__(self):
        self.active = True
        self.event_count = 0
        
    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Emit an SSE event with the given topic and payload.
        
        Args:
            topic: SSE event topic/type (e.g. "dgm.proposals", "dgm.rollback")
            payload: Event data payload to send to clients
        """
        if not self.active:
            return
            
        self.event_count += 1
        
        # Format payload for logging
        try:
            payload_str = json.dumps(payload, separators=(',', ':'))
            if len(payload_str) > 200:
                payload_str = payload_str[:200] + "..."
        except (TypeError, ValueError):
            payload_str = str(payload)[:200]
        
        # Log the event for debugging
        logger.debug(f"SSE Event: {topic} - {payload_str}")
        
    def emit_message(self, topic: str, data: Dict[str, Any], 
                    event_id: Optional[str] = None) -> None:
        """
        Emit an SSE message with standard formatting.
        
        Args:
            topic: SSE event topic
            data: Message data
            event_id: Optional event ID for client tracking
        """
        message = {
            "timestamp": time.time(),
            "event_id": event_id or f"{topic}_{self.event_count + 1}",
            "data": data
        }
        
        self.emit(topic, message)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get SSE manager statistics."""
        return {
            "active": self.active,
            "event_count": self.event_count,
            "implementation": "stub"
        }
    
    def close(self) -> None:
        """Close the SSE manager."""
        self.active = False
        logger.info("SSE Manager closed")
    
    # DGM-specific SSE methods
    def emit_proposal_start(self, proposals: int, allowed_areas: list, session_id: str) -> None:
        """Emit proposal generation start event."""
        self.emit_message(SSETopics.PROPOSALS_START, {
            "proposals": proposals,
            "allowed_areas": allowed_areas,
            "session_id": session_id
        })
    
    def emit_proposal_progress(self, current: int, total: int, patch_id: str = None, patch_summary: dict = None, session_id: str = None) -> None:
        """Emit proposal generation progress event."""
        payload = {
            "current": current,
            "total": total,
            "progress": current / total if total > 0 else 0
        }
        if patch_id:
            payload["patch_id"] = patch_id
        if patch_summary:
            payload["patch_summary"] = patch_summary
        if session_id:
            payload["session_id"] = session_id
        self.emit("dgm.proposals.progress", payload)
    
    def emit_proposal_complete(self, patches: list, rejected: list, execution_time_ms: int, session_id: str) -> None:
        """Emit proposal generation complete event."""
        self.emit_message(SSETopics.PROPOSALS_COMPLETE, {
            "patches": [p.to_summary_dict() if hasattr(p, 'to_summary_dict') else p for p in patches],
            "rejected": rejected,
            "execution_time_ms": execution_time_ms,
            "session_id": session_id
        })
    
    def emit_proposal_error(self, error: str, session_id: str) -> None:
        """Emit proposal generation error event."""
        self.emit_message(SSETopics.ERROR, {
            "error": error,
            "session_id": session_id
        })


def get_sse_manager() -> SSEManager:
    """Get or create the global SSE manager instance."""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager


def get_dgm_sse_manager() -> SSEManager:
    """Get the DGM-specific SSE manager (alias for compatibility)."""
    return get_sse_manager()


def emit(topic: str, payload: Dict[str, Any]) -> None:
    """
    Emit an SSE event to the global event queue.
    
    Args:
        topic: SSE event topic/type
        payload: Event data payload
    """
    evt = {"ts": time.time(), "topic": topic, "payload": payload}
    try:
        _q.put_nowait(evt)
    except queue.Full:
        # Drop oldest event if queue is full
        try:
            _ = _q.get_nowait()
            _q.put_nowait(evt)
        except queue.Empty:
            pass


@router.get("/api/sse")
async def sse_stream():
    """
    SSE endpoint that streams events to connected clients.
    """
    def gen():
        while True:
            try:
                evt = _q.get(timeout=1.0)  # Wait up to 1 second for events
                yield f"data: {json.dumps(evt)}\n\n"
            except queue.Empty:
                # Send keep-alive ping every second if no events
                yield f"data: {json.dumps({'ts': time.time(), 'topic': 'ping', 'payload': {}})}\n\n"
    
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


# Common DGM SSE topics
class SSETopics:
    """Standard SSE topics for DGM system."""
    
    # Proposal generation events
    PROPOSALS_START = "dgm.proposals.start"
    PROPOSALS_GENERATED = "dgm.proposals"
    PROPOSALS_COMPLETE = "dgm.proposals.complete"
    
    # Application and evaluation events
    APPLY_START = "dgm.apply.start"
    APPLY_COMPLETE = "dgm.apply.complete"
    SHADOW_EVAL_START = "dgm.shadow_eval.start"
    SHADOW_EVAL_COMPLETE = "dgm.shadow_eval.complete"
    
    # Guard and safety events
    GUARD_CHECK = "dgm.guard_check"
    GUARD_VIOLATION = "dgm.guard_violation"
    
    # System events
    ROLLBACK = "dgm.rollback"
    COMMIT = "dgm.commit"
    STATUS_UPDATE = "dgm.status"
    ERROR = "dgm.error"


# Convenience functions for common DGM events
def emit_proposals(patches: list, metadata: Dict[str, Any] = None) -> None:
    """Emit DGM proposals event."""
    emit(SSETopics.PROPOSALS_GENERATED, {
        "patches": patches,
        "count": len(patches),
        "metadata": metadata or {}
    })


def emit_rollback(reason: str, details: Dict[str, Any] = None) -> None:
    """Emit DGM rollback event."""
    emit(SSETopics.ROLLBACK, {
        "reason": reason,
        "details": details or {},
        "timestamp": time.time()
    })


def emit_error(error: str, context: Dict[str, Any] = None) -> None:
    """Emit DGM error event."""
    emit(SSETopics.ERROR, {
        "error": error,
        "context": context or {},
        "timestamp": time.time()
    })


def emit_status_update(status: str, details: Dict[str, Any] = None) -> None:
    """Emit DGM status update event."""
    emit(SSETopics.STATUS_UPDATE, {
        "status": status,
        "details": details or {},
        "timestamp": time.time()
    })


# Module-level cleanup
def cleanup():
    """Cleanup SSE resources."""
    global _sse_manager
    if _sse_manager:
        _sse_manager.close()
        _sse_manager = None