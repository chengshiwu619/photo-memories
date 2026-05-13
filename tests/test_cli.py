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
    assert "NAS" in result.stdout or "scan" in result.stdout


def test_cli_setup_no_crash():
    result = subprocess.run(
        [sys.executable, "main.py", "setup"],
        capture_output=True, text=True, timeout=5,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode in (0, 1)


def test_cli_scan_without_config():
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
