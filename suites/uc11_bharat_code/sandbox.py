"""Run untrusted model-written Python under macOS sandbox-exec: no network, writes only inside a fresh temp dir,
no reads under $HOME (so .env keys stay out of reach) except the Python stdlib, 10 s wall clock, isolated interpreter (python -I)."""
import os, subprocess, sys, tempfile, shutil

PROFILE = """(version 1)
(allow default)
(deny network*)
(deny file-write*)
(deny file-read* (subpath "{home}"))
(allow file-read* (subpath "{pyhome}"))
(allow file-write* (subpath "{tmp}") (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr"))
"""
PY = os.path.realpath(sys.executable)
PYHOME = os.path.realpath(sys.base_prefix)  # stdlib only; the venv and the rest of $HOME are unreadable
HOME = os.path.realpath(os.path.expanduser("~"))


def run_sandboxed(code, timeout=10):
    """Returns (ok, output). ok = exit code 0. Output is stdout+stderr, truncated."""
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="uc11_"))
    try:
        with open(os.path.join(tmp, "main.py"), "w") as f:
            f.write(code)
        prof = PROFILE.format(tmp=tmp, home=HOME, pyhome=PYHOME)
        env = {"PATH": "/usr/bin:/bin", "HOME": tmp, "TMPDIR": tmp, "PYTHONDONTWRITEBYTECODE": "1", "LANG": "en_US.UTF-8"}
        try:
            p = subprocess.run(["sandbox-exec", "-p", prof, PY, "-I", "main.py"], cwd=tmp, env=env,
                               capture_output=True, text=True, timeout=timeout)
            return p.returncode == 0, (p.stdout + p.stderr)[-4000:]
        except subprocess.TimeoutExpired:
            return False, f"TimeoutError: execution exceeded {timeout} s"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":  # self-test: prove the walls hold
    home = os.path.expanduser("~")
    checks = {
        "network": "import urllib.request\nurllib.request.urlopen('https://example.com', timeout=5)",
        "socket": "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=5)",
        "write_home": f"open({os.path.join(home, 'uc11_pwned.txt')!r}, 'w').write('x')",
        "write_tmp_outside": "open('/tmp/uc11_pwned.txt', 'w').write('x')",
        "subprocess_write": f"import subprocess\nsubprocess.run(['touch', {os.path.join(home, 'uc11_pwned2.txt')!r}], check=True)",
        "read_env_keys": f"print(open({os.path.join(home, 'sarvam-bench', '.env')!r}).read()[:3])",
        "timeout": "while True: pass",
    }
    for name, code in checks.items():
        ok, out = run_sandboxed(code, timeout=3)
        print(name, "BLOCKED" if not ok else "!!! ALLOWED", "|", out.strip().splitlines()[-1][:120] if out.strip() else "")
        assert not ok, name
    for f in ("uc11_pwned.txt", "uc11_pwned2.txt"):
        assert not os.path.exists(os.path.join(home, f))
    assert not os.path.exists("/tmp/uc11_pwned.txt")
    ok, out = run_sandboxed("open('scratch.txt','w').write('ok')\nprint(open('scratch.txt').read(), sum(range(10)))")
    print("write_own_tmp + compute", ok, out.strip()); assert ok and "ok 45" in out
    print("sandbox OK")
