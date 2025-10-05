# marketplace/compare_session.py
from typing import List

MAX_COMPARE = 4
SESSION_KEY = "compare_ids"

def _coerce_ids(raw) -> List[int]:
    out = []
    for v in raw or []:
        try:
            out.append(int(v))
        except Exception:
            continue
    # keep unique + stable order
    seen = set()
    uniq = []
    for i in out:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq

def get_ids(request) -> List[int]:
    return _coerce_ids(request.session.get(SESSION_KEY, []))

def set_ids(request, ids: List[int]) -> None:
    request.session[SESSION_KEY] = _coerce_ids(ids)
    request.session.modified = True
