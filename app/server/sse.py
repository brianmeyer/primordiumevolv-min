"""
DGM Server-Sent Events (SSE) - Real-time streaming for DGM operations

This module handles SSE streaming for DGM proposal generation, validation,
and application processes.
"""

import json
import logging
import time
import queue
from typing import Dict, Any, Optional
from dataclasses import asdict

logger = logging.getLogger(__name__)


class DGMSSEManager:
    """
    Manages Server-Sent Events for DGM operations.
    
    Provides topic-based streaming for different DGM event types:
    - dgm.proposals: Proposal generation and validation events
    - dgm.canary.update: Canary test progress updates  
    - dgm.commit: System modification commits
    - dgm.rollback: Rollback operations
    """
    
    def __init__(self):
        # Topic-based event queues: {topic: {session_id: queue}}
        self.topic_queues: Dict[str, Dict[str, queue.Queue]] = {
            "dgm.proposals": {},
            "dgm.canary.update": {},
            "dgm.commit": {},
            "dgm.rollback": {}
        }
        
        # Track active sessions
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
    
    def subscribe(self, topic: str, session_id: str) -> queue.Queue:
        """
        Subscribe to a DGM topic.
        
        Args:
            topic: Topic name (e.g., "dgm.proposals")
            session_id: Unique session identifier
            
        Returns:
            Queue for receiving events
        """
        if topic not in self.topic_queues:
            logger.warning(f"Unknown DGM topic: {topic}")
            topic = "dgm.proposals"  # Default fallback
        
        # Create queue for this session
        event_queue = queue.Queue(maxsize=100)
        self.topic_queues[topic][session_id] = event_queue
        
        # Track session
        self.active_sessions[session_id] = {
            "topic": topic,
            "started_at": time.time(),
            "events_sent": 0
        }
        
        logger.info(f"DGM SSE subscription: {session_id} -> {topic}")
        return event_queue
    
    def unsubscribe(self, session_id: str):
        """
        Unsubscribe a session from all topics.
        
        Args:
            session_id: Session to unsubscribe
        """
        # Remove from all topic queues
        for topic_queues in self.topic_queues.values():
            if session_id in topic_queues:
                del topic_queues[session_id]
        
        # Remove from active sessions
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id]
            logger.info(f"DGM SSE unsubscribed: {session_id} ({session_info['events_sent']} events sent)")
            del self.active_sessions[session_id]
    
    def emit(self, topic: str, event_data: Dict[str, Any], session_id: Optional[str] = None):
        """
        Emit an event to topic subscribers.
        
        Args:
            topic: Topic to emit to
            event_data: Event payload
            session_id: Optional specific session (broadcasts to all if None)
        """
        if topic not in self.topic_queues:
            logger.warning(f"Attempted to emit to unknown topic: {topic}")
            return
        
        # Add metadata
        event = {
            "topic": topic,
            "timestamp": time.time(),
            **event_data
        }
        
        # Get target queues
        if session_id:
            target_queues = {session_id: self.topic_queues[topic].get(session_id)}
            if target_queues[session_id] is None:
                logger.warning(f"No subscription found for session {session_id} on topic {topic}")
                return
        else:
            target_queues = self.topic_queues[topic].copy()
        
        # Send to all target queues
        sent_count = 0
        for sid, event_queue in target_queues.items():
            if event_queue is None:
                continue
                
            try:
                event_queue.put_nowait(event)
                sent_count += 1
                
                # Update session stats
                if sid in self.active_sessions:
                    self.active_sessions[sid]["events_sent"] += 1
                    
            except queue.Full:
                logger.warning(f"DGM SSE queue full for session {sid}, dropping event")
                # Optionally unsubscribe overwhelmed clients
                self.unsubscribe(sid)
        
        if sent_count > 0:
            logger.debug(f"DGM SSE emitted to {topic}: {sent_count} recipients")
    
    def emit_proposal_start(self, count: int, allowed_areas: list, session_id: Optional[str] = None):
        """Emit proposal generation start event."""
        self.emit("dgm.proposals", {
            "event": "start",
            "count": count,
            "allowed_areas": allowed_areas,
            "status": "generating"
        }, session_id)
    
    def emit_proposal_progress(self, current: int, total: int, patch_summary: Optional[Dict] = None, session_id: Optional[str] = None):
        """Emit proposal generation progress."""
        event_data = {
            "event": "progress",
            "current": current,
            "total": total,
            "progress": current / total if total > 0 else 0
        }
        
        if patch_summary:
            event_data["patch"] = patch_summary
        
        self.emit("dgm.proposals", event_data, session_id)
    
    def emit_proposal_complete(self, patches: list, rejected: list, execution_time_ms: int, session_id: Optional[str] = None):
        """Emit proposal generation completion."""
        self.emit("dgm.proposals", {
            "event": "complete",
            "count": len(patches),
            "patches": [p.to_summary_dict() if hasattr(p, 'to_summary_dict') else p for p in patches],
            "rejected": rejected,
            "execution_time_ms": execution_time_ms,
            "status": "completed"
        }, session_id)
    
    def emit_proposal_error(self, error: str, session_id: Optional[str] = None):
        """Emit proposal generation error."""
        self.emit("dgm.proposals", {
            "event": "error", 
            "error": error,
            "status": "error"
        }, session_id)
    
    def emit_canary_update(self, test_id: str, status: str, results: Optional[Dict] = None, session_id: Optional[str] = None):
        """Emit canary test update."""
        event_data = {
            "event": "update",
            "test_id": test_id,
            "status": status
        }
        
        if results:
            event_data["results"] = results
        
        self.emit("dgm.canary.update", event_data, session_id)
    
    def emit_commit_update(self, commit_id: str, status: str, details: Optional[Dict] = None, session_id: Optional[str] = None):
        """Emit commit operation update."""
        event_data = {
            "event": "update",
            "commit_id": commit_id,
            "status": status
        }
        
        if details:
            event_data.update(details)
        
        self.emit("dgm.commit", event_data, session_id)
    
    def emit_rollback_update(self, rollback_id: str, status: str, details: Optional[Dict] = None, session_id: Optional[str] = None):
        """Emit rollback operation update.""" 
        event_data = {
            "event": "update",
            "rollback_id": rollback_id,
            "status": status
        }
        
        if details:
            event_data.update(details)
        
        self.emit("dgm.rollback", event_data, session_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get SSE manager statistics."""
        topic_counts = {topic: len(queues) for topic, queues in self.topic_queues.items()}
        total_sessions = len(self.active_sessions)
        
        return {
            "total_sessions": total_sessions,
            "topic_subscribers": topic_counts,
            "active_sessions": list(self.active_sessions.keys()),
            "uptime_seconds": time.time() - getattr(self, '_start_time', time.time())
        }
    
    def cleanup_stale_sessions(self, max_age_seconds: int = 3600):
        """Clean up sessions older than max_age_seconds."""
        current_time = time.time()
        stale_sessions = []
        
        for session_id, session_info in self.active_sessions.items():
            if current_time - session_info["started_at"] > max_age_seconds:
                stale_sessions.append(session_id)
        
        for session_id in stale_sessions:
            logger.info(f"Cleaning up stale DGM SSE session: {session_id}")
            self.unsubscribe(session_id)
        
        return len(stale_sessions)


# Global DGM SSE manager instance
_dgm_sse_manager: Optional[DGMSSEManager] = None


def get_dgm_sse_manager() -> DGMSSEManager:
    """Get the global DGM SSE manager instance."""
    global _dgm_sse_manager
    if _dgm_sse_manager is None:
        _dgm_sse_manager = DGMSSEManager()
        # Set start time for uptime calculation
        _dgm_sse_manager._start_time = time.time()
    return _dgm_sse_manager


def emit_dgm_event(topic: str, event_data: Dict[str, Any], session_id: Optional[str] = None):
    """
    Convenience function to emit DGM events.
    
    Args:
        topic: DGM topic (dgm.proposals, dgm.canary.update, etc.)
        event_data: Event payload
        session_id: Optional specific session
    """
    manager = get_dgm_sse_manager()
    manager.emit(topic, event_data, session_id)


def subscribe_to_dgm_topic(topic: str, session_id: str) -> queue.Queue:
    """
    Convenience function to subscribe to DGM topics.
    
    Args:
        topic: DGM topic name
        session_id: Unique session identifier
        
    Returns:
        Event queue for the subscription
    """
    manager = get_dgm_sse_manager()
    return manager.subscribe(topic, session_id)


def unsubscribe_from_dgm(session_id: str):
    """
    Convenience function to unsubscribe from DGM events.
    
    Args:
        session_id: Session to unsubscribe
    """
    manager = get_dgm_sse_manager()
    manager.unsubscribe(session_id)


# Helper functions for specific event types
def emit_proposals_event(event_type: str, data: Dict[str, Any], session_id: Optional[str] = None):
    """Emit a dgm.proposals event."""
    emit_dgm_event("dgm.proposals", {"event": event_type, **data}, session_id)


def emit_canary_event(event_type: str, data: Dict[str, Any], session_id: Optional[str] = None):
    """Emit a dgm.canary.update event."""
    emit_dgm_event("dgm.canary.update", {"event": event_type, **data}, session_id)


def emit_commit_event(event_type: str, data: Dict[str, Any], session_id: Optional[str] = None):
    """Emit a dgm.commit event."""
    emit_dgm_event("dgm.commit", {"event": event_type, **data}, session_id)


def emit_rollback_event(event_type: str, data: Dict[str, Any], session_id: Optional[str] = None):
    """Emit a dgm.rollback event.""" 
    emit_dgm_event("dgm.rollback", {"event": event_type, **data}, session_id)