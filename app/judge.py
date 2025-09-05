from typing import List, Dict, Optional
import json
from app.groq_client import chat_complete, pick_model, available as groq_available
from app.evolve.loop import score_output  # semantic fallback

JUDGE_SYS = """You are a strict evaluator. Compare two candidate answers for the given task and criteria.
Return ONLY JSON with fields:
{"winner":"A|B|tie", "rationale":"brief reason"}"""


def build_judge_messages(task: str, assertions: List[str], out_a: str, out_b: str) -> List[Dict]:
    criteria = "\n".join(f"- {a}" for a in (assertions or []))
    user = f"""Task:
{task}

Criteria:
{criteria if criteria else "No explicit criteria; judge closeness to task intent."}

Candidate A:
{out_a}

Candidate B:
{out_b}

Return JSON only."""
    return [{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}]


def judge_pair(task: str, assertions: List[str], out_a: str, out_b: str) -> Dict:
    if groq_available():
        msgs = build_judge_messages(task, assertions or [], out_a, out_b)
        try:
            content = chat_complete(msgs, model_id=pick_model())
            s = content.strip()
            start = s.find("{")
            end = s.rfind("}")
            if start != -1 and end != -1:
                s = s[start : end + 1]
            data = json.loads(s)
            winner = data.get("winner", "tie").lower()[0]
            return {"winner": "A" if winner == "a" else "B" if winner == "b" else "tie", "rationale": data.get("rationale", "")}
        except Exception:
            pass
    # fallback: semantic scorer
    sa = score_output(out_a, assertions or [], task)
    sb = score_output(out_b, assertions or [], task)
    if abs(sa - sb) < 1e-6:
        return {"winner": "tie", "rationale": "semantic scores equal"}
    return {"winner": "A" if sa > sb else "B", "rationale": f"semantic {sa:.3f} vs {sb:.3f}"}

