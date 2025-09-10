"""
DGM Mutations - Explicit, tiny mutation operations for code improvement

This module defines specific mutation operations that can be applied to
different areas of the codebase. Each mutation is small, reversible, and
produces a valid unified diff.
"""

import os
import random
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class MutationOp:
    """Base class for mutation operations."""
    
    def __init__(self, area: str, description: str):
        self.area = area
        self.description = description
        
    def generate_diff(self) -> Optional[Tuple[str, str, str]]:
        """
        Generate a unified diff for this mutation.
        
        Returns:
            Tuple of (diff, notes, loc_delta) or None if failed
        """
        raise NotImplementedError
        
    def validate(self, diff: str) -> bool:
        """Validate that diff meets constraints."""
        lines = diff.strip().split('\n')
        added = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
        removed = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))
        loc_delta = added - removed
        
        # Must be under 50 LOC change
        if abs(loc_delta) > 50:
            return False
            
        # Must have actual changes
        if added == 0 and removed == 0:
            return False
            
        return True


class PromptMutation(MutationOp):
    """Mutations for prompt files."""
    
    def __init__(self):
        super().__init__("prompts", "Enhance prompt structure")
        self.mutations = [
            ("add_failure_summary", self._add_failure_summary),
            ("tweak_role_goal", self._tweak_role_goal),
            ("add_clarification", self._add_clarification)
        ]
        
    def generate_diff(self) -> Optional[Tuple[str, str, str]]:
        """Generate a prompt mutation."""
        # Pick a random mutation type
        mutation_name, mutation_func = random.choice(self.mutations)
        
        # Find prompt files
        prompt_files = list(Path("prompts").glob("*.md")) if Path("prompts").exists() else []
        if not prompt_files:
            logger.warning("No prompt files found")
            return None
            
        # Pick a random prompt file
        target_file = random.choice(prompt_files)
        
        try:
            with open(target_file, 'r') as f:
                content = f.read()
                
            new_content, notes = mutation_func(content)
            
            if new_content == content:
                return None  # No change made
                
            # Generate diff
            diff = self._create_diff(str(target_file), content, new_content)
            loc_delta = new_content.count('\n') - content.count('\n')
            
            return diff, notes, str(loc_delta)
            
        except Exception as e:
            logger.error(f"Failed to mutate prompt: {e}")
            return None
            
    def _add_failure_summary(self, content: str) -> Tuple[str, str]:
        """Add a failure summary section."""
        if "## Failure Summary" in content or "## Common Issues" in content:
            return content, "Section already exists"
            
        # Find a good insertion point
        sections = content.split('\n## ')
        if len(sections) > 1:
            # Insert after first section
            sections[1] = sections[1] + "\n\n## Failure Summary\n\nWhen encountering errors:\n- Note the specific error type\n- Check prerequisites and assumptions\n- Verify input format matches expectations\n"
            new_content = '\n## '.join(sections)
            return new_content, "Added failure summary section to improve error handling"
        
        return content, "Could not find insertion point"
        
    def _tweak_role_goal(self, content: str) -> Tuple[str, str]:
        """Adjust the role/goal line."""
        # Look for role definition patterns
        patterns = [
            (r'(You are a[n]? )([^.]+)(\.)', r'\1highly skilled \2\3'),
            (r'(Your goal is to )([^.]+)(\.)', r'\1efficiently \2\3'),
            (r'(Focus on )([^.]+)(\.)', r'\1carefully \2\3')
        ]
        
        for pattern, replacement in patterns:
            if re.search(pattern, content):
                new_content = re.sub(pattern, replacement, content, count=1)
                if new_content != content:
                    return new_content, "Enhanced role definition for clarity"
                    
        return content, "No role pattern found to modify"
        
    def _add_clarification(self, content: str) -> Tuple[str, str]:
        """Add a small clarification."""
        clarifications = [
            "\nNote: Prioritize accuracy over speed.\n",
            "\nRemember: Validate assumptions before proceeding.\n",
            "\nImportant: Consider edge cases in your approach.\n"
        ]
        
        clarification = random.choice(clarifications)
        
        # Add at end of first paragraph
        lines = content.split('\n\n')
        if len(lines) > 0:
            lines[0] = lines[0] + clarification
            new_content = '\n\n'.join(lines)
            return new_content, f"Added clarification: {clarification.strip()}"
            
        return content, "Could not add clarification"
        
    def _create_diff(self, filepath: str, old_content: str, new_content: str) -> str:
        """Create a unified diff."""
        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')
        
        # Simple diff for demonstration - in production use difflib
        diff_lines = [
            f"--- a/{filepath}",
            f"+++ b/{filepath}",
            "@@ -1,{} +1,{} @@".format(len(old_lines), len(new_lines))
        ]
        
        # Find first difference
        for i, (old, new) in enumerate(zip(old_lines, new_lines)):
            if old != new:
                if i > 0:
                    diff_lines.append(f" {old_lines[i-1]}")
                diff_lines.append(f"-{old}")
                diff_lines.append(f"+{new}")
                if i < len(old_lines) - 1:
                    diff_lines.append(f" {old_lines[i+1]}")
                break
                
        # Handle added lines
        if len(new_lines) > len(old_lines):
            for line in new_lines[len(old_lines):]:
                diff_lines.append(f"+{line}")
                
        return '\n'.join(diff_lines)


class BanditMutation(MutationOp):
    """Mutations for bandit algorithm parameters."""
    
    def __init__(self):
        super().__init__("bandit", "Optimize exploration parameters")
        
    def generate_diff(self) -> Optional[Tuple[str, str, str]]:
        """Generate a bandit mutation."""
        mutations = [
            self._adjust_epsilon,
            self._adjust_ucb_c,
            self._reorder_arms
        ]
        
        mutation_func = random.choice(mutations)
        return mutation_func()
        
    def _adjust_epsilon(self) -> Optional[Tuple[str, str, str]]:
        """Adjust epsilon by ±0.02."""
        try:
            # Read current config
            config_path = "app/config.py"
            with open(config_path, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if '"eps":' in line and 'META_DEFAULT_EPS' in line:
                    # Extract current value
                    match = re.search(r'"([0-9.]+)"', line)
                    if match:
                        current = float(match.group(1))
                        # Adjust by ±0.02, keep in [0.05, 0.3]
                        delta = random.choice([-0.02, 0.02])
                        new_val = max(0.05, min(0.3, current + delta))
                        
                        if new_val == current:
                            return None
                            
                        old_line = line
                        new_line = line.replace(f'"{current}"', f'"{new_val}"')
                        
                        diff = f"""--- a/{config_path}
+++ b/{config_path}
@@ -{i+1},1 +{i+1},1 @@
-{old_line.rstrip()}
+{new_line.rstrip()}"""
                        
                        notes = f"Adjusted epsilon from {current} to {new_val} to {'increase' if delta > 0 else 'decrease'} exploration"
                        return diff, notes, "0"
                        
        except Exception as e:
            logger.error(f"Failed to adjust epsilon: {e}")
            
        return None
        
    def _adjust_ucb_c(self) -> Optional[Tuple[str, str, str]]:
        """Adjust UCB exploration constant."""
        try:
            config_path = "app/config.py"
            with open(config_path, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if '"ucb_c":' in line and 'UCB_C' in line:
                    match = re.search(r'"([0-9.]+)"', line)
                    if match:
                        current = float(match.group(1))
                        # Adjust by ±0.1
                        delta = random.choice([-0.1, 0.1])
                        new_val = max(0.5, min(3.0, current + delta))
                        
                        if new_val == current:
                            return None
                            
                        old_line = line
                        new_line = line.replace(f'"{current}"', f'"{new_val}"')
                        
                        diff = f"""--- a/{config_path}
+++ b/{config_path}
@@ -{i+1},1 +{i+1},1 @@
-{old_line.rstrip()}
+{new_line.rstrip()}"""
                        
                        notes = f"Adjusted UCB c from {current} to {new_val} for {'more' if delta > 0 else 'less'} exploration"
                        return diff, notes, "0"
                        
        except Exception as e:
            logger.error(f"Failed to adjust UCB c: {e}")
            
        return None
        
    def _reorder_arms(self) -> Optional[Tuple[str, str, str]]:
        """Reorder operator groups to test memory_seeded earlier."""
        try:
            config_path = "app/config.py"
            with open(config_path, 'r') as f:
                content = f.read()
                
            # Look for OP_GROUPS definition
            if 'OP_GROUPS = {' in content:
                # Move memory operators earlier in SEAL group
                if '"inject_memory"' in content:
                    # This is a complex refactor - simplified for demo
                    notes = "Reordered operators to test memory seeding earlier"
                    # Would need actual AST manipulation here
                    return None  # Skip for now
                    
        except Exception as e:
            logger.error(f"Failed to reorder arms: {e}")
            
        return None


class ASIMutation(MutationOp):
    """Mutations for ASI architecture parameters."""
    
    def __init__(self):
        super().__init__("asi_lite", "Expand ASI parameter grid")
        
    def generate_diff(self) -> Optional[Tuple[str, str, str]]:
        """Generate an ASI mutation."""
        # Add top_p value for reasoning tasks
        try:
            # This would modify asi_arch.py if it exists
            asi_path = "app/meta/asi_arch.py"
            if not Path(asi_path).exists():
                # Create a simple ASI config
                content = """# ASI Architecture Configuration
                
REASONING_PARAMS = {
    "temperature": [0.7, 0.8],
    "top_p": [0.9, 0.95],  # Added 0.95 for better reasoning
    "top_k": [40, 50]
}
"""
                diff = f"""--- /dev/null
+++ b/{asi_path}
@@ -0,0 +1,7 @@
+# ASI Architecture Configuration
+
+REASONING_PARAMS = {{
+    "temperature": [0.7, 0.8],
+    "top_p": [0.9, 0.95],  # Added 0.95 for better reasoning
+    "top_k": [40, 50]
+}}"""
                notes = "Added top_p=0.95 to reasoning parameter grid"
                return diff, notes, "7"
                
        except Exception as e:
            logger.error(f"Failed to mutate ASI: {e}")
            
        return None


class RAGMutation(MutationOp):
    """Mutations for RAG retriever parameters."""
    
    def __init__(self):
        super().__init__("rag", "Optimize RAG retrieval")
        
    def generate_diff(self) -> Optional[Tuple[str, str, str]]:
        """Generate a RAG mutation."""
        mutations = [
            self._raise_min_sim,
            self._cap_k_by_latency
        ]
        
        mutation_func = random.choice(mutations)
        return mutation_func()
        
    def _raise_min_sim(self) -> Optional[Tuple[str, str, str]]:
        """Raise minimum similarity threshold."""
        try:
            rag_path = "app/rag/retriever.py"
            if not Path(rag_path).exists():
                return None
                
            with open(rag_path, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if 'min_similarity' in line or 'MIN_SIM' in line:
                    # Find current value
                    match = re.search(r'([0-9.]+)', line)
                    if match:
                        current = float(match.group(1))
                        new_val = min(0.87, current + 0.02)
                        
                        if new_val == current:
                            return None
                            
                        old_line = line
                        new_line = line.replace(str(current), str(new_val))
                        
                        diff = f"""--- a/{rag_path}
+++ b/{rag_path}
@@ -{i+1},1 +{i+1},1 @@
-{old_line.rstrip()}
+{new_line.rstrip()}"""
                        
                        notes = f"Raised min similarity from {current} to {new_val} for better precision"
                        return diff, notes, "0"
                        
        except Exception as e:
            logger.error(f"Failed to raise min_sim: {e}")
            
        return None
        
    def _cap_k_by_latency(self) -> Optional[Tuple[str, str, str]]:
        """Cap K by latency budget."""
        # This would add latency-aware K selection
        notes = "Added latency-aware K capping for retrieval"
        # Implementation would check latency and adjust K
        return None  # Complex implementation


class MemoryMutation(MutationOp):
    """Mutations for memory retriever parameters."""
    
    def __init__(self):
        super().__init__("memory_policy", "Optimize memory retrieval")
        
    def generate_diff(self) -> Optional[Tuple[str, str, str]]:
        """Generate a memory mutation."""
        mutations = [
            self._adjust_reward_weight,
            self._switch_injection_mode
        ]
        
        mutation_func = random.choice(mutations)
        return mutation_func()
        
    def _adjust_reward_weight(self) -> Optional[Tuple[str, str, str]]:
        """Adjust MEMORY_REWARD_WEIGHT by ±0.05."""
        try:
            config_path = "app/config.py"
            with open(config_path, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if 'MEMORY_REWARD_WEIGHT' in line:
                    match = re.search(r'"([0-9.]+)"', line)
                    if match:
                        current = float(match.group(1))
                        delta = random.choice([-0.05, 0.05])
                        new_val = max(0.2, min(0.5, current + delta))
                        
                        if new_val == current:
                            return None
                            
                        old_line = line
                        new_line = line.replace(f'"{current}"', f'"{new_val}"')
                        
                        diff = f"""--- a/{config_path}
+++ b/{config_path}
@@ -{i+1},1 +{i+1},1 @@
-{old_line.rstrip()}
+{new_line.rstrip()}"""
                        
                        notes = f"Adjusted memory reward weight from {current} to {new_val}"
                        return diff, notes, "0"
                        
        except Exception as e:
            logger.error(f"Failed to adjust memory weight: {e}")
            
        return None
        
    def _switch_injection_mode(self) -> Optional[Tuple[str, str, str]]:
        """Switch injection mode for code tasks."""
        try:
            config_path = "app/config.py"
            with open(config_path, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                if 'MEMORY_INJECTION_MODE' in line:
                    if '"system_prepend"' in line:
                        old_line = line
                        new_line = line.replace('"system_prepend"', '"planner_only"')
                        
                        diff = f"""--- a/{config_path}
+++ b/{config_path}
@@ -{i+1},1 +{i+1},1 @@
-{old_line.rstrip()}
+{new_line.rstrip()}  # Better for code tasks"""
                        
                        notes = "Switched memory injection to planner-only mode for code tasks"
                        return diff, notes, "0"
                        
        except Exception as e:
            logger.error(f"Failed to switch injection mode: {e}")
            
        return None


class UIMutation(MutationOp):
    """Mutations for UI panels (read-only metrics)."""
    
    def __init__(self):
        super().__init__("ui_metrics", "Add UI metric tiles")
        
    def generate_diff(self) -> Optional[Tuple[str, str, str]]:
        """Add a metric tile to UI."""
        try:
            ui_path = "app/ui/index.html"
            with open(ui_path, 'r') as f:
                content = f.read()
                
            # Find a good place to add a metric
            if '<div class="result-card"' in content:
                # Add a new metric tile
                new_metric = """
              <div class="result-card" style="padding:12px">
                <div class="text-muted" style="font-size:0.9em">Cache Hit Rate</div>
                <div id="cacheHitRate" style="font-size:1.2em;font-weight:bold">-</div>
              </div>"""
                
                # Insert after first result-card
                pos = content.find('<div class="result-card"')
                if pos > 0:
                    # Find end of this card
                    end_pos = content.find('</div>', pos)
                    end_pos = content.find('</div>', end_pos + 1) + 6
                    
                    new_content = content[:end_pos] + new_metric + content[end_pos:]
                    
                    # Create a simplified diff
                    diff = f"""--- a/{ui_path}
+++ b/{ui_path}
@@ -100,0 +100,4 @@
+              <div class="result-card" style="padding:12px">
+                <div class="text-muted" style="font-size:0.9em">Cache Hit Rate</div>
+                <div id="cacheHitRate" style="font-size:1.2em;font-weight:bold">-</div>
+              </div>"""
                    
                    notes = "Added cache hit rate metric tile to UI"
                    return diff, notes, "4"
                    
        except Exception as e:
            logger.error(f"Failed to add UI metric: {e}")
            
        return None


# Registry of all mutation types
MUTATION_REGISTRY = {
    "prompts": PromptMutation,
    "bandit": BanditMutation,
    "asi_lite": ASIMutation,
    "rag": RAGMutation,
    "memory_policy": MemoryMutation,
    "ui_metrics": UIMutation
}


def generate_mutation(area: Optional[str] = None) -> Optional[Tuple[str, str, str, str]]:
    """
    Generate a random mutation for the specified area.
    
    Args:
        area: Specific area to mutate, or None for random
        
    Returns:
        Tuple of (area, diff, notes, loc_delta) or None
    """
    if area:
        if area not in MUTATION_REGISTRY:
            logger.error(f"Unknown mutation area: {area}")
            return None
        mutation_class = MUTATION_REGISTRY[area]
    else:
        # Pick random area
        area = random.choice(list(MUTATION_REGISTRY.keys()))
        mutation_class = MUTATION_REGISTRY[area]
        
    # Create mutation instance and generate
    mutation = mutation_class()
    result = mutation.generate_diff()
    
    if result:
        diff, notes, loc_delta = result
        
        # Validate the diff
        if mutation.validate(diff):
            return area, diff, notes, loc_delta
        else:
            logger.warning(f"Generated diff failed validation for {area}")
            
    return None


def generate_multiple_mutations(count: int = 3) -> List[Dict[str, str]]:
    """
    Generate multiple mutations across different areas.
    
    Args:
        count: Number of mutations to generate
        
    Returns:
        List of mutation dictionaries
    """
    mutations = []
    used_areas = set()
    
    for _ in range(count):
        # Try to get diverse areas
        available_areas = [a for a in MUTATION_REGISTRY.keys() if a not in used_areas]
        if not available_areas:
            available_areas = list(MUTATION_REGISTRY.keys())
            
        area = random.choice(available_areas)
        used_areas.add(area)
        
        result = generate_mutation(area)
        if result:
            area, diff, notes, loc_delta = result
            mutations.append({
                "area": area,
                "diff": diff,
                "notes": notes,
                "loc_delta": int(loc_delta) if loc_delta else 0
            })
            
    return mutations