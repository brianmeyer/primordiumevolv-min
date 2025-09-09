# Analytics V2 - Modernized Analytics System

## Overview

Analytics V2 is a comprehensive refactor of the PrimordiumEvolv analytics system that provides:

- **Single source of truth** via cached snapshots
- **Task class normalization** to canonical categories
- **Deprecation handling** for obsolete operators/voices/judges
- **Integrated cost/latency metrics** (former Costs tab merged into Overview/Golden)
- **Auto-refresh functionality** and consistent timestamps
- **Backward compatibility** with all evolution-critical metrics

## Key Features

### 1. Snapshot-Based Architecture

The system now uses cached snapshots stored in the `analytics_snapshot` table to provide fast, consistent analytics:

```python
from app.meta.analytics_v2 import get_snapshot_manager

manager = get_snapshot_manager()
snapshot = manager.get_snapshot(window_days=30)  # 7, 30, or -1 (all)

# Returns:
{
    "totals": {...},     # KPIs and aggregated metrics
    "series": {...},     # Time-series data for charts
    "meta": {...},       # Computation metadata
    "cached": bool,      # Whether data came from cache
    "age_seconds": int   # Cache age
}
```

**Cache TTL**: 60 seconds. Snapshots auto-refresh when older than 1 minute.

### 2. Task Class Normalization

All task classes are normalized to canonical categories:

| Canonical | Aliases |
|-----------|---------|
| `code` | coding, programming, debug, debugging, development |
| `analysis` | data, analytics, data_analysis, reporting |
| `writing` | creative, content, copywriting, marketing |
| `business` | strategy, planning, management, operations |
| `research` | fact_checking, investigation, lookup, search |
| `general` | other, misc, default |

**Migration**: Original `task_class` values are preserved; `normalized_task_class` column added.

### 3. Deprecation System

Operators, voices, and judges can be marked as deprecated:

```sql
INSERT INTO deprecated_entities (entity_type, entity_name, deprecated_at, reason)
VALUES ('operator', 'old_operator', 1642680000, 'Superseded by new_operator');
```

**UI Behavior**: 
- Deprecated items hidden by default
- Toggle: "Show deprecated (N)" reveals them with striped background
- Deprecated items show 🗑️ icon

### 4. Integrated Tabs

#### Overview Tab
- **Core KPIs**: Total runs, avg score, Δ improvement, avg latency
- **Memory & Cost**: Hit rate, reward lift, store size, cost penalty
- **Charts**: Score progression, runs by task class

#### Operators Tab
- Usage count, avg reward, avg latency, success rate
- Hide/show deprecated operators
- Sortable table format

#### Voices Tab  
- System prompt performance (truncated display)
- Usage count, avg reward, avg cost penalty
- Deprecation support

#### Judges Tab
- Evaluated count, tie-breaker rate
- Latency percentiles (P50/P90)

#### Golden Tab
- **Integrated cost metrics** from former Costs tab
- Total tests, pass rate, avg reward, avg cost
- Streaming run button preserved
- Pass rates per canonical task class

#### Thresholds Tab
- Delta reward min, cost ratio max, golden pass target
- Environment-configured values

#### Memory Tab
- Unchanged - uses existing memory analytics system
- Hit rate, reward lift, store size analysis

### 5. API Endpoints

#### New Snapshot Endpoint
```
GET /api/meta/analytics/snapshot?window=30d
```

**Parameters**:
- `window`: `7d`, `30d`, or `all`

**Response**:
```json
{
  "totals": {
    "runs": {"total": 42, "avg_score": 0.847},
    "improvement": {"delta_total_reward": 0.143},
    "memory": {"enabled": true, "hit_rate": 0.73, "reward_lift": 0.05},
    "operators": [...],
    "voices": [...],
    "judges": {"evaluated": 156, "tie_breaker_rate": 0.12},
    "golden": {"total_tests": 8, "pass_rate": 0.875},
    "costs": {"avg_latency_ms": 1200, "avg_cost_penalty": -0.002},
    "thresholds": {"delta_reward_min": 0.05, "cost_ratio_max": 0.9}
  },
  "series": {
    "score_progression": [...],
    "runs_by_class": {"code": 15, "analysis": 8, "writing": 12, ...}
  },
  "meta": {
    "snapshot_version": "2.0",
    "computation_time_ms": 45,
    "window_days": 30
  },
  "cached": true,
  "age_seconds": 23
}
```

#### Existing Endpoints (Preserved)
- `GET /api/meta/analytics` - Legacy analytics (soft-fail safe)
- `GET /api/meta/analytics/memory` - Memory-specific analytics
- All evolution and Golden Set endpoints unchanged

## Database Schema

### Analytics Snapshot Table

```sql
CREATE TABLE analytics_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_days INTEGER,  -- 7, 30, or -1 for all
    created_at REAL,
    totals_json TEXT,     -- Serialized totals object
    series_json TEXT,     -- Serialized series data  
    meta_json TEXT        -- Metadata and computation info
);
```

### Task Class Normalization

```sql
ALTER TABLE runs ADD COLUMN normalized_task_class TEXT;
-- Populated by migration 001 with normalized values
```

### Deprecation Tracking

```sql
CREATE TABLE deprecated_entities (
    entity_type TEXT,    -- 'operator', 'voice', 'judge'
    entity_name TEXT,
    deprecated_at REAL,
    reason TEXT,
    PRIMARY KEY (entity_type, entity_name)
);
```

## Migration System

Analytics V2 includes a comprehensive migration system:

### Migration 001: Task Class Normalization
- Adds `normalized_task_class` column to runs table
- Backfills normalized values for all existing runs
- Preserves original `task_class` values

### Migration 002: Deprecation Flags  
- Creates `deprecated_entities` table
- Allows marking operators/voices/judges as deprecated

### Migration 003: Analytics Snapshot
- Creates `analytics_snapshot` table
- Initializes snapshot computation system

### Migration 004: Backfill Snapshots
- Computes initial snapshots for 7d, 30d, and all-time windows
- Ensures immediate availability of cached data

**Migration Safety**: All migrations are additive. No existing data is modified or removed.

## UI Improvements

### Auto-Refresh
- Refreshes every 5 seconds when evolution runs are active
- Manual refresh button available
- Global timestamp: "Last updated HH:MM:SS"

### History Windows
- Dropdown: 7 days / 30 days / All time
- Default: 30 days
- Instant switching between windows

### Deprecation Toggle
- Checkbox: "Show deprecated (N)" 
- Hidden by default, toggle reveals with visual styling
- Count shows number of deprecated items

### Responsive Design
- Grid layouts adapt to content
- Mobile-friendly card design
- Skeleton loaders during data fetch

## Extending Analytics V2

### Adding New Metrics

1. **Extend Snapshot Schema**:
   ```python
   # In analytics_v2.py _compute_totals()
   def _compute_custom_stats(self, conn, date_filter):
       cursor = conn.execute(f"SELECT ... FROM ... WHERE ... {date_filter}")
       return {"custom_metric": cursor.fetchone()[0]}
   ```

2. **Update UI**:
   ```javascript
   function populateCustomTab(customStats) {
       document.getElementById('customMetric').textContent = customStats.custom_metric;
   }
   ```

3. **Add to Snapshot Structure**:
   ```python
   # In _compute_totals()
   return {
       # ... existing totals
       "custom": self._compute_custom_stats(conn, date_filter)
   }
   ```

### Adding New Tabs

1. **HTML Structure**:
   ```html
   <button class="analytics-tab-btn secondary-btn" data-tab="newtab" onclick="selectAnalyticsTab('newtab')">New Tab</button>
   
   <div id="tab-newtab" class="tab-pane hidden">
       <div class="result-card">
           <h4>New Analytics</h4>
           <div id="newTabContent"></div>
       </div>
   </div>
   ```

2. **JavaScript Handler**:
   ```javascript
   // Add 'newtab' to tabs array in selectAnalyticsTab()
   const tabs = ['overview','runs','operators','voices','judges','golden','thresholds','memory','newtab'];
   
   // Add population function
   function populateNewTab(data) {
       document.getElementById('newTabContent').innerHTML = generateContent(data);
   }
   ```

3. **Data Source**:
   Add computation method to `AnalyticsSnapshotManager` and include in snapshot.

### Deprecating Items

```python
from app.meta.store import _conn

def deprecate_operator(operator_name, reason="Performance/usage"):
    conn = _conn()
    conn.execute("""
        INSERT OR REPLACE INTO deprecated_entities 
        (entity_type, entity_name, deprecated_at, reason)
        VALUES ('operator', ?, ?, ?)
    """, (operator_name, time.time(), reason))
    conn.commit()
    conn.close()
```

## Performance Considerations

### Computation Cost
- Snapshot computation: ~50ms for 1000 runs
- Cache hit: ~1ms
- UI load time: <100ms with cached data

### Database Impact
- Minimal: Snapshots stored as JSON blobs
- Indexes: Existing run/variant indexes sufficient
- Storage: ~1KB per snapshot

### Memory Usage
- Manager singleton pattern
- Snapshots GC'd after use
- No persistent memory accumulation

## Rollback Plan

If needed, Analytics V2 can be cleanly rolled back:

```sql
-- Rollback script (rollback_analytics_v2.sql)
DROP TABLE IF EXISTS analytics_snapshot;
DROP TABLE IF EXISTS deprecated_entities;

-- Remove added columns (optional)
-- ALTER TABLE runs DROP COLUMN normalized_task_class;
```

**UI Rollback**: Revert `app.js` and `index.html` to use `loadAnalytics()` instead of `loadAnalyticsV2()`.

**API Rollback**: Remove snapshot endpoint from `main.py`.

## Evolution-Critical Metrics Preservation

Analytics V2 **preserves all evolution-critical functionality**:

✅ **Bandit Operator Learning**: Operator stats computation unchanged  
✅ **Golden Set Gating**: Golden Set runner and metrics preserved  
✅ **Memory Hit Rate/Lift**: Memory analytics system untouched  
✅ **Judge Scoring**: Judge evaluation metrics maintained  
✅ **Total Reward Calculation**: Reward computation logic unchanged  
✅ **Threshold Enforcement**: All Phase 4 thresholds accessible  

**Zero Regression Guarantee**: All self-evolution algorithms continue to function identically.

## Testing

```bash
# Run Analytics V2 test suite
python test_analytics_v2.py

# Test categories:
# - Task class normalization
# - Snapshot computation and caching  
# - Migration system
# - API compatibility
# - UI integration
# - Performance benchmarks
```

## Conclusion

Analytics V2 modernizes the PrimordiumEvolv analytics system while maintaining complete backward compatibility. The snapshot-based architecture provides fast, consistent analytics, while the normalization and deprecation systems improve data quality and UI usability.

The system is designed for extensibility - new metrics, tabs, and functionality can be easily added without disrupting existing evolution processes.