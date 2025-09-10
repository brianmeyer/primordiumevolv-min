#!/usr/bin/env python3
"""Test DGM mutation generation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.dgm.mutations import generate_mutation, generate_multiple_mutations, MUTATION_REGISTRY

def test_individual_mutations():
    """Test each mutation type."""
    print("\n=== Testing Individual Mutations ===\n")
    
    for area in MUTATION_REGISTRY.keys():
        print(f"Testing {area}...")
        result = generate_mutation(area)
        
        if result:
            area, diff, notes, loc_delta = result
            print(f"  ✓ Generated: {notes}")
            print(f"    LOC delta: {loc_delta}")
            print(f"    Diff preview: {diff[:100]}...")
        else:
            print(f"  ✗ Failed to generate mutation")
        print()

def test_multiple_mutations():
    """Test generating multiple diverse mutations."""
    print("\n=== Testing Multiple Mutations ===\n")
    
    mutations = generate_multiple_mutations(count=5)
    
    for i, mutation in enumerate(mutations, 1):
        print(f"{i}. Area: {mutation['area']}")
        print(f"   Notes: {mutation['notes']}")
        print(f"   LOC delta: {mutation['loc_delta']}")
        print()
    
    print(f"Generated {len(mutations)} mutations")

def test_proposer_integration():
    """Test proposer with explicit mutations."""
    print("\n=== Testing Proposer Integration ===\n")
    
    from app.dgm.proposer import generate
    
    # Test with high mutation rate
    print("Testing with 100% mutation rate...")
    response = generate(n=3, mutation_rate=1.0)
    
    print(f"Generated {len(response.patches)} proposals")
    for patch in response.patches:
        print(f"  - {patch.id}: {patch.area} ({patch.origin})")
        print(f"    Notes: {patch.notes}")
    
    # Test with mixed mode
    print("\nTesting with 50% mutation rate...")
    response = generate(n=3, mutation_rate=0.5)
    
    print(f"Generated {len(response.patches)} proposals")
    for patch in response.patches:
        print(f"  - {patch.id}: {patch.area} ({patch.origin})")

def main():
    """Run all tests."""
    print("\n" + "="*50)
    print("     DGM MUTATION TEST SUITE")
    print("="*50)
    
    test_individual_mutations()
    test_multiple_mutations()
    
    try:
        test_proposer_integration()
    except Exception as e:
        print(f"\nProposer integration test failed: {e}")
        print("(This is expected if models are not available)")
    
    print("\n" + "="*50)
    print("     TEST COMPLETE")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()