import os
import subprocess
from datetime import datetime

from logger_setup import logger
from config import SOURCE_DRIVE, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, DATA_DIR
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState

ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
ES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "everything", "es.exe")
FALLBACK_ES = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "es_tool", "es.exe")

_ES_INSTANCE = None

CHECKPOINT_FILE = os.path.join(DATA_DIR, "scan_checkpoint.json")

_cp = CheckpointManager(CHECKPOINT_FILE)
_db = Database()

ScanState = CheckpointState


def clear_checkpoint():
    _cp.clear()


def get_checkpoint_status():
    status = _cp.get_status()
    if not status["has_checkpoint"]:
        return {"has_checkpoint": False}
    data = status.get("data", {})
    return {
        "has_checkpoint": True,
        "state": data.get("state"),
        "current_index": data.get("current_index", 0),
        "total": data.get("total", 0),
        "new_added": data.get("new_added", 0),
    }


def set_paused():
    _cp.request_pause()


def set_stopped():
    _cp.request_stop()


def _get_es_path():
    if os.path.exists(ES_PATH):
        return ES_PATH
    if os.path.exists(FALLBACK_ES):
        return FALLBACK_ES
    return None


def es_available():
    return _get_es_path() is not None


def _try_start_everything():
    try:
        from everything.ensure import ensure_everything
        return ensure_everything()
    except Exception:
        return False


def _detect_instance():
    global _ES_INSTANCE
    if _ES_INSTANCE is not None:
        return _ES_INSTANCE

    es_exe = _get_es_path()
    if not es_exe:
        _ES_INSTANCE = ""
        return _ES_INSTANCE

    import subprocess as sp
    for inst in ["", "1.5a", "1.5"]:
        cmd = [es_exe, "-instance", inst, "-get-result-count", "C:\\"] if inst else [es_exe, "-get-result-count", "C:\\"]
        try:
            r = sp.run(cmd, capture_output=True, text=True, timeout=10, creationflags=sp.CREATE_NO_WINDOW)
            if r.returncode == 0 and r.stdout.strip().isdigit():
                _ES_INSTANCE = inst
                logger.info(f"Everything 实例: [{inst or '默认'}], 索引 {r.stdout.strip()} 个文件")
                return inst
        except Exception:
            pass
    _ES_INSTANCE = "__FAIL__"
    return _ES_INSTANCE


def _run_es(args, timeout=120):
    es_exe = _get_es_path()
    if not es_exe:
        return "", -1

    inst = _detect_instance()
    if inst == "__FAIL__":
        return "", -1

    if inst:
        cmd = [es_exe, "-instance", inst] + args
    else:
        cmd = [es_exe] + args

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        text = result.stdout.decode("utf-8", errors="replace").strip()
        return text, result.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"es.exe 调用失败: {e}")
        return "", -1


def _list_all_image_files():
    list_file = os.path.join(DATA_DIR, "filelist.txt")
    if os.path.exists(list_file):
        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].strip() == f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}":
            paths = [os.path.normpath(l.rstrip("\n")) for l in lines[1:] if l.strip()]
            if paths:
                logger.info("使用缓存文件列表: %s 个文件" % len(paths))
                return paths
        logger.info("缓存文件列表来源不匹配当前 SOURCE_DRIVE, 重新扫描")

    inst = _detect_instance()
    if inst == "__FAIL__":
        logger.info("Everything IPC 不可用, 回退 os.walk")
        return _walk_files()

    logger.info("Everything 全量扫描: %s (实例: [%s])" % (SOURCE_DRIVE, inst or "默认"))

    ext_list = [e.lstrip(".") for e in ALL_EXTENSIONS]
    ext_query = "ext:%s" % ";".join(ext_list)
    logger.info("查询: %s (全局扩展名搜索, Python侧过滤路径)" % ext_query)

    out, code = _run_es(["-csv", "-no-header", ext_query], timeout=120)

    if code == 0 and out:
        files = _parse_es_csv(out)
        logger.info("Everything 返回 %s 条记录, 过滤后 %s 个媒体文件" % (len(out.split("\n")), len(files)))
        if files:
            os.makedirs(DATA_DIR, exist_ok=True)
            tmp = list_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}\n")
                for fp in files:
                    f.write(fp + "\n")
            os.replace(tmp, list_file)
            logger.info("文件列表已缓存: %s" % list_file)
            return files

    logger.info("Everything 查询失败, 回退 os.walk")
    return _walk_files()


def _parse_es_csv(text):
    src_prefix = SOURCE_DRIVE.rstrip("\\") + "\\"
    files = []
    for line in text.strip().split("\n"):
        line = line.strip()
        filepath = line.strip("\"")
        if not filepath.startswith(src_prefix):
            continue
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ALL_EXTENSIONS:
            files.append(filepath)
    return files


def _walk_files():
    list_file = os.path.join(DATA_DIR, "filelist.txt")
    if os.path.exists(list_file):
        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].strip() == f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}":
            paths = [os.path.normpath(line.rstrip("\n")) for line in lines[1:] if line.strip()]
            if paths:
                logger.info(f"使用缓存文件列表: {len(paths)} 个文件")
                return paths
        logger.info("缓存文件列表来源不匹配当前 SOURCE_DRIVE, 重新扫描")

    logger.info("os.walk 遍历中, 请耐心等待...")
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp_file = list_file + ".tmp"
    file_list = []
    with open(tmp_file, "w", encoding="utf-8") as fout:
        fout.write(f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}\n")
        for root, dirs, files in os.walk(SOURCE_DRIVE):
            for fname in files:
                if os.path.splitext(fname)[1].lower() in ALL_EXTENSIONS:
                    fp = os.path.normpath(os.path.join(root, fname))
                    fout.write(fp + "\n")
                    file_list.append(fp)
            if len(file_list) % 5000 == 0 and file_list:
                fout.flush()
                logger.info(f"  已发现 {len(file_list)} 个文件...")
    os.replace(tmp_file, list_file)
    logger.info(f"文件列表已缓存: {list_file}, 共 {len(file_list)} 个")
    return file_list


def full_scan(progress_callback=None, batch_limit=None):
    logger.info(f"扫描驱动器: {SOURCE_DRIVE}")

    file_list = _list_all_image_files()
    if file_list is None:
        logger.info("Everything 不可用, 使用 os.walk 扫描")
        file_list = _walk_files()

    logger.info(f"磁盘发现 {len(file_list)} 个媒体文件")

    _db.init_tables()
    conn = _db.get_persistent_connection()
    conn.execute("PRAGMA busy_timeout=60000")

    cp = _cp.load()
    if cp and "current_index" not in cp:
        logger.info("旧格式扫描断点, 清理")
        _cp.clear()
        cp = None
    start_idx = cp["current_index"] if cp else 0
    new_added = cp["new_added"] if cp else 0
    batch_count = 0

    existing = set(r[0] for r in conn.execute("SELECT file_path FROM files"))
    logger.info(f"数据库中已有 {len(existing)} 条文件记录")
    total = len(file_list)

    is_new = not cp
    if is_new and total > 0:
        _cp.save(CheckpointState.RUNNING, current_index=0, total=total, new_added=0)
        logger.info("新扫描任务已创建检查点")
    elif cp:
        logger.info(f"从断点恢复: idx={start_idx}, total={total}, new_added={new_added}")

    remove_set = set(existing)
    for fp in file_list:
        remove_set.discard(fp)

    for i in range(start_idx, total):
        filepath = os.path.normpath(file_list[i])

        if filepath in existing:
            if progress_callback and (i + 1) % 50 == 0:
                progress_callback(i + 1, total)
            continue

        try:
            stat = os.stat(filepath)
            is_image = os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS
            if is_image:
                file_hash = None
            else:
                file_hash = None

            folder = os.path.normpath(os.path.dirname(filepath))
            conn.execute(
                """INSERT OR IGNORE INTO files
                   (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    filepath,
                    os.path.basename(filepath),
                    folder,
                    os.path.basename(folder),
                    stat.st_size,
                    datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    file_hash,
                    1 if is_image else 0,
                    datetime.now().isoformat(),
                ),
            )
            new_added += 1
            batch_count += 1

            if new_added % 50 == 0:
                conn.commit()
        except Exception as e:
            logger.error(f"扫描文件失败 {filepath}: {e}")

        if progress_callback:
            progress_callback(i + 1, total)

        if batch_limit and batch_count >= batch_limit:
            _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, new_added=new_added)
            logger.info(f"扫描热身: {new_added} 条, 剩余 {total - i - 1} 条后台继续")
            conn.commit()
            conn.close()
            return {"paused": True, "batch_limit_reached": True, "total": total, "new": new_added, "removed": 0}

        if (i + 1) % 100 == 0:
            if _cp.is_pause_or_stop_requested():
                _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, new_added=new_added)
                logger.info(f"扫描暂停: idx={i + 1}, 新增 {new_added}")
                conn.commit()

                if remove_set:
                    logger.info(f"清理 {len(remove_set)} 个已移除文件...")
                    for path in remove_set:
                        conn.execute("DELETE FROM files WHERE file_path = ?", (path,))
                    conn.commit()

                conn.close()
                return {"paused": True, "total": total, "new": new_added, "removed": len(remove_set)}

            _cp.save(CheckpointState.RUNNING, current_index=i + 1, total=total, new_added=new_added)

    if remove_set:
        logger.info(f"清理 {len(remove_set)} 个已移除文件...")
        for path in remove_set:
            conn.execute("DELETE FROM files WHERE file_path = ?", (path,))
        conn.commit()

    final = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    conn.commit()
    conn.close()
    _cp.clear()

    logger.info(f"扫描完成: 总计 {final} 文件, 新增 {new_added}, 移除 {len(remove_set)}")
    return {"total": final, "new": new_added, "removed": len(remove_set)}


def fast_scan(num_files=1000, progress_callback=None):
    _db.init_tables()

    ext_queries = []
    for ext in ALL_EXTENSIONS:
        ext_queries.append(f"{SOURCE_DRIVE} *{ext}")
    query = "|".join(ext_queries)

    if not es_available():
        logger.warning("es.exe 不可用，回退到 os.walk 扫描")
        return None

    import random

    args = ["-csv", "-no-header"]
    if num_files:
        args.append(f"-n {num_files}")

    logger.info(f"Everything 快速扫描: {SOURCE_DRIVE}")
    out, code = _run_es(args + [query], timeout=120)

    if code != 0 or not out:
        logger.warning("es.exe 返回空或失败")
        return None

    files = []
    for line in out.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith(SOURCE_DRIVE):
            continue
        filepath = line.strip('"').replace("\\\\", "\\")
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ALL_EXTENSIONS:
            files.append(filepath)

    logger.info(f"Everything 返回 {len(files)} 个文件")

    if num_files and len(files) > num_files:
        files = random.sample(files, num_files)

    with _db.connect() as conn:
        existing = set(r[0] for r in conn.execute("SELECT file_path FROM files"))

        new_added = 0
        total = len(files)

        for i, filepath in enumerate(files):
            if filepath in existing:
                if progress_callback and i % 200 == 0:
                    progress_callback(i + 1, total)
                continue

            try:
                stat = os.stat(filepath)
                is_image = os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS
                file_hash = None

                folder = os.path.dirname(filepath)
                conn.execute(
                    """INSERT OR IGNORE INTO files
                       (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        filepath,
                        os.path.basename(filepath),
                        folder,
                        os.path.basename(folder),
                        stat.st_size,
                        datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        file_hash,
                        1 if is_image else 0,
                        datetime.now().isoformat(),
                    ),
                )
                new_added += 1

                if new_added % 50 == 0:
                    conn.commit()
            except Exception as e:
                logger.error(f"扫描文件失败 {filepath}: {e}")

            if progress_callback and (i + 1) % 100 == 0:
                progress_callback(i + 1, total)

        conn.commit()
        final = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    logger.info(f"Everything 扫描完成: 总计 {final} 文件, 新增 {new_added}")
    return {"total": final, "new": new_added, "removed": 0}


if __name__ == "__main__":
    result = full_scan()
    if result.get("paused"):
        print(f"扫描暂停: 新增 {result['new']}, 总计 {result['total']}")
    else:
        print(f"扫描完成: 总计 {result['total']}, 新增 {result['new']}, 移除 {result.get('removed', 0)}")
