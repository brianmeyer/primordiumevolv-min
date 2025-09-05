import threading
import queue
from typing import Dict, List

_lock = threading.Lock()
_subs: Dict[int, List[queue.Queue]] = {}


def subscribe(run_id: int) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _lock:
        _subs.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: int, q: queue.Queue):
    with _lock:
        lst = _subs.get(run_id, [])
        if q in lst:
            lst.remove(q)
        if not lst and run_id in _subs:
            _subs.pop(run_id, None)


def publish(run_id: int, event: dict):
    with _lock:
        lst = list(_subs.get(run_id, []))
    for q in lst:
        try:
            q.put_nowait(event)
        except Exception:
            try:
                q.put(event)
            except Exception:
                pass

