import subprocess
import sys


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False)


_run([sys.executable, "-m", "ruff", "check", "--fix", "."])
_run([sys.executable, "-m", "ruff", "format", "."])
_run(["git", "add", "-u"])
result = _run([sys.executable, "-m", "ruff", "check", "."])
sys.exit(result.returncode)
