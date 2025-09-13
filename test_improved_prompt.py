#!/usr/bin/env python3
"""
Test the improved DGM proposal generation with explicit prompts
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.proposer import generate, generate_single, DGM_ALLOWED_AREAS, DGM_PROPOSALS

def test_proposals():
    """Test proposal generation with improved prompt"""
    
    # Use only the areas that actually exist
    test_areas = ["bandit", "memory_policy"]
    
    print("Testing DGM proposal generation with IMPROVED EXPLICIT PROMPT...")
    print("=" * 80)
    
    total_attempts = 0
    successful_patches = 0
    failed_patches = []
    all_results = {}
    
    for area in test_areas:
        print(f"\n\nTesting area: {area}")
        print("-" * 40)
        
        # Generate proposals for this area (use generate with only one area)
        result = generate(n=3, allowed_areas=[area])
        all_results[area] = result  # Store for later analysis
        proposals = result.patches  # Access patches attribute
        
        # Count total attempts (valid + rejected)
        total_attempts += len(proposals) + len(result.rejected)
        
        if not proposals:
            print(f"❌ No valid proposals generated for {area}")
            # Check rejected for insights
            if result.rejected:
                print(f"  {len(result.rejected)} proposals were rejected:")
                for rej in result.rejected[:3]:  # Show first 3 rejections
                    print(f"    - {rej.get('reason', 'unknown reason')}")
        else:
            for i, proposal in enumerate(proposals, 1):
                print(f"\n  Proposal {i}/{len(proposals)}:")
                print(f"    Model: {proposal.origin}")
                print(f"    Area: {proposal.area}")
                print(f"    Rationale: {proposal.notes[:100] if proposal.notes else 'N/A'}")
                
                # All patches in proposals should be valid
                print(f"    ✅ Valid patch! Diff preview:")
                diff_lines = proposal.diff.split('\n')[:10] if proposal.diff else []
                for line in diff_lines:
                    print(f"      {line}")
                successful_patches += 1
        
        # Add rejected to failed_patches for tracking
        for rej in result.rejected:
            failed_patches.append({
                'area': area,
                'error': rej.get('reason', 'unknown'),
                'model': rej.get('origin', 'unknown')
            })
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY WITH IMPROVED PROMPT:")
    print(f"  Total attempts: {total_attempts}")
    print(f"  Successful patches: {successful_patches}")
    print(f"  Failed patches: {len(failed_patches)}")
    if total_attempts > 0:
        success_rate = (successful_patches / total_attempts) * 100
        print(f"  SUCCESS RATE: {success_rate:.1f}%")
        
        if success_rate == 100:
            print("\n  🎉 ACHIEVED 100% SUCCESS RATE! 🎉")
        elif success_rate >= 90:
            print("\n  📈 Excellent! Over 90% success rate!")
        elif success_rate >= 75:
            print("\n  ✅ Good progress! Over 75% success rate!")
        else:
            print("\n  ⚠️  Still need improvement...")
    
    if failed_patches:
        print("\n  Failed patches details:")
        for fp in failed_patches:
            print(f"    - {fp['area']} ({fp['model']}): {fp['error'][:100]}")
    
    return successful_patches, failed_patches

if __name__ == "__main__":
    # Set environment variables
    os.environ['FF_DGM'] = '1'
    os.environ['DGM_PROPOSALS'] = '5'  # Test with 5 proposals per area
    os.environ['DGM_USE_JUDGE_POOL'] = '1'  # Use multiple models
    
    successful, failed = test_proposals()
    
    # Exit with error code if not 100% success
    if len(failed) > 0:
        sys.exit(1)
    else:
        print("\n✨ All tests passed! 100% valid patches generated! ✨")
        sys.exit(0)