"""
DGM Storage - Artifact storage for committed patches and metadata

This module handles storage of patch artifacts, commit history, and metadata
for the DGM system's committed modifications.
"""

import os
import json
import time
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from app.dgm.types import MetaPatch
from app.dgm.eval import ShadowEvalResult
from app.config import DGM_PATCH_STORAGE_PATH

logger = logging.getLogger(__name__)


@dataclass
class CommitArtifact:
    """Represents a committed patch with all metadata."""
    patch_id: str
    commit_sha: str
    timestamp: float
    
    # Patch data
    area: str
    origin: str
    notes: str
    diff: str
    loc_delta: int
    
    # Shadow evaluation results
    reward_delta: Optional[float] = None
    error_rate_delta: Optional[float] = None
    latency_p95_delta: Optional[float] = None
    
    # Commit metadata
    commit_message: str = ""
    test_results: Optional[Dict[str, Any]] = None
    rollback_sha: Optional[str] = None
    status: str = "committed"  # "committed", "rolled_back", "failed"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommitArtifact':
        """Create from dict."""
        return cls(**data)


class PatchStorage:
    """
    Manages storage of DGM patch artifacts and commit history.
    """
    
    def __init__(self, storage_path: str = None):
        self.storage_path = Path(storage_path or DGM_PATCH_STORAGE_PATH)
        self._ensure_storage_exists()
    
    def _ensure_storage_exists(self):
        """Ensure storage directories exist."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"DGM storage path ready: {self.storage_path}")
    
    def _get_timestamp_dir(self, timestamp: float = None) -> Path:
        """Get timestamped subdirectory for organizing patches."""
        if timestamp is None:
            timestamp = time.time()
        
        # Format: YYYYMMDD_HHMMSS
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp)
        dir_name = dt.strftime("%Y%m%d_%H%M%S")
        
        return self.storage_path / dir_name
    
    def save_patch_artifact(self, patch: MetaPatch, shadow_result: Optional[ShadowEvalResult] = None,
                          commit_sha: str = "", test_results: Optional[Dict[str, Any]] = None) -> str:
        """
        Save a patch artifact to storage.
        
        Args:
            patch: The patch to save
            shadow_result: Optional shadow evaluation results
            commit_sha: Git commit SHA if committed
            test_results: Optional test results
            
        Returns:
            Path to saved artifact
        """
        timestamp = time.time()
        artifact_dir = self._get_timestamp_dir(timestamp)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Create commit artifact
        artifact = CommitArtifact(
            patch_id=patch.id,
            commit_sha=commit_sha,
            timestamp=timestamp,
            area=patch.area,
            origin=patch.origin,
            notes=patch.notes,
            diff=patch.diff,
            loc_delta=patch.loc_delta,
            commit_message=f"[DGM] {patch.id[:8]} {patch.area} - {patch.notes}",
            test_results=test_results,
            status="committed" if commit_sha else "pending"
        )
        
        # Add shadow evaluation results if available
        if shadow_result:
            artifact.reward_delta = shadow_result.reward_delta
            artifact.error_rate_delta = shadow_result.error_rate_delta
            artifact.latency_p95_delta = shadow_result.latency_p95_delta
        
        # Save diff file
        diff_file = artifact_dir / f"{patch.id}.diff"
        with open(diff_file, 'w') as f:
            f.write(patch.diff)
        
        # Save metadata JSON
        meta_file = artifact_dir / f"{patch.id}.json"
        with open(meta_file, 'w') as f:
            json.dump(artifact.to_dict(), f, indent=2)
        
        # Save to index
        self._update_index(artifact)
        
        logger.info(f"Saved patch artifact: {artifact_dir}/{patch.id}")
        return str(artifact_dir)
    
    def _update_index(self, artifact: CommitArtifact):
        """Update the central index of all committed patches."""
        index_file = self.storage_path / "index.json"
        
        # Load existing index
        if index_file.exists():
            with open(index_file, 'r') as f:
                index = json.load(f)
        else:
            index = {"patches": [], "stats": {}}
        
        # Add/update entry
        patch_entry = {
            "patch_id": artifact.patch_id,
            "timestamp": artifact.timestamp,
            "area": artifact.area,
            "commit_sha": artifact.commit_sha,
            "reward_delta": artifact.reward_delta,
            "status": artifact.status
        }
        
        # Remove old entry if exists
        index["patches"] = [p for p in index["patches"] if p["patch_id"] != artifact.patch_id]
        index["patches"].append(patch_entry)
        
        # Update stats
        index["stats"]["total_patches"] = len(index["patches"])
        index["stats"]["committed_patches"] = len([p for p in index["patches"] if p["status"] == "committed"])
        index["stats"]["rolled_back_patches"] = len([p for p in index["patches"] if p["status"] == "rolled_back"])
        index["stats"]["last_updated"] = time.time()
        
        # Save updated index
        with open(index_file, 'w') as f:
            json.dump(index, f, indent=2)
    
    def get_patch_artifact(self, patch_id: str) -> Optional[CommitArtifact]:
        """
        Retrieve a patch artifact by ID.
        
        Args:
            patch_id: ID of patch to retrieve
            
        Returns:
            CommitArtifact or None if not found
        """
        # Search for patch in storage
        for dir_path in self.storage_path.iterdir():
            if not dir_path.is_dir():
                continue
            
            meta_file = dir_path / f"{patch_id}.json"
            if meta_file.exists():
                with open(meta_file, 'r') as f:
                    data = json.load(f)
                return CommitArtifact.from_dict(data)
        
        logger.warning(f"Patch artifact not found: {patch_id}")
        return None
    
    def list_artifacts(self, status_filter: Optional[str] = None) -> List[CommitArtifact]:
        """
        List all stored patch artifacts.
        
        Args:
            status_filter: Optional status to filter by
            
        Returns:
            List of CommitArtifact objects
        """
        artifacts = []
        
        for dir_path in self.storage_path.iterdir():
            if not dir_path.is_dir():
                continue
            
            for json_file in dir_path.glob("*.json"):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    artifact = CommitArtifact.from_dict(data)
                    
                    if status_filter is None or artifact.status == status_filter:
                        artifacts.append(artifact)
                        
                except Exception as e:
                    logger.warning(f"Failed to load artifact {json_file}: {e}")
        
        # Sort by timestamp, newest first
        artifacts.sort(key=lambda a: a.timestamp, reverse=True)
        return artifacts
    
    def update_artifact_status(self, patch_id: str, status: str, 
                              rollback_sha: Optional[str] = None) -> bool:
        """
        Update the status of a patch artifact.
        
        Args:
            patch_id: ID of patch to update
            status: New status ("committed", "rolled_back", "failed")
            rollback_sha: Optional rollback commit SHA
            
        Returns:
            True if updated successfully
        """
        artifact = self.get_patch_artifact(patch_id)
        if not artifact:
            return False
        
        artifact.status = status
        if rollback_sha:
            artifact.rollback_sha = rollback_sha
        
        # Find and update the file
        for dir_path in self.storage_path.iterdir():
            if not dir_path.is_dir():
                continue
            
            meta_file = dir_path / f"{patch_id}.json"
            if meta_file.exists():
                with open(meta_file, 'w') as f:
                    json.dump(artifact.to_dict(), f, indent=2)
                
                # Update index
                self._update_index(artifact)
                
                logger.info(f"Updated patch artifact status: {patch_id} -> {status}")
                return True
        
        return False
    
    def get_latest_commit(self) -> Optional[CommitArtifact]:
        """Get the most recent committed patch."""
        artifacts = self.list_artifacts(status_filter="committed")
        return artifacts[0] if artifacts else None
    
    def get_commit_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent commit history.
        
        Args:
            limit: Maximum number of commits to return
            
        Returns:
            List of commit summaries
        """
        artifacts = self.list_artifacts()[:limit]
        
        history = []
        for artifact in artifacts:
            history.append({
                "patch_id": artifact.patch_id,
                "timestamp": artifact.timestamp,
                "area": artifact.area,
                "commit_sha": artifact.commit_sha[:8] if artifact.commit_sha else "pending",
                "reward_delta": artifact.reward_delta,
                "status": artifact.status,
                "notes": artifact.notes
            })
        
        return history
    
    def cleanup_old_artifacts(self, days: int = 30) -> int:
        """
        Remove artifacts older than specified days.
        
        Args:
            days: Age threshold in days
            
        Returns:
            Number of artifacts removed
        """
        cutoff_time = time.time() - (days * 24 * 3600)
        removed_count = 0
        
        for dir_path in self.storage_path.iterdir():
            if not dir_path.is_dir():
                continue
            
            # Check directory age
            dir_stat = dir_path.stat()
            if dir_stat.st_mtime < cutoff_time:
                try:
                    shutil.rmtree(dir_path)
                    removed_count += 1
                    logger.info(f"Removed old artifact directory: {dir_path}")
                except Exception as e:
                    logger.error(f"Failed to remove {dir_path}: {e}")
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old artifact directories")
        
        return removed_count
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get statistics about patch storage."""
        total_patches = 0
        total_size_bytes = 0
        status_counts = {}
        area_counts = {}
        
        for dir_path in self.storage_path.iterdir():
            if not dir_path.is_dir():
                continue
            
            for file_path in dir_path.iterdir():
                total_size_bytes += file_path.stat().st_size
                
                if file_path.suffix == '.json':
                    total_patches += 1
                    
                    try:
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                        
                        status = data.get('status', 'unknown')
                        status_counts[status] = status_counts.get(status, 0) + 1
                        
                        area = data.get('area', 'unknown')
                        area_counts[area] = area_counts.get(area, 0) + 1
                        
                    except Exception:
                        pass
        
        return {
            "total_patches": total_patches,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
            "status_distribution": status_counts,
            "area_distribution": area_counts,
            "storage_path": str(self.storage_path)
        }


# Global storage instance
_patch_storage: Optional[PatchStorage] = None


def get_patch_storage() -> PatchStorage:
    """Get the global patch storage instance."""
    global _patch_storage
    if _patch_storage is None:
        _patch_storage = PatchStorage()
    return _patch_storage


def save_commit_artifact(patch: MetaPatch, shadow_result: Optional[ShadowEvalResult] = None,
                        commit_sha: str = "", test_results: Optional[Dict[str, Any]] = None) -> str:
    """
    Convenience function to save a patch artifact.
    
    Returns:
        Path to saved artifact
    """
    storage = get_patch_storage()
    return storage.save_patch_artifact(patch, shadow_result, commit_sha, test_results)


def get_commit_by_patch_id(patch_id: str) -> Optional[CommitArtifact]:
    """
    Convenience function to get a commit artifact by patch ID.
    """
    storage = get_patch_storage()
    return storage.get_patch_artifact(patch_id)