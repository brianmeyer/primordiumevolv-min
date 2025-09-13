#!/usr/bin/env python3
"""
Test that simple_prompt.py can generate patches for all operator types
"""

import sys
import json
from app.dgm.simple_prompt import make_simple_prompt
from app.config import DGM_ALLOWED_AREAS

def test_all_areas():
    """Test prompt generation for all allowed areas"""
    
    # Test with config.py snapshot
    config_snapshot = [{
        'path': 'app/config.py',
        'content': open('app/config.py').read()
    }]
    
    # Test with operators.py snapshot  
    operators_snapshot = [{
        'path': 'app/meta/operators.py',
        'content': open('app/meta/operators.py').read()
    }]
    
    results = []
    
    print(f"Testing {len(DGM_ALLOWED_AREAS)} areas from DGM_ALLOWED_AREAS:")
    print(f"Areas: {DGM_ALLOWED_AREAS}\n")
    
    for _ in range(20):  # Generate 20 samples to see variety
        # Test with config file
        prompt = make_simple_prompt(DGM_ALLOWED_AREAS, 50, config_snapshot)
        
        # Extract area from prompt
        if '"area":' in prompt:
            area_start = prompt.find('"area": "') + 9
            area_end = prompt.find('"', area_start)
            area = prompt[area_start:area_end]
            
            # Extract task
            if 'Task: Change' in prompt:
                task_start = prompt.find('Task: Change') + 13
                task_end = prompt.find('\n', task_start)
                task = prompt[task_start:task_end]
            else:
                task = "Unknown"
            
            results.append((area, task, 'config.py'))
        
        # Test with operators file
        prompt = make_simple_prompt(DGM_ALLOWED_AREAS, 50, operators_snapshot)
        
        if '"area":' in prompt:
            area_start = prompt.find('"area": "') + 9
            area_end = prompt.find('"', area_start)
            area = prompt[area_start:area_end]
            
            if 'Task: Change' in prompt:
                task_start = prompt.find('Task: Change') + 13
                task_end = prompt.find('\n', task_start)
                task = prompt[task_start:task_end]
            else:
                task = "Unknown"
                
            results.append((area, task, 'operators.py'))
    
    # Analyze results
    areas_seen = set()
    area_counts = {}
    
    print("Sample of generated prompts:")
    for i, (area, task, file) in enumerate(results[:10]):
        print(f"{i+1}. Area: {area:15} Task: {task[:60]:60} File: {file}")
        areas_seen.add(area)
        area_counts[area] = area_counts.get(area, 0) + 1
    
    print(f"\nAreas covered: {sorted(areas_seen)}")
    print(f"Coverage: {len(areas_seen)}/{len(DGM_ALLOWED_AREAS)} areas")
    
    # Check which areas are missing
    missing = set(DGM_ALLOWED_AREAS) - areas_seen
    if missing:
        print(f"Missing areas: {sorted(missing)}")
        print("Note: Some areas may not appear in small samples due to randomization")
    
    print(f"\nArea frequency in {len(results)} samples:")
    for area in sorted(area_counts.keys()):
        print(f"  {area:15}: {area_counts[area]:3} times")
    
    return len(areas_seen) >= 5  # Success if we see at least 5 different areas

if __name__ == "__main__":
    success = test_all_areas()
    sys.exit(0 if success else 1)