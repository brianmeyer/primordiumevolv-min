"""
Lightweight JSONL registry for DGM proposal tracking and evaluation history.

Provides atomic append operations with rotation for production-grade event logging.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from app.util.log import get_logger

logger = get_logger(__name__)

REGISTRY_FILE = "data/dgm_registry.jsonl"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
VALID_EVENTS = {"propose", "dry_run", "shadow_eval", "guard", "winner", "error"}


class DGMRegistry:
    """
    Lightweight JSONL registry for DGM events with rotation.
    
    Thread-safe atomic appends with file rotation when size exceeds 10MB.
    """
    
    def __init__(self, file_path: str = REGISTRY_FILE):
        self.file_path = file_path
        self.data_dir = Path(file_path).parent
        self.data_dir.mkdir(exist_ok=True)
        
    def record(self, patch_id: str, event: str, data: Dict[str, Any]) -> None:
        """
        Record a DGM event with atomic append.
        
        Args:
            patch_id: Unique patch identifier
            event: Event type (propose, dry_run, shadow_eval, guard, winner, error)
            data: Event-specific data dictionary
        """
        if event not in VALID_EVENTS:
            logger.warning(f"Invalid event type: {event}. Valid types: {VALID_EVENTS}")
            return
            
        # Check if rotation needed before write
        self._rotate_if_needed()
        
        record = {
            "ts": datetime.now().isoformat(),
            "patch_id": patch_id,
            "event": event,
            **data
        }
        
        # Atomic append
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, separators=(',', ':')) + '\n')
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"Failed to record event {event} for patch {patch_id}: {e}")
            
    def list_recent(self, n: int = 50) -> List[Dict[str, Any]]:
        """
        Get the last n records, newest first.
        
        Args:
            n: Number of recent records to return
            
        Returns:
            List of record dictionaries, newest first
        """
        if not os.path.exists(self.file_path):
            return []
            
        records = []
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipping malformed JSON line: {e}")
                            continue
        except Exception as e:
            logger.error(f"Failed to read registry: {e}")
            return []
            
        # Return newest first, limited to n records
        return records[-n:][::-1]
        
    def list_by_patch(self, patch_id: str) -> List[Dict[str, Any]]:
        """
        Get all records for a specific patch ID, newest first.
        
        Args:
            patch_id: Patch identifier to filter by
            
        Returns:
            List of record dictionaries for the patch, newest first
        """
        if not os.path.exists(self.file_path):
            return []
            
        patch_records = []
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            if record.get("patch_id") == patch_id:
                                patch_records.append(record)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipping malformed JSON line: {e}")
                            continue
        except Exception as e:
            logger.error(f"Failed to read registry for patch {patch_id}: {e}")
            return []
            
        # Return newest first
        return patch_records[::-1]
        
    def stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.
        
        Returns:
            Dictionary with event counts and metadata
        """
        if not os.path.exists(self.file_path):
            return {
                "total_records": 0,
                "event_counts": {},
                "last_ts": None,
                "file_size_mb": 0.0
            }
            
        event_counts = {}
        total_records = 0
        last_ts = None
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            total_records += 1
                            event = record.get("event", "unknown")
                            event_counts[event] = event_counts.get(event, 0) + 1
                            last_ts = record.get("ts")  # Keep updating to get the last one
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipping malformed JSON line: {e}")
                            continue
                            
            file_size_mb = os.path.getsize(self.file_path) / (1024 * 1024)
            
        except Exception as e:
            logger.error(f"Failed to generate stats: {e}")
            return {
                "total_records": 0,
                "event_counts": {},
                "last_ts": None,
                "file_size_mb": 0.0,
                "error": str(e)
            }
            
        return {
            "total_records": total_records,
            "event_counts": event_counts,
            "last_ts": last_ts,
            "file_size_mb": round(file_size_mb, 2)
        }
        
    def _rotate_if_needed(self) -> None:
        """Rotate the registry file if it exceeds max size."""
        if not os.path.exists(self.file_path):
            return
            
        if os.path.getsize(self.file_path) > MAX_FILE_SIZE:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_name = f"{self.file_path}.{timestamp}"
            
            try:
                shutil.move(self.file_path, rotated_name)
                logger.info(f"Registry rotated to {rotated_name}")
            except Exception as e:
                logger.error(f"Failed to rotate registry: {e}")


# Global registry instance
_registry = None

def get_registry() -> DGMRegistry:
    """Get or create the global registry instance."""
    global _registry
    if _registry is None:
        _registry = DGMRegistry()
    return _registry