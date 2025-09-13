import logging
logging.basicConfig(level=logging.DEBUG)

from app.dgm.proposer import _parse_response

# Test with markdown wrapped JSON  
test_response = '''```json
{
  "area": "bandit",
  "rationale": "Increase exploration",
  "diff": "--- a/app/config.py\n+++ b/app/config.py\n@@ -23,7 +23,7 @@\n     # UCB Bandit Configuration\n-    \"ucb_c\": float(os.getenv(\"UCB_C\", \"2.0\")),\n+    \"ucb_c\": float(os.getenv(\"UCB_C\", \"2.02\")),\n     \"warm_start_min_pulls\": int(os.getenv(\"WARM_START_MIN_PULLS\", \"1\")),"
}
```'''

result = _parse_response(test_response, "test-model")
print("Parse result:", result)
