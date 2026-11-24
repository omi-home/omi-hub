"""Chạy lệnh cục bộ (git, lệnh test/lint của dự án)."""
import subprocess


def run_cmd(cmd, cwd=None):
    """str = lệnh của dự án (qua shell); list = lệnh nội bộ như git (không qua shell, tránh injection)."""
    p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=cwd)
    return p.returncode, (p.stdout or "") + (p.stderr or "")
