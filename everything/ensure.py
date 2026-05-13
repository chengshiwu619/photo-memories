import os
import subprocess
import time

from logger_setup import logger

_EVERYTHING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "everything")

_INSTANCE = None


def get_es_path():
    bundled = os.path.join(_EVERYTHING_DIR, "es.exe")
    if os.path.exists(bundled):
        return bundled
    legacy = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "es_tool", "es.exe")
    if os.path.exists(legacy):
        return legacy
    return None


def get_everything_path():
    bundled = os.path.join(_EVERYTHING_DIR, "Everything64.exe")
    if os.path.exists(bundled):
        return bundled
    bundled = os.path.join(_EVERYTHING_DIR, "Everything.exe")
    if os.path.exists(bundled):
        return bundled
    return None


def is_everything_running():
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Everything*.exe"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0 and "Everything" in result.stdout
    except Exception:
        return False


def start_everything():
    everything_exe = get_everything_path()
    if not everything_exe:
        logger.warning("Everything.exe 未找到, 请放入 everything/ 目录")
        return False

    if is_everything_running():
        logger.info("Everything 已在运行")
        return True

    logger.info("启动 Everything: %s" % everything_exe)
    try:
        subprocess.Popen(
            [everything_exe, "-startup", "-minimized"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for _ in range(15):
            time.sleep(1)
            if is_everything_running():
                logger.info("Everything 服务已就绪")
                time.sleep(3)
                return True
        logger.warning("Everything 启动超时")
        return False
    except Exception as e:
        logger.error("启动 Everything 失败: %s" % e)
        return False


def detect_instance():
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE

    es = get_es_path()
    if not es:
        _INSTANCE = "__NONE__"
        return _INSTANCE

    for inst in ["", "1.5a", "1.5"]:
        cmd = [es, "-instance", inst, "-get-result-count", "C:\\"] if inst else [es, "-get-result-count", "C:\\"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode == 0 and r.stdout.strip().isdigit():
                _INSTANCE = inst
                logger.info("Everything 实例: [%s], C盘 %s 个文件" % (inst or "默认", r.stdout.strip()))
                return inst
        except Exception:
            pass
    _INSTANCE = "__FAIL__"
    return _INSTANCE


def ensure_everything():
    es = get_es_path()
    if not es:
        logger.warning("es.exe 未找到, Everything 扫描不可用")
        return False

    if not is_everything_running():
        if not start_everything():
            return False

    inst = detect_instance()
    if inst == "__FAIL__":
        logger.warning("Everything IPC 不可用, 请确认 Everything 已启动并完成索引")
        return False

    logger.info("Everything 可用, 实例: [%s]" % (inst or "默认"))
    return True
