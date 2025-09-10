# DELETE_PLAN.md

## Temporary/Scaffold Files for Removal

This document lists files and directories identified for deletion to clean the repository.

### Temporary Runtime Files
```
.reset_live.out          # Reset operation output file
.uvicorn.pid            # Process ID file for uvicorn server
```

### Backup Directories
```
backups/                # Historical backup directories
├── 20250908_212210/    # Dated backup from Sep 8
└── 20250908_212210 2/  # Duplicate backup directory
```

### Logs Directory
```
logs/                   # Runtime log files directory (54 files)
```

### Run Data Directories
```
runs/                   # Evolution run data directories (100+ timestamped folders)
├── 1757039465/         # Example run directory
├── 1757039494/         # Example run directory
├── 1757040186/         # Example run directory
└── ... (100+ more)     # Many timestamped run directories
```

## Summary

**Total items for removal:** ~110+ files and directories

**Categories:**
- Runtime process files: 2 files
- Backup directories: 2 directories + contents  
- Log files: 1 directory with ~54 files
- Run data: 1 directory with 100+ timestamped subdirectories

**Recommended action:** Remove all items listed above as they are:
1. Runtime artifacts that will be regenerated
2. Historical data not needed for production baseline
3. Development/debugging artifacts

**No duplicate modules** (*_old.py, *_copy.py) were found in app/dgm/**
**No large patch files** (>1MB) were found in meta/patches/**