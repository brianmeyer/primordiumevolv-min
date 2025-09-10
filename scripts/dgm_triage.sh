#!/bin/bash
# DGM Triage Script - Test proposal system and analyze failures

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== DGM Triage Report ===${NC}"
echo "Testing proposal generation and failure analysis..."
echo ""

# Check if server is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${RED}Error: Server not running on localhost:8000${NC}"
    echo "Please start the server first with: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    exit 1
fi

# Enable DGM if not already enabled
echo -e "${YELLOW}Ensuring DGM is enabled...${NC}"
export FF_DGM=1

# Test DGM proposal endpoint
echo -e "${BLUE}Testing DGM proposal generation...${NC}"

RESPONSE_FILE=$(mktemp)
curl -s -X POST "http://localhost:8000/api/dgm/propose?dry_run=1&shadow_eval=1" \
    -H "Content-Type: application/json" \
    > "$RESPONSE_FILE"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to call DGM proposal endpoint${NC}"
    exit 1
fi

# Check if response is valid JSON
if ! jq empty "$RESPONSE_FILE" > /dev/null 2>&1; then
    echo -e "${RED}Error: Invalid JSON response${NC}"
    cat "$RESPONSE_FILE"
    exit 1
fi

echo -e "${GREEN}✓ DGM proposal endpoint responded${NC}"

# Extract and display key metrics
PATCH_COUNT=$(jq '.count // 0' "$RESPONSE_FILE")
REJECTED_COUNT=$(jq '.rejected | length' "$RESPONSE_FILE")
TOTAL_ATTEMPTS=$(jq '.rejected | length + .count' "$RESPONSE_FILE")
HAS_WINNER=$(jq '.winner != null' "$RESPONSE_FILE")
SMOKE_PATCH_USED=$(jq '.patches[]? | select(.origin == "dgm-smoke") | .id' "$RESPONSE_FILE" | wc -l | tr -d ' ')

echo ""
echo -e "${BLUE}=== Proposal Summary ===${NC}"
echo "Total attempts: $TOTAL_ATTEMPTS"
echo "Accepted patches: $PATCH_COUNT"
echo "Rejected patches: $REJECTED_COUNT"
echo "Has winner: $HAS_WINNER"
echo "Smoke patches used: $SMOKE_PATCH_USED"

# Analyze rejections by reason
echo ""
echo -e "${BLUE}=== Rejection Analysis ===${NC}"

if [ "$REJECTED_COUNT" -gt 0 ]; then
    echo "Rejected patches breakdown:"
    jq -r '.rejected[] | "\(.reason): \(.detail // "No details")"' "$RESPONSE_FILE" | \
    sort | uniq -c | sort -rn | while read count reason_detail; do
        reason=$(echo "$reason_detail" | cut -d':' -f1)
        case "$reason" in
            "bad_json") echo -e "  ${RED}$count × $reason_detail${NC}" ;;
            "bad_diff_format") echo -e "  ${RED}$count × $reason_detail${NC}" ;;
            "path_not_allowed") echo -e "  ${YELLOW}$count × $reason_detail${NC}" ;;
            "loc_delta_exceeded") echo -e "  ${YELLOW}$count × $reason_detail${NC}" ;;
            "git_apply_check") echo -e "  ${RED}$count × $reason_detail${NC}" ;;
            *) echo -e "  $count × $reason_detail" ;;
        esac
    done
else
    echo -e "${GREEN}No rejections found!${NC}"
fi

# Check for smoke patch usage
if [ "$SMOKE_PATCH_USED" -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}=== Smoke Patch Detected ===${NC}"
    jq -r '.patches[] | select(.origin == "dgm-smoke") | "Smoke patch used: \(.id) (\(.area))"' "$RESPONSE_FILE"
    echo "This indicates no regular proposals passed validation."
fi

# Check if we have at least one patch (smoke allowed)
if [ "$PATCH_COUNT" -eq 0 ]; then
    echo ""
    echo -e "${RED}=== CRITICAL: No Valid Patches Generated ===${NC}"
    echo "Even smoke patch failed or is disabled. This breaks end-to-end pipeline."
    echo "Check DGM_ENABLE_SMOKE_PATCH configuration."
else
    echo ""
    echo -e "${GREEN}=== Pipeline Integrity: OK ===${NC}"
    echo "At least one valid patch candidate available."
fi

# Show successful patches
if [ "$PATCH_COUNT" -gt 0 ]; then
    echo ""
    echo -e "${BLUE}=== Accepted Patches ===${NC}"
    jq -r '.patches[] | "ID: \(.id[:8]) | Origin: \(.origin) | Area: \(.area) | LOC: \(.loc_delta)"' "$RESPONSE_FILE"
fi

# Get registry stats
echo ""
echo -e "${BLUE}=== Registry Activity ===${NC}"

REGISTRY_RESPONSE=$(mktemp)
curl -s "http://localhost:8000/api/dgm/registry/stats" > "$REGISTRY_RESPONSE"

if jq empty "$REGISTRY_RESPONSE" > /dev/null 2>&1; then
    ERROR_COUNT=$(jq '.event_counts.error // 0' "$REGISTRY_RESPONSE")
    GUARD_COUNT=$(jq '.event_counts.guard // 0' "$REGISTRY_RESPONSE")
    SHADOW_EVAL_COUNT=$(jq '.event_counts.shadow_eval // 0' "$REGISTRY_RESPONSE")
    
    echo "Error events recorded: $ERROR_COUNT"
    echo "Guard events: $GUARD_COUNT"
    echo "Shadow eval events: $SHADOW_EVAL_COUNT"
else
    echo -e "${YELLOW}Registry stats not available${NC}"
fi

# Show recent violations if any
echo ""
echo -e "${BLUE}=== Recent Issues ===${NC}"

DEBUG_RESPONSE=$(mktemp)
curl -s "http://localhost:8000/api/dgm/debug/last_propose" > "$DEBUG_RESPONSE"

if jq empty "$DEBUG_RESPONSE" > /dev/null 2>&1 && jq '.response' "$DEBUG_RESPONSE" > /dev/null 2>&1; then
    # Look for violations in patches
    VIOLATIONS=$(jq -r '.response.patches[]? | select(.violations) | .violations[]?' "$DEBUG_RESPONSE" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$VIOLATIONS" -gt 0 ]; then
        echo "Guard violations detected:"
        jq -r '.response.patches[] | select(.violations) | .violations[]?' "$DEBUG_RESPONSE" 2>/dev/null
    else
        echo -e "${GREEN}No guard violations in latest run${NC}"
    fi
else
    echo -e "${YELLOW}Debug endpoint not available${NC}"
fi

# Cleanup
rm -f "$RESPONSE_FILE" "$REGISTRY_RESPONSE" "$DEBUG_RESPONSE"

echo ""
echo -e "${BLUE}=== Triage Complete ===${NC}"

# Exit with appropriate code
if [ "$PATCH_COUNT" -eq 0 ]; then
    echo -e "${RED}Triage result: FAIL - No valid patches generated${NC}"
    exit 1
else
    echo -e "${GREEN}Triage result: PASS - Pipeline functional${NC}"
    exit 0
fi