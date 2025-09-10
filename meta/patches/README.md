# DGM Patches Directory

This directory contains all patches generated, evaluated, and applied by the Darwin Gödel Machine (DGM) self-modification system. Each patch represents a proposed or applied change to the system's core files, complete with metadata, diff, and lifecycle tracking.

## Directory Structure

```
meta/patches/
├── README.md              # This documentation
├── index.json            # Global patch index and statistics
└── YYYYMMDD_HHMMSS/     # Timestamped patch batch directories
    ├── {patch_id}.json   # Patch metadata and results
    └── {patch_id}.diff   # Unified diff format
```

## Patch Lifecycle

### 1. **Proposal Phase**
- **Trigger**: LLM analyzes system for potential improvements
- **Generation**: Structured patch proposal with targeted area and diff
- **Validation**: Allowlist checking and safety constraint verification
- **Output**: MetaPatch object with unique ID and metadata

### 2. **Shadow Evaluation Phase**
- **Isolation**: Patch applied in temporary environment
- **Testing**: Multiple runs against baseline performance
- **Metrics**: Reward delta, error rates, latency impact measurement
- **Decision**: Statistical significance testing for viability

### 3. **Guard Validation Phase**  
- **Threshold Checking**: Error rate, latency regression, reward delta limits
- **Risk Assessment**: Impact analysis and rollback planning
- **Approval**: Human oversight gates (if configured)
- **Go/No-Go**: Final deployment decision based on safety criteria

### 4. **Commit Phase**
- **Pre-Commit Tests**: Full test suite execution (`pytest tests/dgm/`)
- **Git Integration**: Atomic commit with detailed metadata
- **Live Deployment**: Patch applied to production system
- **Monitoring**: Real-time guard checking begins

### 5. **Monitoring Phase**
- **Performance Tracking**: Continuous metrics collection
- **Guard Evaluation**: Real-time threshold monitoring
- **Attribution**: Impact measurement and success attribution
- **Rollback Triggers**: Automatic revert on guard violations

## Patch Metadata Schema

Each `.json` file contains comprehensive patch metadata:

```json
{
  "patch_id": "unique_identifier",
  "commit_sha": "git_commit_hash",
  "timestamp": 1757451424.277011,
  "area": "bandit|prompts|ui_metrics|config|operators",
  "origin": "llm_generation|mutation|human|test_script",
  "notes": "Human-readable description",
  "diff": "unified_diff_content",
  "loc_delta": 5,
  "reward_delta": 0.125,
  "error_rate_delta": -0.01,
  "latency_p95_delta": -15.0,
  "commit_message": "DGM commit message",
  "test_results": {
    "passed": true,
    "failures": 0,
    "duration_ms": 1250
  },
  "shadow_eval": {
    "baseline_reward": 0.75,
    "shadow_reward": 0.875,
    "execution_time_ms": 2100,
    "runs": 25,
    "statistical_significance": 0.01
  },
  "guards": {
    "error_rate": {"passed": true, "value": 0.08, "threshold": 0.15},
    "latency_p95": {"passed": true, "regression_ms": 12, "threshold": 500},
    "reward_delta": {"passed": true, "delta": 0.125, "threshold": -0.05}
  },
  "rollback_sha": null,
  "status": "committed|rolled_back|failed|rejected"
}
```

## Patch Areas

### **bandit** - Bandit Algorithm Optimization
- **Files**: `app/meta/bandit.py`, `config/bandit.yaml`
- **Purpose**: Epsilon-greedy and UCB parameter tuning
- **Examples**: Exploration rates, confidence bounds, warm start settings
- **Safety**: Conservative changes with statistical validation

### **prompts** - System Prompt Engineering  
- **Files**: `prompts/`, `app/prompts/`
- **Purpose**: System voice optimization and instruction refinement
- **Examples**: Engineer/Analyst/Optimizer persona adjustments
- **Safety**: A/B testing against baseline performance

### **ui_metrics** - User Experience Optimization
- **Files**: `static/`, `templates/`, UI configuration
- **Purpose**: Interface improvements and user experience enhancements
- **Examples**: Progress indicators, error messaging, visual feedback
- **Safety**: Non-functional changes with user preference tracking

### **config** - System Configuration Tuning
- **Files**: `config/`, `app/config.py`, environment settings
- **Purpose**: Runtime parameter optimization
- **Examples**: Timeout values, rate limits, feature flags
- **Safety**: Gradual rollout with automatic rollback

### **operators** - Meta-Evolution Operators
- **Files**: `app/meta/operators/`
- **Purpose**: New operator development and existing operator improvements
- **Examples**: Novel mutation strategies, operator parameter tuning
- **Safety**: Extensive shadow evaluation before deployment

## Index Management

The `index.json` file maintains global patch statistics:

```json
{
  "patches": [
    {
      "patch_id": "example_001",
      "timestamp": 1757451424.277011,
      "area": "prompts", 
      "commit_sha": "abc123def456",
      "reward_delta": 0.15,
      "status": "committed"
    }
  ],
  "stats": {
    "total_patches": 47,
    "committed_patches": 23,
    "rolled_back_patches": 3,
    "success_rate": 0.489,
    "avg_reward_delta": 0.087,
    "last_updated": 1757451424.2775629
  }
}
```

## File Naming Convention

- **Batch Directory**: `YYYYMMDD_HHMMSS` (creation timestamp)
- **Metadata File**: `{patch_id}.json` (unique identifier)
- **Diff File**: `{patch_id}.diff` (unified diff format)
- **Patch ID Format**: `{area}_{type}_{sequence}` (e.g., `prompts_optimize_001`)

## Safety Mechanisms

### **Allowlist Enforcement**
Only files in approved directories can be modified:
- ✅ `prompts/`, `app/prompts/` - System prompts and instructions
- ✅ `config/` - Configuration files and parameters  
- ✅ `app/meta/operators/` - Meta-evolution operators
- ✅ `static/`, `templates/` - UI files (non-executable)
- ✅ `tests/` - Test files and validation scripts
- ❌ Core system files, executables, security-critical components

### **Change Limits**
- **LOC Delta**: Maximum 50 lines of code per patch
- **Batch Size**: Maximum 3 patches per hour
- **File Count**: Maximum 5 files touched per patch
- **Content Analysis**: Block dangerous operations (eval, exec, system calls)

### **Rollback Protection**
- **Git Integration**: Every commit tagged with DGM metadata
- **Instant Revert**: `git revert <commit_sha>` for immediate rollback
- **Dependency Tracking**: Automatic rollback of dependent changes
- **State Verification**: System health checks after rollback

## Analytics & Attribution

### **Success Metrics**
- **Patch Acceptance Rate**: % of proposed patches that get committed
- **Performance Impact**: Average reward delta from applied patches  
- **Rollback Frequency**: Rate of patches requiring rollback
- **Area Effectiveness**: Success rates by modification area

### **Attribution Tracking**
- **Origin Analysis**: Performance by patch generation method
- **Temporal Patterns**: Success rates over time and learning trends
- **Correlation Analysis**: Patch characteristics vs performance outcomes
- **Human Feedback Integration**: Rating influence on future proposals

### **Quality Indicators**
- **Shadow Evaluation Accuracy**: Correlation between shadow and live performance
- **Guard Effectiveness**: False positive/negative rates for safety thresholds
- **Test Coverage**: Percentage of code paths validated by test suite
- **Performance Stability**: Variance in system performance post-deployment

## Operational Procedures

### **Manual Patch Review**
1. Navigate to specific patch directory: `meta/patches/YYYYMMDD_HHMMSS/`
2. Review patch metadata: `cat {patch_id}.json`
3. Examine code changes: `cat {patch_id}.diff`
4. Check test results and guard status in metadata
5. Verify commit hash matches: `git show {commit_sha}`

### **Emergency Rollback**
```bash
# Find patch to rollback
cat meta/patches/index.json | jq '.patches[] | select(.status=="committed")'

# Rollback specific patch
git revert {commit_sha}

# Update patch status
# Edit corresponding .json file to set "status": "rolled_back"
```

### **Cleanup Old Patches**
- Patches older than 90 days are eligible for archival
- Rolled-back patches archived after 30 days
- Failed/rejected patches can be cleaned up immediately
- Critical successful patches preserved indefinitely

## Integration Points

### **API Endpoints**
- `GET /api/dgm/patches` - List all patches with filtering
- `GET /api/dgm/patches/{patch_id}` - Get specific patch details
- `POST /api/dgm/patches/{patch_id}/rollback` - Trigger rollback
- `GET /api/dgm/analytics` - Patch performance analytics

### **Monitoring Integration**
- Patch metrics feed into system analytics dashboard
- Real-time alerts for guard violations and rollback triggers
- Performance attribution visible in evolution analytics
- Integration with human rating system for feedback loops

### **CI/CD Integration**
- Test suite runs automatically before any commit
- Guard thresholds enforce deployment safety
- Rollback triggers integrated with monitoring systems
- Full audit trail for compliance and debugging

---

*This directory represents the complete history of DGM self-modification attempts, providing transparency, accountability, and learning insights for the evolutionary AI system.*

## Research Applications

The patch history enables advanced research in:
- **AI Self-Improvement**: Analyzing successful self-modification patterns
- **Safety Mechanisms**: Validating multi-layer safety approaches
- **Emergent Behavior**: Discovering unexpected optimization strategies  
- **Human-AI Collaboration**: Studying oversight and approval patterns
- **System Evolution**: Long-term learning and adaptation trends

Each patch represents a data point in the system's self-improvement journey, contributing to our understanding of safe and effective AI evolution.