# Evolution Reset Plan - Repository Consistency Sweep

**Branch**: `chore/repo-consistency-and-evolution-reset`  
**Created**: 2025-09-08  
**Status**: Pre-execution planning phase

## Executive Summary

This document outlines a comprehensive repository consistency sweep to address accumulated technical debt, dead code, module duplication, and configuration inconsistencies that have impacted the Groq multi-judge evolution system. The primary goals are to establish a single source of truth (SSOT) for judge model configurations, eliminate code duplication, and reset evolution/judge history safely.

## Current State Analysis

### Repository Structure
```
primordiumevolv-min/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── engines.py                 # Groq/Ollama engine wrapper
│   ├── quality_judge.py           # Groq multi-judge implementation  
│   ├── groq_client.py            # Groq API client
│   ├── ollama_client.py          # Ollama API client
│   ├── meta/
│   │   ├── runner.py             # Evolution runner
│   │   ├── rewards.py            # Scoring/rewards
│   │   ├── operators.py          # Evolution operators
│   │   ├── bandit.py             # Multi-armed bandit
│   │   └── store.py              # Evolution state storage
│   ├── memory/
│   │   ├── store.py              # Memory storage
│   │   ├── embed.py              # Embeddings
│   │   └── retriever.py          # RAG retrieval
│   ├── tools/
│   │   ├── rag.py                # RAG tools
│   │   └── web_search.py         # Web search tools
│   └── ui/
│       └── app.js                # Frontend (minimal Node.js)
├── requirements.txt               # Python dependencies
├── package.json                  # Node.js dependencies (MCP SDK only)
├── server.sh                     # Server startup script
└── server 2.sh                   # Duplicate server script
```

### Identified Issues

#### Configuration Inconsistencies
- **Judge Models**: Hardcoded in multiple locations without SSOT
- **Token Limits**: Mixed 1024/2048 configurations across files
- **Timeout Values**: Inconsistent 60s/180s settings
- **Environment Variables**: Scattered without central configuration

#### Code Duplication
- **Duplicate Files**: `server 2.sh`, `cache_manager 2.py`, `job_manager 2.py`
- **Redundant Modules**: Multiple memory implementations
- **Dead Code**: Unused imports, commented blocks
- **Repeated Patterns**: Similar functions across modules

#### Evolution System Issues
- **Judge Configuration**: Only "groq/compound" showing instead of multiple judges
- **State Management**: Inconsistent evolution history tracking
- **UI Integration**: Static displays not updating with actual evolution results
- **Error Handling**: Incomplete error recovery in judge flows

## Cleanup Plan - 9 Steps

### Step 0: Pre-execution Mapping ✅ COMPLETED
- [x] Map repository structure
- [x] Identify Python/JS packages and entry points
- [x] Detect FastAPI routers and React components
- [x] Create this comprehensive plan document

### Step 1: Process Cleanup
**Goal**: Eliminate resource conflicts from multiple server instances
- Kill all background uvicorn processes
- Clean up stale PID files and port conflicts
- Reset application state cleanly

### Step 2: Dead Code Removal
**Goal**: Remove unused and duplicate code
- Delete duplicate files: `server 2.sh`, `cache_manager 2.py`, `job_manager 2.py`
- Remove unused imports across all Python modules
- Clean up commented dead code blocks
- Consolidate redundant functions

### Step 3: Module Deduplication
**Goal**: Merge duplicate functionality
- Consolidate memory implementations (`app/memory.py` vs `app/memory/`)
- Merge overlapping client implementations
- Standardize error handling patterns
- Remove redundant utility functions

### Step 4: SSOT Configuration Architecture
**Goal**: Create centralized configuration system with complete judge model pool
- Create `config/models.yaml` with canonical 10 judge models from README:
  ```yaml
  groq_judges:
    primary_pool:
      - model: "llama-3.3-70b-versatile"
        description: "Advanced reasoning capabilities"
        role: "primary"
        weight: 0.20
      - model: "openai/gpt-oss-120b"
        description: "Large-scale language understanding"
        role: "primary" 
        weight: 0.15
      - model: "openai/gpt-oss-20b"
        description: "Efficient high-quality evaluation"
        role: "primary"
        weight: 0.15
      - model: "llama-3.1-8b-instant"
        description: "Fast, reliable scoring"
        role: "primary"
        weight: 0.15
      - model: "groq/compound"
        description: "Multi-faceted analysis"
        role: "primary"
        weight: 0.10
      - model: "groq/compound-mini"
        description: "Lightweight evaluation"
        role: "secondary"
        weight: 0.08
      - model: "meta-llama/llama-4-maverick-17b-128e-instruct"
        description: "Latest instruction-following"
        role: "secondary"
        weight: 0.07
      - model: "meta-llama/llama-4-scout-17b-16e-instruct"
        description: "Exploration-focused evaluation"
        role: "secondary"
        weight: 0.05
      - model: "qwen/qwen3-32b"
        description: "Advanced multilingual capabilities"
        role: "tiebreaker"
        weight: 0.03
      - model: "moonshotai/kimi-k2-instruct"
        description: "Specialized instruction understanding"
        role: "tiebreaker"
        weight: 0.02
    selection_strategy:
      judge_1_pool: ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant", "groq/compound"]
      judge_2_pool: ["openai/gpt-oss-20b", "groq/compound-mini", "meta-llama/llama-4-maverick-17b-128e-instruct"]
      tiebreaker_pool: ["meta-llama/llama-4-scout-17b-16e-instruct", "qwen/qwen3-32b", "moonshotai/kimi-k2-instruct"]
      rotation_algorithm: "weighted_round_robin"
  ```
- Create `config/system.yaml` for system-wide settings
- Generate typed interfaces for Python (`config_types.py`) and TypeScript

### Step 5: Code Generation from SSOT
**Goal**: Auto-generate configuration code
- Python dataclasses from YAML schemas
- TypeScript interfaces for frontend
- FastAPI route validation schemas
- Environment variable templates

### Step 6: Evolution History Reset  
**Goal**: Safely reset accumulated evolution state across all data stores
- Create `scripts/reset_evolution.py` with comprehensive data handling:
  - **Full Data Backup**: `backups/{timestamp}/`
    - Judge history tables and metadata
    - Bandit arm statistics and payoffs  
    - Human ratings and feedback data
    - Recipe evolution chains
    - Golden KPI benchmarks and results
    - Trajectory logs and eval reports
    - Memory store and embeddings
  - **Selective Reset Operations**:
    - Clear judge history and model rotation state
    - Reset bandit arm statistics (preserve algorithm config)
    - Truncate human_ratings table while preserving schema
    - Clear recipes evolution history (keep top-performing baseline recipes)
    - Reset golden_kpis results (preserve test definitions)
    - Archive trajectory logs to cold storage
    - Clean eval_report accumulated results
    - Preserve memory store episodic experiences (user configurable)
  - **Safety Mechanisms**:
    - Atomic transactions with rollback capability
    - Integrity checks before and after reset
    - Configuration preservation (system settings, feature flags, thresholds)
    - Schema validation and version compatibility checks
- Recovery script for full system restoration from backup

### Step 7: Integration Testing Framework  
**Goal**: Ensure system consistency
- Create `tests/integration/test_full_flow.py`
- Test judge selection rotation (should see 2-3 judges per iteration)
- Test evolution progression with proper scoring
- Validate UI updates reflect actual best strategies

### Step 8: CI Consistency Gates  
**Goal**: Prevent future inconsistencies with robust validation
- **Pre-commit Hooks** (`.pre-commit-config.yaml`):
  - YAML schema validation for all config files
  - Import sorting (isort) and dead code detection (vulture)
  - Configuration drift detection against SSOT
  - Judge model availability validation against Groq API
  - Python type checking (mypy) for generated config types
- **GitHub Actions Workflow** (`.github/workflows/consistency.yml`):
  - **Schema Validation Pipeline**:
    - Validate `config/models.yaml` against JSON schema
    - Check judge model pool completeness (all 10 models present)
    - Verify selection strategy pools have valid model references
    - Validate system configuration against expected structure
  - **Analytics Endpoint Validation**:
    - **Hard Fail on Structure Issues**: `/api/meta/analytics` must return valid JSON schema
    - **Soft-fail Detection**: Distinguish between soft-fail (null values with valid structure) vs hard-fail (broken endpoint)
    - **Schema Compliance**: Validate analytics response against expected schema:
      ```json
      {
        "total_runs": "number|null",
        "avg_reward": "number|null", 
        "judge_stats": "object|null",
        "error_indicators": {
          "soft_fail": "boolean",
          "data_available": "boolean",
          "schema_valid": "boolean"
        }
      }
      ```
    - **Break Build on Hard Fail**: CI fails if analytics returns 500, invalid JSON, or missing error_indicators
    - **Continue on Soft Fail**: CI passes if analytics returns valid JSON with null data but proper structure
  - **Configuration Consistency Checks**:
    - Cross-reference judge models between README, code, and config files
    - Verify environment variable documentation matches actual usage
    - Check feature flag consistency across codebase
  - **Automated Remediation**:
    - Auto-generate pull requests for detected configuration drift
    - Update documentation when config schemas change
    - Regenerate typed interfaces when YAML files are modified

### Step 9: Documentation and Validation
**Goal**: Document new architecture and validate
- Update README with new configuration system
- Create developer guide for SSOT patterns
- Run comprehensive system test
- Generate `POST_SWEEP_SUMMARY.md`

## Expected Outcomes

### Fixed Judge System
- Multiple Groq judges (llama-3.1-8b, llama-3.1-70b, mixtral) rotating properly
- Two-judge evaluation with automatic tiebreaker for disagreements
- Judge metadata flowing correctly to UI displays
- Non-empty judge arrays in iteration logs

### Improved Performance
- Eliminated resource conflicts from duplicate servers
- Reduced memory footprint from dead code removal
- Faster startup times with cleaner module imports
- More reliable evolution runs with proper error handling

### Better Maintainability
- Single source of truth for all model configurations
- Automated code generation preventing configuration drift
- Clear separation of concerns between modules
- Comprehensive test coverage for critical paths

### Enhanced Developer Experience
- Clear repository structure with no duplicate files
- Consistent patterns across all modules
- Self-documenting configuration system
- Reliable CI/CD pipeline preventing regressions

## Risk Assessment

### Low Risk
- Dead code removal (can be reverted)
- Configuration centralization (improves maintainability)
- Documentation updates

### Medium Risk  
- Module deduplication (requires careful testing)
- Evolution history reset (has backup mechanism)
- Integration testing changes

### High Risk
- None identified with proper backup procedures

## Rollback Plan

1. **Git Branch Protection**: All changes isolated to feature branch
2. **Evolution Data Backup**: Automatic backup before any history reset
3. **Configuration Backup**: Preserve existing configuration files
4. **Atomic Commits**: Each step as separate commit for selective rollback
5. **Integration Tests**: Comprehensive testing before merge

## Success Criteria

- [ ] Multiple Groq judges visible in UI (not just "groq/compound")
- [ ] Judge arrays populated with 2-3 judges per evolution iteration  
- [ ] UI "best strategy" updates correctly with actual scoring
- [ ] No duplicate files or dead code in repository
- [ ] All configurations managed through SSOT YAML files
- [ ] CI pipeline enforces consistency requirements
- [ ] Evolution system runs reliably without timeout errors
- [ ] Clean repository structure with logical module organization

## Commit Strategy

The cleanup will be executed as 7-11 atomic commits:

1. **Process cleanup and duplicate file removal**
2. **Dead code elimination across modules** 
3. **Module deduplication and consolidation**
4. **SSOT configuration system implementation**
5. **Auto-generated configuration code**
6. **Evolution history reset script**
7. **Integration testing framework**
8. **CI consistency gates**
9. **Documentation updates**
10. **Final validation and testing** *(if needed)*
11. **Post-sweep summary generation** *(if needed)*

Each commit will be focused, reversible, and include appropriate tests to ensure system stability throughout the cleanup process.

---
*This plan will be executed as a non-interactive automated process with progress tracking via atomic commits.*