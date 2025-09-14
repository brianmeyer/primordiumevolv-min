"""
UI Strings and Copy - Centralized user-facing text for the DGM system

This module contains all user-facing strings to support localization,
A/B testing of copy, and consistent messaging across the UI.

Migration Note: Updated from "diff" to "edits" terminology to reflect
the move from unified diff patches to structured edits packages.
"""

# Evolution Process Messages
EVOLUTION_STARTING = "🚀 Starting evolution process..."
EVOLUTION_COMPLETE = "✅ Evolution cycle complete"
EVOLUTION_FAILED = "❌ Evolution failed"

# Proposal Generation
PROPOSAL_GENERATING = "🧠 Generating system improvements..."
PROPOSAL_GENERATED = "💡 Generated {count} improvement proposals"
PROPOSAL_NONE = "No viable proposals generated"

# Edit Processing (Updated from "diff" terminology)
EDIT_APPLYING = "⚙️ Applying code edits..."
EDIT_APPLIED = "✅ Applied {count} edits to {files} files"
EDIT_FAILED = "❌ Failed to apply edits: {error}"
EDIT_VALIDATED = "🔍 Edits validated successfully"
EDIT_INVALID = "⚠️ Edits failed validation: {reason}"

# Legacy Diff Support (for backward compatibility)
DIFF_FALLBACK = "🔄 Using legacy diff format"
DIFF_APPLYING = "⚙️ Applying unified diff patch..."
DIFF_APPLIED = "✅ Applied diff patch successfully"

# Shadow Evaluation
SHADOW_EVAL_STARTING = "🕵️ Running shadow evaluation..."
SHADOW_EVAL_COMPLETE = "📊 Shadow evaluation complete (score: {score})"
SHADOW_EVAL_FAILED = "⚠️ Shadow evaluation failed"

# Quality Scoring
QUALITY_JUDGING = "⚖️ Evaluating code quality..."
QUALITY_SCORE = "📈 Quality score: {score}/10"
QUALITY_EXCELLENT = "🌟 Excellent quality improvement!"
QUALITY_GOOD = "👍 Good quality improvement"
QUALITY_POOR = "👎 Poor quality - needs improvement"

# Commit and Git Operations
COMMIT_CREATING = "📝 Creating commit..."
COMMIT_CREATED = "✅ Commit created: {hash}"
COMMIT_FAILED = "❌ Commit failed: {error}"

GIT_CHECKING = "🔍 Checking git status..."
GIT_CLEAN = "✅ Repository is clean"
GIT_DIRTY = "⚠️ Repository has uncommitted changes"

# Error Messages
ERROR_GENERIC = "❌ An error occurred: {error}"
ERROR_MODEL_UNAVAILABLE = "🚫 Model {model} is not available"
ERROR_TIMEOUT = "⏰ Operation timed out"
ERROR_NETWORK = "🌐 Network error: {error}"
ERROR_PERMISSION = "🔐 Permission denied: {error}"

# Safety and Security
SAFETY_CHECK_PASS = "🛡️ Safety checks passed"
SAFETY_CHECK_FAIL = "🚨 Safety check failed: {reason}"
SECURITY_ALERT = "🔒 Security alert: {message}"

# Progress and Status
STATUS_IDLE = "⏸️ System idle"
STATUS_BUSY = "⚙️ System processing..."
STATUS_READY = "✅ System ready"

PROGRESS_STARTING = "🚀 Starting..."
PROGRESS_IN_PROGRESS = "⚙️ In progress... ({percent}%)"
PROGRESS_COMPLETE = "✅ Complete"

# Analytics and Metrics
ANALYTICS_RECORDING = "📊 Recording analytics..."
ANALYTICS_RECORDED = "✅ Analytics recorded"
METRICS_UPDATED = "📈 Metrics updated"

# Areas and Categories (for user display)
AREA_DISPLAY_NAMES = {
    "operators": "🔧 Operators",
    "prompts": "💬 Prompts",
    "bandit": "🎰 Bandit Algorithm",
    "rag": "📚 RAG System",
    "memory_policy": "🧠 Memory Policy",
    "temperature": "🌡️ Temperature",
    "sampling": "🎲 Sampling",
    "web_search": "🔍 Web Search",
    "fewshot": "📝 Few-Shot Learning",
    "ui_metrics": "📊 UI Metrics",
}

# Model Information
MODEL_LOCAL = "🏠 Local Model"
MODEL_CLOUD = "☁️ Cloud Model"
MODEL_UNKNOWN = "❓ Unknown Model"


# Time and Duration Formatting
def format_duration_ms(ms: int) -> str:
    """Format milliseconds as human-readable duration"""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}min"


def format_time_ago(timestamp: str) -> str:
    """Format timestamp as time ago (placeholder)"""
    return "just now"


# Success Messages with Edits Terminology
SUCCESS_EDITS_APPLIED = "🎉 Successfully applied {count} code edits!"
SUCCESS_EVOLUTION_COMPLETE = "🎊 Evolution cycle completed successfully!"
SUCCESS_QUALITY_IMPROVED = "📈 Code quality improved by {delta} points!"

# Help and Information
HELP_EDITS_PACKAGE = """
📦 Edits Package Format:
Structured JSON containing exact string matches and replacements,
providing more reliable code modifications than traditional diffs.
"""

HELP_LEGACY_DIFFS = """
🔄 Legacy Diff Support:
The system supports traditional unified diffs for backward compatibility,
but prefers structured edits packages for better reliability.
"""

# Feature Flags and Toggles
FF_EDITS_ENABLED = "✨ Enhanced edits system enabled"
FF_LEGACY_DIFFS = "🔄 Legacy diff support enabled"
FF_SAFETY_MODE = "🛡️ Safety mode enabled"

# Debugging and Development
DEBUG_PARSING_RESPONSE = "🔍 Parsing model response..."
DEBUG_VALIDATING_EDITS = "✅ Validating edits package..."
DEBUG_APPLYING_FALLBACK = "🔄 Applying fallback method..."

# Warnings
WARNING_EDITS_TRUNCATED = "⚠️ Edits response was truncated"
WARNING_LEGACY_FORMAT = "⚠️ Using legacy diff format"
WARNING_RATE_LIMITED = "⚠️ Rate limited - slowing down requests"

# Configuration
CONFIG_UPDATED = "⚙️ Configuration updated"
CONFIG_RESET = "🔄 Configuration reset to defaults"
CONFIG_INVALID = "❌ Invalid configuration: {error}"

# Batch Operations
BATCH_STARTING = "📦 Starting batch operation ({count} items)..."
BATCH_PROGRESS = "📦 Batch progress: {current}/{total}"
BATCH_COMPLETE = "✅ Batch operation complete"

# Export Formats (for different output types)
EXPORT_JSON = "📄 JSON format"
EXPORT_YAML = "📄 YAML format"
EXPORT_CSV = "📊 CSV format"
