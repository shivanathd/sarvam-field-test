"""Glue candidate code + hidden tests into one program, run it in the sandbox, parse the verdict."""
import json
from sandbox import run_sandboxed

FOOTER = '''

# ---------------- hidden tests (appended by the harness) ----------------
import datetime as _dt, json as _json, math as _math, unicodedata as _ud, traceback as _tb
def _nfc(s): return _ud.normalize("NFC", s) if isinstance(s, str) else s
def _same(got, exp):
    if isinstance(exp, bool) or exp is None or isinstance(got, bool):
        return got is exp or (isinstance(got, bool) and isinstance(exp, bool) and got == exp)
    if isinstance(exp, float):
        return isinstance(got, (int, float)) and _math.isclose(got, exp, abs_tol=1e-6)
    if isinstance(exp, int):
        return type(got) is int and got == exp
    if isinstance(exp, (tuple, list)):
        return isinstance(got, (tuple, list)) and len(got) == len(exp) and all(_same(a, b) for a, b in zip(got, exp))
    if isinstance(exp, dict):
        return isinstance(got, dict) and got.keys() == exp.keys() and all(_same(got[k], exp[k]) for k in exp)
    return type(got) is type(exp) and got == exp
_TESTS = %s
_fails = []
for _call, _exp in _TESTS:
    try:
        if _exp.startswith("RAISES:"):
            _want = _exp.split(":", 1)[1]
            try:
                _got = eval(_call)
                _fails.append(f"{_call} -> expected {_want} to be raised, got {_got!r}")
            except Exception as _e:
                if type(_e).__name__ != _want and not (_want == "ValueError" and isinstance(_e, ValueError)):
                    _fails.append(f"{_call} -> expected {_want}, got {type(_e).__name__}: {_e}")
            continue
        _got, _e = eval(_call), eval(_exp)
        if not _same(_got, _e):
            _fails.append(f"{_call} -> expected {_e!r}, got {_got!r}")
    except Exception as _e:
        _fails.append(f"{_call} -> raised {type(_e).__name__}: {str(_e)[:200]}")
print("__RESULT__" + _json.dumps({"passed": len(_TESTS) - len(_fails), "total": len(_TESTS), "fails": _fails}))
'''


def run_tests(code, tests, timeout=10):
    """Returns dict(ok, passed, total, fails:[str], error:str|None)."""
    ok, out = run_sandboxed(code + FOOTER % repr(tests), timeout=timeout)
    for line in out.splitlines()[::-1]:
        if line.startswith("__RESULT__"):
            r = json.loads(line[len("__RESULT__"):])
            return {"ok": r["passed"] == r["total"], **r, "error": None}
    return {"ok": False, "passed": 0, "total": len(tests), "fails": [], "error": out[-1500:] or "no output"}


def feedback(res, max_fails=5):
    """What a coding-agent harness would show the model after a failed run (truncated)."""
    if res["error"]:
        return "Running your code failed before the tests could finish:\n" + res["error"][-1200:]
    lines = res["fails"][:max_fails]
    more = len(res["fails"]) - len(lines)
    return (f"{res['total'] - res['passed']} of {res['total']} tests failed:\n" + "\n".join(f"- {l[:300]}" for l in lines)
            + (f"\n... and {more} more" if more else ""))


if __name__ == "__main__":  # every reference solution must pass every test, and a wrong solution must fail
    import sys
    from tasks import T
    bad = 0
    for t in T:
        r = run_tests(t["ref"], t["tests"])
        if not r["ok"]:
            bad += 1
            print(t["id"], t["func"], feedback(r))
    assert all(8 <= len(t["tests"]) <= 15 for t in T), [(t["id"], len(t["tests"])) for t in T if not 8 <= len(t["tests"]) <= 15]
    r = run_tests("def is_valid_aadhaar(n): return True", T[0]["tests"]); assert not r["ok"], r
    r = run_tests("syntax error here(", T[0]["tests"]); assert r["error"], r
    print(f"{len(T) - bad}/{len(T)} references pass; tests per task:", sorted(len(t['tests']) for t in T))
    sys.exit(bad)
