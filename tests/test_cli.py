import subprocess
import sys
import os


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert result.returncode == 0
    assert "NAS" in result.stdout
    assert "web" in result.stdout
    assert "setup" in result.stdout
    assert "ui" not in result.stdout

def test_cli_rejects_removed_scan_command():
    env = os.environ.copy()
    env["DEEPSEEK_API_KEY"] = ""
    env["SOURCE_DRIVE"] = ""
    env["PHOTO_DATA_DIR"] = ""
    result = subprocess.run(
        [sys.executable, "main.py", "scan"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
    )
    assert result.returncode != 0
    assert "invalid choice" in result.stderr
