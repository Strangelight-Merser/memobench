from .schema import ABSTAIN, Case

_ABSTAIN_WORDS = (ABSTAIN, "不清楚", "没有提到", "未提及", "无法确定", "不记得")


def _norm(s):
    return s.lower().replace(" ", "")


def score(case: Case, answer: str):
    """返回 (是否正确, 是否泄露了应遗忘/已过期的信息)。"""
    a = _norm(answer)
    leaked = any(_norm(f) in a for f in case.forbidden)
    if case.answers == [ABSTAIN]:
        ok = any(w in answer for w in _ABSTAIN_WORDS) and not leaked
    else:
        ok = all(_norm(x) in a for x in case.answers) and not leaked
    return ok, leaked
