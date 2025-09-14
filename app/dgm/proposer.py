"""
DGM Proposer - Generates system modification proposals using judge models

The proposer generates small, safe meta-patches by randomly selecting models
from the judge pool and instructing them to propose minimal system changes.
"""

import random
import logging
import time
from typing import List, Optional, Dict, Any
from app.dgm.types import MetaPatch, ProposalResponse, calculate_loc_delta, is_safe_diff
from app.config import (
    DGM_USE_JUDGE_POOL,
    DGM_JUDGE_MODEL_POOL,
    DGM_LOCAL_MODEL,
    DGM_GROQ_MODEL,
    DGM_ALLOWED_AREAS,
    DGM_MAX_LOC_DELTA,
)
from app.engines import call_engine

logger = logging.getLogger(__name__)


def make_prompt(allowed_areas: List[str], max_loc: int) -> str:
    """
    Create instruction prompt for the model to propose a system modification.

    Args:
        allowed_areas: List of allowed modification areas
        max_loc: Maximum lines of code change allowed

    Returns:
        Formatted prompt string
    """
    areas_str = ", ".join(allowed_areas)

    prompt = f"""You are a system improvement AI. Propose ONE minimal, reversible change to the PrimordiumEvolv meta-learning system.

REQUIREMENTS:
- Choose area from: {areas_str}
- Maximum {max_loc} lines of code change
- Output unified diff format + one-line rationale
- Must be safe, reversible, and minimal

ALLOWED CHANGES BY AREA:
- prompts: Small prompt tweaks, add clarity, fix typos
- bandit: Epsilon adjustment ±0.02, confidence parameter tuning
- asi_lite: Add lightweight safety check, adjust threshold
- rag: RAG threshold tweak, similarity adjustment ±0.05
- memory_policy: Memory weight adjustment ±0.05, decay parameter
- ui_metrics: Add small metric tile, improve existing dashboard element

FORMAT YOUR RESPONSE EXACTLY AS:
AREA: [chosen_area]
RATIONALE: [one-line explanation]
DIFF:
```diff
[unified diff here]
```

EXAMPLE:
AREA: bandit
RATIONALE: Increase exploration to improve operator diversity
DIFF:
```diff
--- a/app/config.py
+++ b/app/config.py
@@ -19,7 +19,7 @@
     "memory_k": 3,
     "rag_k": 3,
-    "eps": float(os.getenv("META_DEFAULT_EPS", "0.6")),
+    "eps": float(os.getenv("META_DEFAULT_EPS", "0.62")),
     "web_k": 3,
```

Now propose YOUR change:"""

    return prompt


def pick_model() -> str:
    """
    Select a model for proposal generation.

    Returns:
        Model ID to use for generation
    """
    if DGM_USE_JUDGE_POOL and DGM_JUDGE_MODEL_POOL:
        # Randomly select from judge pool
        model_id = random.choice(DGM_JUDGE_MODEL_POOL)
        logger.info(f"Selected judge model for DGM proposal: {model_id}")
        return model_id
    else:
        # Fall back to configured models
        fallback = DGM_GROQ_MODEL if "groq" in DGM_GROQ_MODEL else DGM_LOCAL_MODEL
        logger.info(f"Using fallback model for DGM proposal: {fallback}")
        return fallback


def _parse_response(response: str, model_id: str) -> Optional[Dict[str, str]]:
    """
    Parse model response to extract area, rationale, and diff.

    Args:
        response: Raw model response
        model_id: ID of model that generated response

    Returns:
        Dict with parsed components or None if parsing failed
    """
    try:
        lines = response.strip().split("\n")
        area = None
        rationale = None
        diff_lines = []
        in_diff = False

        for line in lines:
            if line.startswith("AREA:"):
                area = line.replace("AREA:", "").strip()
            elif line.startswith("RATIONALE:"):
                rationale = line.replace("RATIONALE:", "").strip()
            elif line.strip() == "```diff":
                in_diff = True
            elif line.strip() == "```" and in_diff:
                break
            elif in_diff:
                diff_lines.append(line)

        if not all([area, rationale, diff_lines]):
            logger.warning(f"Incomplete response from {model_id}: missing components")
            return None

        diff = "\n".join(diff_lines)

        # Validate area is allowed
        if area not in DGM_ALLOWED_AREAS:
            logger.warning(f"Invalid area '{area}' from {model_id}")
            return None

        return {"area": area, "rationale": rationale, "diff": diff}

    except Exception as e:
        logger.error(f"Failed to parse response from {model_id}: {e}")
        return None


def _route_model_call(model_id: str, prompt: str) -> tuple[str, str]:
    """
    Route model call to appropriate engine based on model ID.

    Args:
        model_id: Model identifier
        prompt: Prompt to send

    Returns:
        (response, actual_model_id) tuple
    """
    try:
        # Determine engine based on model ID patterns
        if any(
            pattern in model_id.lower()
            for pattern in ["groq", "llama", "qwen", "gpt", "kimi"]
        ):
            # Use Groq engine for judge models
            response, actual_id = call_engine(
                "groq",
                prompt,
                system=None,
                options={"max_tokens": 1024, "temperature": 0.7},
            )
            return response, actual_id
        else:
            # Use Ollama for local models
            response, actual_id = call_engine(
                "ollama",
                prompt,
                system=None,
                options={"num_predict": 1024, "temperature": 0.7},
            )
            return response, actual_id

    except Exception as e:
        logger.error(f"Model call failed for {model_id}: {e}")
        raise


def _gen_one(model_id: str) -> Optional[MetaPatch]:
    """
    Generate one proposal using the specified model.

    Args:
        model_id: Model to use for generation

    Returns:
        MetaPatch if successful, None if failed
    """
    try:
        # Create prompt
        prompt = make_prompt(DGM_ALLOWED_AREAS, DGM_MAX_LOC_DELTA)

        # Call model
        response, actual_model_id = _route_model_call(model_id, prompt)

        # Parse response
        parsed = _parse_response(response, model_id)
        if not parsed:
            return None

        area = parsed["area"]
        rationale = parsed["rationale"]
        diff = parsed["diff"]

        # Calculate LOC delta
        loc_delta = calculate_loc_delta(diff)

        # Check size limit
        if loc_delta > DGM_MAX_LOC_DELTA:
            logger.warning(
                f"Patch from {model_id} exceeds LOC limit: {loc_delta} > {DGM_MAX_LOC_DELTA}"
            )
            return None

        # Check safety
        is_safe, safety_reason = is_safe_diff(diff)
        if not is_safe:
            logger.warning(f"Unsafe patch from {model_id}: {safety_reason}")
            return None

        # Create MetaPatch
        patch = MetaPatch.create(
            area=area,
            origin=actual_model_id,  # Use actual model ID returned by engine
            notes=rationale,
            diff=diff,
            loc_delta=loc_delta,
        )

        logger.info(
            f"Generated patch {patch.id} from {model_id} (area: {area}, loc_delta: {loc_delta})"
        )
        return patch

    except Exception as e:
        logger.error(f"Failed to generate patch with {model_id}: {e}")
        return None


def generate(n: int, allowed_areas: Optional[List[str]] = None) -> ProposalResponse:
    """
    Generate multiple system modification proposals.

    Args:
        n: Number of proposals to attempt
        allowed_areas: Override allowed areas (uses config default if None)

    Returns:
        ProposalResponse with generated patches and metadata
    """
    start_time = time.time()
    patches = []
    rejected = []

    # Use provided areas or default from config
    areas = allowed_areas or DGM_ALLOWED_AREAS

    logger.info(f"Generating {n} DGM proposals in areas: {areas}")

    for i in range(n):
        try:
            # Pick model for this proposal
            model_id = pick_model()

            # Generate proposal
            patch = _gen_one(model_id)

            if patch:
                patches.append(patch)
                logger.info(f"Proposal {i+1}/{n}: Success - {patch.id}")
            else:
                rejected.append(
                    {
                        "index": i + 1,
                        "origin": model_id,
                        "reason": "Generation or validation failed",
                        "area": "unknown",
                    }
                )
                logger.info(f"Proposal {i+1}/{n}: Rejected from {model_id}")

        except Exception as e:
            logger.error(f"Proposal {i+1}/{n}: Exception - {e}")
            rejected.append(
                {
                    "index": i + 1,
                    "origin": "unknown",
                    "reason": f"Exception: {str(e)}",
                    "area": "unknown",
                }
            )

    execution_time = int((time.time() - start_time) * 1000)

    logger.info(
        f"Generated {len(patches)} patches, rejected {len(rejected)}, took {execution_time}ms"
    )

    return ProposalResponse(
        patches=patches,
        rejected=rejected,
        total_generated=n,
        execution_time_ms=execution_time,
    )


def generate_single(area: str, model_id: Optional[str] = None) -> Optional[MetaPatch]:
    """
    Generate a single proposal for a specific area.

    Args:
        area: Target modification area
        model_id: Optional specific model to use

    Returns:
        MetaPatch if successful, None if failed
    """
    if area not in DGM_ALLOWED_AREAS:
        logger.error(f"Area '{area}' not in allowed areas: {DGM_ALLOWED_AREAS}")
        return None

    # Override allowed areas for this generation
    original_areas = DGM_ALLOWED_AREAS.copy()
    try:
        # Temporarily modify allowed areas to only include target
        import app.config

        app.config.DGM_ALLOWED_AREAS = [area]

        # Use specified model or pick one
        target_model = model_id or pick_model()

        # Generate
        patch = _gen_one(target_model)
        return patch

    finally:
        # Restore original allowed areas
        import app.config

        app.config.DGM_ALLOWED_AREAS = original_areas


# Statistics and monitoring
_generation_stats = {
    "total_attempts": 0,
    "successful_patches": 0,
    "rejected_patches": 0,
    "model_usage": {},
    "area_distribution": {},
}


def get_generation_stats() -> Dict[str, Any]:
    """Get statistics about proposal generation."""
    return _generation_stats.copy()


def reset_generation_stats():
    """Reset generation statistics."""
    global _generation_stats
    _generation_stats = {
        "total_attempts": 0,
        "successful_patches": 0,
        "rejected_patches": 0,
        "model_usage": {},
        "area_distribution": {},
    }
