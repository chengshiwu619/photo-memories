import os
import subprocess
from datetime import datetime

from logger_setup import logger
from config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, get_settings
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState

ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
ES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "everything", "es.exe")
FALLBACK_ES = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "es_tool", "es.exe")

_ES_INSTANCE = None
_BAD_PATH_COUNT = 0
_BAD_PATH_SAMPLES = []
BAD_PATH_SAMPLE_LIMIT = 10

_db = Database()
_cp = CheckpointManager(_db, "scan")

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
        text = result.stdout.decode("gbk", errors="replace").strip()
        return text, result.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"es.exe 调用失败: {e}")
        return "", -1


def _reset_bad_path_stats():
    global _BAD_PATH_COUNT, _BAD_PATH_SAMPLES
    _BAD_PATH_COUNT = 0
    _BAD_PATH_SAMPLES = []


def _record_bad_path_sample(filepath, reason):
    global _BAD_PATH_COUNT
    _BAD_PATH_COUNT += 1
    if len(_BAD_PATH_SAMPLES) < BAD_PATH_SAMPLE_LIMIT:
        _BAD_PATH_SAMPLES.append({"path": filepath, "reason": reason})


def _get_bad_path_stats():
    return _BAD_PATH_COUNT, list(_BAD_PATH_SAMPLES)


_drive_mappings_cache = None


def _resolve_unc_host(unc_path):
    host = unc_path[2:].split("\\")[0] if unc_path.startswith("\\\\") else ""
    if not host:
        return ""
    try:
        import socket
        ip = socket.gethostbyname(host)
        return ip if ip != host else ""
    except Exception:
        return ""


def _get_drive_mappings():
    global _drive_mappings_cache
    if _drive_mappings_cache is not None:
        return _drive_mappings_cache

    drive_to_unc = {}
    unc_to_drive = {}

    try:
        result = subprocess.run(
            ["net", "use"],
            capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        text = result.stdout.decode("gbk", errors="replace")
        for line in text.split("\n"):
            parts = line.split()
            if len(parts) >= 3 and len(parts[1]) == 2 and parts[1][1] == ':' and parts[2].startswith("\\\\"):
                drive = parts[1].upper()
                unc = parts[2].rstrip("\\")
                drive_to_unc[drive] = unc
                unc_to_drive[unc.upper()] = drive

                ip = _resolve_unc_host(unc)
                if ip:
                    unc_with_ip = "\\\\" + ip + unc[2 + len(unc[2:].split("\\")[0]):]
                    unc_to_drive[unc_with_ip.upper()] = drive
    except Exception:
        pass

    _drive_mappings_cache = (drive_to_unc, unc_to_drive)
    return _drive_mappings_cache


def _expand_source_dir_prefixes(sd):
    sd_norm = sd.rstrip("\\")
    prefixes = {sd_norm + "\\"}

    drive_to_unc, unc_to_drive = _get_drive_mappings()

    if len(sd_norm) >= 2 and sd_norm[1] == ':':
        drive = sd_norm[:2].upper()
        if drive in drive_to_unc:
            unc_root = drive_to_unc[drive]
            remainder = sd_norm[2:]
            prefixes.add((unc_root + remainder).rstrip("\\") + "\\")

    if sd_norm.startswith("\\\\"):
        sd_upper = sd_norm.upper()
        for unc_key, drive in unc_to_drive.items():
            if sd_upper.startswith(unc_key):
                remainder = sd_norm[len(unc_key):]
                prefixes.add((drive + remainder).rstrip("\\") + "\\")

        ip = _resolve_unc_host(sd_norm)
        if ip:
            ip_prefix = "\\\\" + ip + sd_norm[2 + len(sd_norm[2:].split("\\")[0]):]
            ip_prefix = ip_prefix.rstrip("\\") + "\\"
            prefixes.add(ip_prefix)
            for unc_key, drive in unc_to_drive.items():
                if ip_prefix.upper().startswith(unc_key):
                    remainder = ip_prefix[len(unc_key):].rstrip("\\")
                    prefixes.add((drive + remainder).rstrip("\\") + "\\")

    return prefixes


def _normalize_filepath(filepath, source_dir):
    sd_norm = source_dir.rstrip("\\")
    fp_norm = filepath

    drive_to_unc, unc_to_drive = _get_drive_mappings()

    if sd_norm.startswith("\\\\") and len(fp_norm) >= 2 and fp_norm[1] == ':':
        drive = fp_norm[:2].upper()
        if drive in drive_to_unc:
            remainder = fp_norm[2:]
            return sd_norm + remainder

    if len(sd_norm) >= 2 and sd_norm[1] == ':' and fp_norm.startswith("\\\\"):
        fp_upper = fp_norm.upper()
        best_len = 0
        best_drive = None
        best_unc_key = None
        for unc_key, drive in unc_to_drive.items():
            if fp_upper.startswith(unc_key) and len(unc_key) > best_len:
                best_len = len(unc_key)
                best_drive = drive
                best_unc_key = unc_key
        if best_drive:
            remainder = fp_norm[len(best_unc_key):]
            return best_drive + remainder

    if sd_norm.startswith("\\\\") and fp_norm.startswith("\\\\"):
        sd_host = sd_norm[2:].split("\\")[0]
        fp_host = fp_norm[2:].split("\\")[0]
        if sd_host.lower() != fp_host.lower():
            remainder = fp_norm[2 + len(fp_host):]
            return sd_norm + remainder

    return filepath


def _match_source_dir(filepath):
    for sd in get_settings().source_dirs:
        for prefix in _expand_source_dir_prefixes(sd):
            if filepath.startswith(prefix) or filepath.startswith(prefix.replace("\\", "/")):
                return sd
    return None


def _file_list_cache_path(settings=None):
    _s = settings or get_settings()
    return os.path.join(_s.photo_data_dir, "filelist.txt")


def _source_cache_keys(settings=None):
    _s = settings or get_settings()
    keys = {os.path.normpath(_s.source_drive)}
    keys.update(os.path.normpath(p) for p in _s.source_dirs)
    return keys


def load_cached_file_list(settings=None):
    _s = settings or get_settings()
    list_file = _file_list_cache_path(_s)
    if not os.path.exists(list_file):
        return None

    with open(list_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return None

    header_prefix = "# SOURCE_DRIVE="
    header = lines[0].strip()
    if not header.startswith(header_prefix):
        return None

    cached_source = os.path.normpath(header[len(header_prefix):])
    if cached_source not in _source_cache_keys(_s):
        logger.info("缓存文件列表来源不匹配当前 SOURCE_DRIVE, 重新扫描")
        return None

    paths = []
    skipped = 0
    for line in lines[1:]:
        path = os.path.normpath(line.rstrip("\n"))
        if not path.strip():
            continue
        if "\ufffd" in path or "?" in path:
            skipped += 1
            continue
        paths.append(path)

    if skipped:
        logger.warning(f"缓存文件列表跳过 {skipped} 个编码损坏路径")
    if paths:
        logger.info(f"使用缓存文件列表: {len(paths)} 个文件")
        return paths
    return None


def _list_all_image_files():
    _s = get_settings()
    cached = load_cached_file_list(_s)
    if cached:
        return cached

    list_file = os.path.join(_s.photo_data_dir, "filelist.txt")
    if os.path.exists(list_file):
        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].strip() == f"# SOURCE_DRIVE={os.path.normpath(_s.source_drive)}":
            paths = []
            skipped = 0
            for l in lines[1:]:
                p = os.path.normpath(l.rstrip("\n"))
                if not p.strip():
                    continue
                if "\ufffd" in p or "?" in p:
                    skipped += 1
                    continue
                paths.append(p)
            if skipped:
                logger.warning(f"缓存文件列表跳过 {skipped} 个编码损坏路径")
            if paths:
                logger.info("使用缓存文件列表: %s 个文件" % len(paths))
                return paths
        logger.info("缓存文件列表来源不匹配当前 SOURCE_DRIVE, 重新扫描")

    inst = _detect_instance()
    if inst == "__FAIL__":
        logger.info("Everything IPC 不可用, 回退 os.walk")
        return _walk_files()

    logger.info("Everything 全量扫描: %s (实例: [%s])" % (_s.source_drive, inst or "默认"))

    ext_list = [e.lstrip(".") for e in ALL_EXTENSIONS]
    ext_query = "ext:%s" % ";".join(ext_list)
    logger.info("查询: %s (全局扩展名搜索, Python侧过滤路径)" % ext_query)

    out, code = _run_es(["-csv", "-no-header", ext_query], timeout=120)

    if code == 0 and out:
        files = _parse_es_csv(out)
        logger.info("Everything 返回 %s 条记录, 过滤后 %s 个媒体文件" % (len(out.split("\n")), len(files)))
        if files:
            os.makedirs(_s.photo_data_dir, exist_ok=True)
            tmp = list_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(f"# SOURCE_DRIVE={os.path.normpath(_s.source_drive)}\n")
                for fp in files:
                    f.write(fp + "\n")
            os.replace(tmp, list_file)
            logger.info("文件列表已缓存: %s" % list_file)
            return files

    logger.info("Everything 查询失败, 回退 os.walk")
    return _walk_files()


def _parse_es_csv(text):
    files = []
    for line in text.strip().split("\n"):
        line = line.strip()
        filepath = line.strip("\"")
        if "\ufffd" in filepath or "?" in filepath:
            _record_bad_path_sample(filepath, "encoding_damaged")
            continue
        sd = _match_source_dir(filepath)
        if sd is None:
            continue
        filepath = _normalize_filepath(filepath, sd)
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ALL_EXTENSIONS:
            files.append(filepath)
    return files


def _walk_files():
    _s = get_settings()
    list_file = os.path.join(_s.photo_data_dir, "filelist.txt")
    if os.path.exists(list_file):
        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].strip() == f"# SOURCE_DRIVE={os.path.normpath(_s.source_drive)}":
            paths = [os.path.normpath(line.rstrip("\n")) for line in lines[1:] if line.strip()]
            if paths:
                logger.info(f"使用缓存文件列表: {len(paths)} 个文件")
                return paths
        logger.info("缓存文件列表来源不匹配当前 SOURCE_DRIVE, 重新扫描")

    logger.info("os.walk 遍历中, 请耐心等待...")
    os.makedirs(_s.photo_data_dir, exist_ok=True)
    tmp_file = list_file + ".tmp"
    file_list = []
    with open(tmp_file, "w", encoding="utf-8") as fout:
        fout.write(f"# SOURCE_DRIVE={os.path.normpath(_s.source_drive)}\n")
        for source_dir in _s.source_dirs:
            if not os.path.isdir(source_dir):
                logger.warning(f"照片库路径不存在, 跳过: {source_dir}")
                continue
            for root, dirs, files in os.walk(source_dir):
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


def normalize_path_identity(filepath):
    path = os.path.normpath(str(filepath or "")).replace("/", "\\")
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\" + path[7:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return path.rstrip("\\").casefold()


def _canonicalize_discovered_path(filepath):
    path = os.path.normpath(filepath)
    sd = _match_source_dir(path)
    if sd is not None:
        path = _normalize_filepath(path, sd)
    return os.path.normpath(path)


def _iter_walk_files(limit=None, verbose=False):
    _s = get_settings()
    yielded = 0
    for source_dir in _s.source_dirs:
        if not os.path.isdir(source_dir):
            logger.warning(f"照片库路径不存在, 跳过: {source_dir}")
            continue
        for root, dirs, files in os.walk(source_dir):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in ALL_EXTENSIONS:
                    if verbose:
                        logger.debug(f"跳过非媒体扩展名: {os.path.join(root, fname)}")
                    continue
                yield _canonicalize_discovered_path(os.path.join(root, fname))
                yielded += 1
                if limit and yielded >= limit:
                    return


def _discover_incremental_files(limit=None, prefer_everything=True, verbose=False, es_timeout=None):
    _reset_bad_path_stats()
    if prefer_everything:
        inst = _detect_instance()
        if inst != "__FAIL__":
            ext_list = [e.lstrip(".") for e in ALL_EXTENSIONS]
            ext_query = "ext:%s" % ";".join(ext_list)
            logger.info("增量扫描 Everything 查询: %s" % ext_query)
            timeout = es_timeout or getattr(get_settings(), "everything_timeout_seconds", 20)
            out, code = _run_es(["-csv", "-no-header", ext_query], timeout=timeout)
            if code == 0 and out:
                files = _parse_es_csv(out)
                if files:
                    files = [_canonicalize_discovered_path(fp) for fp in files]
                    if limit:
                        files = files[:limit]
                    logger.info("增量扫描 Everything 返回 %s 个媒体文件" % len(files))
                    return files, "everything"
                if verbose:
                    logger.info("Everything 返回结果未命中配置的照片源目录, 回退目录遍历")
            elif verbose:
                logger.info("Everything 查询失败或为空, 回退目录遍历")
        elif verbose:
            logger.info("Everything IPC 不可用, 回退目录遍历")

    files = list(_iter_walk_files(limit=limit, verbose=verbose))
    logger.info("增量扫描目录遍历发现 %s 个媒体文件" % len(files))
    return files, "walk"


def _build_file_row(filepath, settings):
    stat = os.stat(filepath)
    folder = os.path.normpath(os.path.dirname(filepath))
    source_dir = _match_source_dir(filepath)
    if source_dir is None and settings.source_dirs:
        source_dir = settings.source_dirs[0]
    is_image = os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS
    return {
        "file_path": filepath,
        "file_name": os.path.basename(filepath),
        "folder_path": folder,
        "folder_name": os.path.basename(folder),
        "file_size": stat.st_size,
        "file_mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "file_hash": None,
        "is_image": 1 if is_image else 0,
        "scanned_at": datetime.now().isoformat(),
        "source_dir": source_dir,
    }


def _load_existing_file_index(db):
    existing = {}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, file_path, file_size, file_mtime, source_dir FROM files"
        ).fetchall()
    for row in rows:
        canonical_path = _canonicalize_discovered_path(row["file_path"])
        existing[normalize_path_identity(canonical_path)] = row
    return existing


def incremental_scan(
    progress_callback=None,
    limit=None,
    dry_run=True,
    verbose=False,
    prefer_everything=True,
    db=None,
    settings=None,
    status_callback=None,
    should_stop=None,
    should_pause=None,
    es_timeout=None,
):
    """Safely discover new/changed media files without deleting source files or DB rows."""
    _s = settings or get_settings()
    scan_db = db or _db
    scan_db.init_tables()

    logger.info(
        "增量扫描开始: source_drive=%s limit=%s dry_run=%s prefer_everything=%s",
        _s.source_drive,
        limit,
        dry_run,
        prefer_everything,
    )

    file_list, discovery_source = _discover_incremental_files(
        limit=limit,
        prefer_everything=prefer_everything,
        verbose=verbose,
        es_timeout=es_timeout,
    )
    bad_path_count, bad_path_samples = _get_bad_path_stats()
    existing = _load_existing_file_index(scan_db)

    stats = {
        "dry_run": bool(dry_run),
        "state": "running",
        "current_task": "scan",
        "discovery_source": discovery_source,
        "scanned": 0,
        "new": 0,
        "existing": 0,
        "changed": 0,
        "skipped": 0,
        "errors": 0,
        "db_inserted": 0,
        "db_updated": 0,
        "thumbnail_pending": 0,
        "tag_pending": 0,
        "bad_path_count": bad_path_count,
        "batch_limit_reached": False,
        "paused": False,
        "stopped": False,
        "samples": {
            "new": [],
            "changed": [],
            "skipped": [],
            "errors": [],
            "bad_paths": bad_path_samples,
        },
    }
    if limit and len(file_list) >= limit:
        stats["batch_limit_reached"] = True

    pending_inserts = []
    pending_updates = []
    seen_keys = set()

    total = len(file_list)
    for i, raw_path in enumerate(file_list):
        if _cp.is_pause_or_stop_requested() or (should_stop and should_stop()):
            stats["state"] = "paused" if _cp.is_pause_or_stop_requested() else "stopped"
            stats["paused"] = stats["state"] == "paused"
            stats["stopped"] = stats["state"] == "stopped"
            logger.info("增量扫描收到暂停/停止请求: %s", stats["state"])
            break
        if should_pause and should_pause():
            stats["state"] = "paused"
            stats["paused"] = True
            logger.info("增量扫描收到暂停请求")
            break

        filepath = _canonicalize_discovered_path(raw_path)
        key = normalize_path_identity(filepath)
        stats["scanned"] += 1

        if key in seen_keys:
            stats["skipped"] += 1
            if verbose and len(stats["samples"]["skipped"]) < 10:
                stats["samples"]["skipped"].append({"path": filepath, "reason": "duplicate_in_discovery"})
            continue
        seen_keys.add(key)

        ext = os.path.splitext(filepath)[1].lower()
        if ext not in ALL_EXTENSIONS:
            stats["skipped"] += 1
            if verbose and len(stats["samples"]["skipped"]) < 10:
                stats["samples"]["skipped"].append({"path": filepath, "reason": "unsupported_extension"})
            continue

        try:
            row = _build_file_row(filepath, _s)
        except OSError as exc:
            stats["errors"] += 1
            if len(stats["samples"]["errors"]) < 10:
                stats["samples"]["errors"].append({"path": filepath, "error": str(exc)})
            logger.warning(f"增量扫描读取文件状态失败: {filepath}: {exc}")
            continue

        old = existing.get(key)
        if old is None:
            stats["new"] += 1
            stats["thumbnail_pending"] += 1 if row["is_image"] else 0
            stats["tag_pending"] += 1 if row["is_image"] else 0
            if len(stats["samples"]["new"]) < 10:
                stats["samples"]["new"].append(filepath)
            pending_inserts.append(row)
        elif old["file_size"] != row["file_size"] or old["file_mtime"] != row["file_mtime"]:
            stats["changed"] += 1
            stats["thumbnail_pending"] += 1 if row["is_image"] else 0
            stats["tag_pending"] += 1 if row["is_image"] else 0
            if len(stats["samples"]["changed"]) < 10:
                stats["samples"]["changed"].append(filepath)
            pending_updates.append((row, old["id"]))
        else:
            stats["existing"] += 1
            if verbose and stats["existing"] <= 10:
                logger.debug(f"增量扫描已存在且未变化: {filepath}")

        if progress_callback:
            progress_callback(i + 1, total)
        if status_callback:
            status_callback(dict(stats))

    if dry_run:
        if stats["state"] == "running":
            stats["state"] = "done"
        logger.info("增量扫描 dry-run 完成: %s", stats)
        return stats

    with scan_db.connect() as conn:
        for row in pending_inserts:
            result = conn.execute(
                """INSERT OR IGNORE INTO files
                   (file_path, file_name, folder_path, folder_name, file_size, file_mtime,
                    file_hash, is_image, scanned_at, source_dir)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["file_path"], row["file_name"], row["folder_path"], row["folder_name"],
                    row["file_size"], row["file_mtime"], row["file_hash"], row["is_image"],
                    row["scanned_at"], row["source_dir"],
                ),
            )
            stats["db_inserted"] += result.rowcount

        for row, file_id in pending_updates:
            result = conn.execute(
                """UPDATE files
                   SET file_path = ?, file_name = ?, folder_path = ?, folder_name = ?,
                       file_size = ?, file_mtime = ?, is_image = ?, scanned_at = ?, source_dir = ?
                   WHERE id = ?""",
                (
                    row["file_path"], row["file_name"], row["folder_path"], row["folder_name"],
                    row["file_size"], row["file_mtime"], row["is_image"], row["scanned_at"],
                    row["source_dir"], file_id,
                ),
            )
            stats["db_updated"] += result.rowcount
            if row["is_image"]:
                conn.execute(
                    """UPDATE photo_metadata
                       SET thumbnail_path = NULL, indexed_at = NULL, phash = NULL, is_duplicate_of = NULL
                       WHERE file_id = ?""",
                    (file_id,),
                )
                conn.execute(
                    "DELETE FROM photo_tags WHERE file_id = ? AND source = 'siglip'",
                    (file_id,),
                )

    if stats["state"] == "running":
        stats["state"] = "done"
    if status_callback:
        status_callback(dict(stats))
    logger.info("增量扫描写库完成: %s", stats)
    return stats


def full_scan(progress_callback=None, batch_limit=None):
    _s = get_settings()
    logger.info(f"扫描驱动器: {_s.source_drive} ({len(_s.source_dirs)} 个库)")

    file_list = _list_all_image_files()
    if file_list is None:
        logger.info("Everything 不可用, 使用 os.walk 扫描")
        file_list = _walk_files()

    logger.info(f"磁盘发现 {len(file_list)} 个媒体文件")

    _db.init_tables()

    with _db.connect() as conn:
        existing = set(r[0] for r in conn.execute("SELECT file_path FROM files"))
    logger.info(f"数据库中已有 {len(existing)} 条文件记录")
    total = len(file_list)

    cp = _cp.load()
    if cp and "current_index" not in cp:
        logger.info("旧格式扫描断点, 清理")
        _cp.clear()
        cp = None
    start_idx = cp["current_index"] if cp else 0
    new_added = cp["new_added"] if cp else 0
    batch_count = 0

    is_new = not cp
    if is_new and total > 0:
        _cp.save(CheckpointState.RUNNING, current_index=0, total=total, new_added=0)
        logger.info("新扫描任务已创建检查点")
    elif cp:
        logger.info(f"从断点恢复: idx={start_idx}, total={total}, new_added={new_added}")

    remove_set = set(existing)
    for fp in file_list:
        remove_set.discard(fp)

    pending_writes = []

    for i in range(start_idx, total):
        filepath = os.path.normpath(file_list[i])

        if filepath in existing:
            if progress_callback and (i + 1) % 50 == 0:
                progress_callback(i + 1, total)
            continue

        try:
            stat = os.stat(filepath)
            is_image = os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS
            file_hash = None

            folder = os.path.normpath(os.path.dirname(filepath))
            source_dir = _match_source_dir(filepath) or _s.source_dirs[0] if _s.source_dirs else None
            pending_writes.append((
                filepath,
                os.path.basename(filepath),
                folder,
                os.path.basename(folder),
                stat.st_size,
                datetime.fromtimestamp(stat.st_mtime).isoformat(),
                file_hash,
                1 if is_image else 0,
                datetime.now().isoformat(),
                source_dir,
            ))
            new_added += 1
            batch_count += 1

            if len(pending_writes) >= 50:
                with _db.connect() as conn:
                    conn.executemany(
                        """INSERT OR IGNORE INTO files
                           (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        pending_writes,
                    )
                pending_writes.clear()
        except Exception as e:
            logger.error(f"扫描文件失败 {filepath}: {e}")

        if progress_callback:
            progress_callback(i + 1, total)

        if batch_limit and batch_count >= batch_limit:
            if pending_writes:
                with _db.connect() as conn:
                    conn.executemany(
                        """INSERT OR IGNORE INTO files
                           (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        pending_writes,
                    )
                pending_writes.clear()
            _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, new_added=new_added)
            logger.info(f"扫描热身: {new_added} 条, 剩余 {total - i - 1} 条后台继续")
            return {"paused": True, "batch_limit_reached": True, "total": total, "new": new_added, "removed": 0}

        if (i + 1) % 100 == 0:
            if _cp.is_pause_or_stop_requested():
                if pending_writes:
                    with _db.connect() as conn:
                        conn.executemany(
                            """INSERT OR IGNORE INTO files
                               (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            pending_writes,
                        )
                    pending_writes.clear()
                _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, new_added=new_added)
                logger.info(f"扫描暂停: idx={i + 1}, 新增 {new_added}")

                if remove_set:
                    logger.info(f"清理 {len(remove_set)} 个已移除文件...")
                    with _db.connect() as conn:
                        conn.executemany(
                            "DELETE FROM files WHERE file_path = ?",
                            [(p,) for p in remove_set],
                        )

                return {"paused": True, "total": total, "new": new_added, "removed": len(remove_set)}

            _cp.save(CheckpointState.RUNNING, current_index=i + 1, total=total, new_added=new_added)

    if pending_writes:
        with _db.connect() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO files
                   (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                pending_writes,
            )
        pending_writes.clear()

    if remove_set:
        logger.info(f"清理 {len(remove_set)} 个已移除文件...")
        with _db.connect() as conn:
            conn.executemany(
                "DELETE FROM files WHERE file_path = ?",
                [(p,) for p in remove_set],
            )

    _cleanup_removed_source_dirs()

    with _db.connect() as conn:
        final = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    _cp.clear()

    logger.info(f"扫描完成: 总计 {final} 文件, 新增 {new_added}, 移除 {len(remove_set)}")
    return {"total": final, "new": new_added, "removed": len(remove_set)}


def _cleanup_removed_source_dirs():
    _dirs = get_settings().source_dirs
    if not _dirs:
        return
    placeholders = ",".join("?" * len(_dirs))
    with _db.connect() as conn:
        removed = conn.execute(
            f"SELECT COUNT(*) FROM files WHERE source_dir IS NOT NULL AND source_dir NOT IN ({placeholders})",
            _dirs
        ).fetchone()[0]
        if removed > 0:
            conn.execute(
                f"DELETE FROM files WHERE source_dir IS NOT NULL AND source_dir NOT IN ({placeholders})",
                _dirs
            )
            logger.info(f"清理 {removed} 个不在配置中的照片库文件")


def fast_scan(num_files=1000, progress_callback=None):
    _s = get_settings()
    _db.init_tables()

    if not es_available():
        logger.warning("es.exe 不可用，回退到 os.walk 扫描")
        return None

    import random

    args = ["-csv", "-no-header"]
    if num_files:
        args.append(f"-n {num_files}")

    ext_queries = []
    for ext in ALL_EXTENSIONS:
        for sd in _s.source_dirs:
            ext_queries.append(f"{sd} *{ext}")
    query = "|".join(ext_queries)

    logger.info(f"Everything 快速扫描: {_s.source_drive}")
    out, code = _run_es(args + [query], timeout=120)

    if code != 0 or not out:
        logger.warning("es.exe 返回空或失败")
        return None

    files = []
    for line in out.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        filepath = line.strip('"').replace("\\\\", "\\")
        sd = _match_source_dir(filepath)
        if sd is None:
            continue
        filepath = _normalize_filepath(filepath, sd)
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
                source_dir = _match_source_dir(filepath) or _s.source_dirs[0] if _s.source_dirs else None
                conn.execute(
                    """INSERT OR IGNORE INTO files
                       (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                        source_dir,
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
