"""
Adaptive Nudge Selection System using UCB Algorithm

Implements context-aware nudge selection based on task classification
and Upper Confidence Bound (UCB) algorithm for exploration/exploitation.
"""

import json
import math
import time
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    from .store import get_nudge_stats, upsert_nudge_stat
except ImportError:
    # Fallback for testing
    def get_nudge_stats(task_type=None): return {}
    def upsert_nudge_stat(nudge_id, task_type, reward): pass

logger = logging.getLogger(__name__)

@dataclass
class NudgeStats:
    """Statistics for a nudge in a specific task context."""
    nudge_id: str
    task_type: str
    total_selections: int = 0
    total_reward: float = 0.0
    average_reward: float = 0.0
    last_used: float = 0.0
    
    def update_reward(self, reward: float) -> None:
        """Update statistics with new reward."""
        self.total_selections += 1
        self.total_reward += reward
        self.average_reward = self.total_reward / self.total_selections
        self.last_used = time.time()

@dataclass
class NudgeLibraryItem:
    """A nudge item from the library."""
    id: str
    text: str
    tags: List[str]
    suitable_tasks: List[str]
    unsuitable_tasks: List[str]
    description: str

class TaskClassifier:
    """Classifies user prompts into task types for nudge selection."""
    
    def __init__(self):
        self.patterns = {
            "code": [
                r'\b(function|class|def|import|return|if|else|for|while)\b',
                r'\b(javascript|python|java|html|css|sql|api)\b',
                r'\b(write.*code|implement|program|script)\b',
                r'[{}()\[\];]'
            ],
            "debug": [
                r'\b(error|bug|fix|debug|issue|problem|not working)\b',
                r'\b(troubleshoot|diagnose|resolve)\b',
                r'\b(why.*not|what.*wrong|help.*fix)\b'
            ],
            "creative": [
                r'\b(story|poem|creative|imagine|draft|write)\b',
                r'\b(brainstorm|idea|inspire|artistic)\b',
                r'\b(elevator pitch|marketing|slogan)\b'
            ],
            "analysis": [
                r'\b(analyze|compare|evaluate|assess|examine)\b',
                r'\b(pros.*cons|advantages|disadvantages)\b',
                r'\b(what.*difference|how.*different)\b'
            ],
            "tutorial": [
                r'\b(how.*to|step.*by.*step|guide|tutorial|teach)\b',
                r'\b(explain.*how|show.*me|walk.*through)\b',
                r'\b(learn|understand|demonstrate)\b'
            ],
            "explanation": [
                r'\b(what.*is|explain|describe|tell.*me.*about)\b',
                r'\b(meaning|definition|concept)\b',
                r'\b(why.*does|how.*does)\b'
            ],
            "planning": [
                r'\b(plan|strategy|roadmap|schedule|organize)\b',
                r'\b(steps|phases|timeline|milestones)\b',
                r'\b(project|task.*list|workflow)\b'
            ],
            "brainstorming": [
                r'\b(ideas|brainstorm|suggestions|alternatives)\b',
                r'\b(creative.*solutions|think.*of|come.*up.*with)\b',
                r'\b(possibilities|options|approaches)\b'
            ],
            "conversation": [
                r'\b(chat|talk|discuss|conversation)\b',
                r'\b(opinion|thoughts|what.*do.*you.*think)\b',
                r'\b(casual|friendly|informal)\b'
            ],
            "quick_answer": [
                r'\b(quick|fast|brief|short|simple)\b',
                r'\b(yes.*no|true.*false|answer.*only)\b',
                r'^(what|when|where|who|which)\s'
            ],
            "summary": [
                r'\b(summary|summarize|sum.*up|brief)\b',
                r'\b(key.*points|main.*ideas|overview)\b',
                r'\b(tldr|in.*short|condensed)\b'
            ]
        }
    
    def classify_task(self, prompt: str) -> str:
        """
        Classify a prompt into a task type.
        
        Args:
            prompt: The user prompt to classify
            
        Returns:
            Task type string
        """
        prompt_lower = prompt.lower()
        
        # Score each task type based on pattern matches
        scores = {}
        for task_type, patterns in self.patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, prompt_lower))
                score += matches
            scores[task_type] = score
        
        # Return task type with highest score, or default
        if scores and max(scores.values()) > 0:
            return max(scores, key=scores.get)
        
        return "explanation"  # Default task type

class AdaptiveNudgeSelector:
    """UCB-based adaptive nudge selection system."""
    
    def __init__(self, library_path: str = None):
        self.library_path = library_path or "app/meta/nudge_library.json"
        self.nudge_library = self._load_library()
        self.task_classifier = TaskClassifier()
        self.c_value = 2.0  # UCB exploration parameter
        self.use_database = True  # Use database for persistence
        
    def _load_library(self) -> Dict[str, Any]:
        """Load nudge library from JSON file."""
        try:
            library_file = Path(self.library_path)
            if not library_file.exists():
                logger.error(f"Nudge library not found at {self.library_path}")
                return self._get_fallback_library()
            
            with open(library_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load nudge library: {e}")
            return self._get_fallback_library()
    
    def _get_fallback_library(self) -> Dict[str, Any]:
        """Fallback library if file loading fails."""
        return {
            "nudges": [
                {
                    "id": "bullet_points",
                    "text": "Respond in bullet points.",
                    "tags": ["format", "structured"],
                    "suitable_tasks": ["analysis", "debug"],
                    "unsuitable_tasks": ["creative", "storytelling"],
                    "description": "Forces responses into bullet point format"
                },
                {
                    "id": "creative_flow",
                    "text": "Use natural, flowing language with creative expression.",
                    "tags": ["creative", "natural"],
                    "suitable_tasks": ["creative", "storytelling"],
                    "unsuitable_tasks": ["code", "debug"],
                    "description": "Encourages creative expression"
                }
            ],
            "task_mappings": {
                "creative": {
                    "preferred": ["creative_flow"],
                    "unsuitable": ["bullet_points"]
                }
            },
            "default_task": "explanation"
        }
    
    def get_suitable_nudges(self, task_type: str) -> List[NudgeLibraryItem]:
        """Get nudges suitable for a task type."""
        suitable_nudges = []
        
        # Get task mapping preferences
        task_mapping = self.nudge_library.get("task_mappings", {}).get(task_type, {})
        preferred = set(task_mapping.get("preferred", []))
        suitable = set(task_mapping.get("suitable", []))
        unsuitable = set(task_mapping.get("unsuitable", []))
        
        for nudge_data in self.nudge_library.get("nudges", []):
            nudge_id = nudge_data["id"]
            
            # Skip if explicitly unsuitable
            if nudge_id in unsuitable:
                continue
            
            # Include if preferred or suitable
            if nudge_id in preferred or nudge_id in suitable:
                suitable_nudges.append(NudgeLibraryItem(**nudge_data))
                continue
            
            # Check nudge's own task lists
            nudge_suitable = nudge_data.get("suitable_tasks", [])
            nudge_unsuitable = nudge_data.get("unsuitable_tasks", [])
            
            if task_type in nudge_unsuitable:
                continue
            
            if task_type in nudge_suitable:
                suitable_nudges.append(NudgeLibraryItem(**nudge_data))
        
        return suitable_nudges
    
    def calculate_ucb_score(self, nudge_id: str, task_type: str, total_selections: int) -> float:
        """Calculate UCB score for a nudge in a task context."""
        if self.use_database:
            # Load stats from database
            db_stats = get_nudge_stats(task_type)
            stats_key = f"{nudge_id}_{task_type}"
            
            if stats_key not in db_stats:
                return float('inf')  # Unselected nudges get infinite score
            
            stats = db_stats[stats_key]
            nudge_selections = stats["total_selections"]
            average_reward = stats["average_reward"]
        else:
            # Use in-memory stats (fallback)
            stats_key = f"{nudge_id}_{task_type}"
            if stats_key not in self.stats:
                return float('inf')
            stats = self.stats[stats_key]
            nudge_selections = stats.total_selections
            average_reward = stats.average_reward
        
        if nudge_selections == 0:
            return float('inf')
        
        # UCB formula: average_reward + c * sqrt(log(total_selections) / nudge_selections)
        confidence_interval = self.c_value * math.sqrt(
            math.log(total_selections) / nudge_selections
        )
        
        return average_reward + confidence_interval
    
    def select_nudge(self, prompt: str, task_type: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        Select the best nudge for a prompt using UCB algorithm.
        
        Args:
            prompt: User prompt
            task_type: Optional explicit task type (auto-classified if None)
            
        Returns:
            Tuple of (nudge_text, selection_info)
        """
        # Classify task if not provided
        if task_type is None:
            task_type = self.task_classifier.classify_task(prompt)
        
        # Get suitable nudges for this task type
        suitable_nudges = self.get_suitable_nudges(task_type)
        
        if not suitable_nudges:
            # Fallback to default nudge
            logger.warning(f"No suitable nudges found for task type: {task_type}")
            return "Use clear, helpful language.", {
                "nudge_id": "fallback",
                "task_type": task_type,
                "selection_method": "fallback",
                "ucb_score": 0.0
            }
        
        # Calculate total selections for UCB
        if self.use_database:
            db_stats = get_nudge_stats(task_type)
            total_selections = sum(
                db_stats.get(f"{nudge.id}_{task_type}", {}).get("total_selections", 0)
                for nudge in suitable_nudges
            )
        else:
            total_selections = sum(
                self.stats.get(f"{nudge.id}_{task_type}", NudgeStats("", "")).total_selections
                for nudge in suitable_nudges
            )
        
        # Select nudge with highest UCB score
        best_nudge = None
        best_score = float('-inf')
        
        for nudge in suitable_nudges:
            score = self.calculate_ucb_score(nudge.id, task_type, total_selections)
            if score > best_score:
                best_score = score
                best_nudge = nudge
        
        if best_nudge is None:
            # This shouldn't happen, but handle gracefully
            best_nudge = suitable_nudges[0]
            best_score = 0.0
        
        # Update last used time
        stats_key = f"{best_nudge.id}_{task_type}"
        if stats_key not in self.stats:
            self.stats[stats_key] = NudgeStats(best_nudge.id, task_type)
        
        selection_info = {
            "nudge_id": best_nudge.id,
            "task_type": task_type,
            "selection_method": "ucb",
            "ucb_score": best_score,
            "total_suitable_nudges": len(suitable_nudges),
            "prompt_length": len(prompt)
        }
        
        logger.info(f"Selected nudge '{best_nudge.id}' for task '{task_type}' (UCB score: {best_score:.3f})")
        
        return best_nudge.text, selection_info
    
    def update_nudge_performance(self, nudge_id: str, task_type: str, reward: float) -> None:
        """Update nudge performance statistics."""
        if self.use_database:
            # Update stats in database
            upsert_nudge_stat(nudge_id, task_type, reward)
            logger.debug(f"Updated nudge stats in database: {nudge_id} in {task_type}, reward: {reward:.3f}")
        else:
            # Update in-memory stats (fallback)
            stats_key = f"{nudge_id}_{task_type}"
            if stats_key not in self.stats:
                self.stats[stats_key] = NudgeStats(nudge_id, task_type)
            self.stats[stats_key].update_reward(reward)
            logger.debug(f"Updated nudge stats: {nudge_id} in {task_type}, "
                        f"new avg reward: {self.stats[stats_key].average_reward:.3f}")
    
    def get_nudge_statistics(self) -> Dict[str, Any]:
        """Get current nudge performance statistics."""
        stats_by_task = {}
        
        for stats_key, stats in self.stats.items():
            task_type = stats.task_type
            if task_type not in stats_by_task:
                stats_by_task[task_type] = []
            
            stats_by_task[task_type].append(asdict(stats))
        
        return {
            "stats_by_task": stats_by_task,
            "total_nudges_tracked": len(self.stats),
            "available_nudges": len(self.nudge_library.get("nudges", [])),
            "supported_task_types": list(self.nudge_library.get("task_mappings", {}).keys())
        }
    
    def reset_statistics(self) -> None:
        """Reset all nudge statistics (for testing)."""
        self.stats.clear()

# Global instance for the application
_adaptive_nudge_selector: Optional[AdaptiveNudgeSelector] = None

def get_adaptive_nudge_selector() -> AdaptiveNudgeSelector:
    """Get or create the global adaptive nudge selector."""
    global _adaptive_nudge_selector
    if _adaptive_nudge_selector is None:
        _adaptive_nudge_selector = AdaptiveNudgeSelector()
    return _adaptive_nudge_selector

def classify_and_select_nudge(prompt: str, task_type: str = None) -> Tuple[str, Dict[str, Any]]:
    """
    Convenience function to classify task and select optimal nudge.
    
    Args:
        prompt: User prompt to classify and select nudge for
        task_type: Optional explicit task type
        
    Returns:
        Tuple of (nudge_text, selection_info)
    """
    selector = get_adaptive_nudge_selector()
    return selector.select_nudge(prompt, task_type)

def update_nudge_reward(nudge_id: str, task_type: str, reward: float) -> None:
    """
    Update nudge performance with reward feedback.
    
    Args:
        nudge_id: ID of the nudge that was used
        task_type: Task type it was used for
        reward: Reward score (typically 0.0-1.0)
    """
    selector = get_adaptive_nudge_selector()
    selector.update_nudge_performance(nudge_id, task_type, reward)