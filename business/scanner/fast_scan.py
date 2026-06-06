import os
import subprocess
from datetime import datetime

from logger_setup import logger
from config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, get_settings
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState
from services.path_resolver import (
    resolve_file_path,
    compute_canonical_key,
    normalize_path_slashes,
    PathStatus,
    PathResolveResult,
    is_media_extension,
)

ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ES_PATH = os.path.join(PROJECT_ROOT, "everything", "es.exe")
FALLBACK_ES = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "es_tool", "es.exe")

_ES_INSTANCE = None
_BAD_PATH_COUNT = 0
_BAD_PATH_SAMPLES = []
BAD_PATH_SAMPLE_LIMIT = 20
SCAN_DEFAULT_SAFE_LIMIT = 1000
SCAN_PROGRESS_LOG_INTERVAL = 5000
SCAN_DB_COMMIT_BATCH = 5000

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


def _looks_like_source_path(filepath):
    value = str(filepath or "").replace("/", "\\").casefold()
    if not value:
        return False
    for sd in get_settings().source_dirs:
        for prefix in _expand_source_dir_prefixes(sd):
            norm_prefix = prefix.replace("/", "\\").rstrip("\\").casefold()
            if value.startswith(norm_prefix):
                return True
    return False


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
        if "\ufffd" in path:
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
                if "\ufffd" in p:
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

    query_desc = _build_everything_source_query(_s)
    logger.info("查询: %s (照片根目录限定搜索)" % query_desc)

    files = _query_everything_source_files(timeout=120, settings=_s)
    logger.info("Everything 过滤后 %s 个媒体文件" % len(files))
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
    """解析 Everything CSV 输出，解析并过滤每条路径。

    使用 path_resolver 检测损坏路径、outside_root、不支持的扩展名。
    损坏路径直接丢弃（后续依赖目录遍历 fallback 发现真实 Unicode 路径）。
    """
    files = []
    source_dirs = get_settings().source_dirs
    for line in text.strip().split("\n"):
        line = line.strip()
        filepath = line.strip("\"")
        if not filepath:
            continue

        # 使用 path_resolver 做路径级检查（不 stat，减少 IO）
        result = resolve_file_path(filepath, source_dirs, stat_file=False)
        if result.status == PathStatus.DAMAGED_PATH:
            _record_bad_path_sample(filepath, f"damaged_path: {result.reason}")
            continue
        if result.status == PathStatus.OUTSIDE_ROOT:
            # 不在配置的源目录下，静默跳过
            continue
        if result.status == PathStatus.UNSUPPORTED_EXT:
            continue

        # 通过规范化后的路径
        files.append(result.normalized_path)
    return files


def _build_everything_ext_query():
    ext_list = [e.lstrip(".") for e in sorted(ALL_EXTENSIONS)]
    return "ext:%s" % ";".join(ext_list)


def _everything_source_search_paths(settings=None):
    _s = settings or get_settings()
    paths = []
    seen = set()
    for sd in _s.source_dirs:
        candidates = []
        for prefix in _expand_source_dir_prefixes(sd):
            raw_root = prefix.rstrip("\\/")
            if len(prefix) == 3 and prefix[1] == ":" and prefix[2] in "\\/":
                raw_root = prefix
            root = os.path.normpath(raw_root)
            if not root:
                continue
            candidates.append(root)
        drive_candidates = [p for p in candidates if len(p) >= 2 and p[1] == ":"]
        if drive_candidates:
            candidates = sorted(drive_candidates, key=lambda p: (len(p), p.casefold()))[:1]
        for root in candidates:
            key = root.replace("/", "\\").rstrip("\\").casefold()
            if key in seen:
                continue
            seen.add(key)
            paths.append(root)

    def sort_key(path):
        is_drive = len(path) >= 2 and path[1] == ":"
        return (0 if is_drive else 1, len(path), path.casefold())

    return sorted(paths, key=sort_key)


def _build_everything_source_query(settings=None):
    _s = settings or get_settings()
    ext_query = _build_everything_ext_query()
    source_terms = []
    for root in _everything_source_search_paths(_s):
        if root:
            source_terms.append(f"-path \"{root}\" {ext_query}")
    if not source_terms:
        return ext_query
    return "|".join(source_terms)


def _query_everything_source_files(limit=None, timeout=20, settings=None):
    _s = settings or get_settings()
    ext_query = _build_everything_ext_query()
    files = []
    seen = set()
    paths = _everything_source_search_paths(_s)
    if not paths:
        out, code = _run_es(["-csv", "-no-header", ext_query], timeout=timeout)
        return _parse_es_csv(out) if code == 0 and out else []

    for root in paths:
        remaining = None if limit is None else max(limit - len(files), 0)
        if remaining == 0:
            break
        args = ["-path", root, "-csv", "-no-header"]
        if remaining:
            args.extend(["-n", str(remaining)])
        args.append(ext_query)
        logger.info("Everything source query: -path %s %s", root, ext_query)
        out, code = _run_es(args, timeout=timeout)
        if code != 0 or not out:
            continue
        for filepath in _parse_es_csv(out):
            key = normalize_path_identity(filepath)
            if key in seen:
                continue
            seen.add(key)
            files.append(filepath)
            if limit and len(files) >= limit:
                break
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
    source_dirs = _s.source_dirs
    yielded = 0
    for source_dir in source_dirs:
        if not os.path.isdir(source_dir):
            logger.warning(f"照片库路径不存在, 跳过: {source_dir}")
            continue
        for root, dirs, files in os.walk(source_dir):
            for fname in files:
                raw_path = os.path.join(root, fname)
                # 目录遍历结果也走 path_resolver（检测损坏路径、扩展名等）
                result = resolve_file_path(raw_path, source_dirs, stat_file=False)
                if result.status == PathStatus.UNSUPPORTED_EXT:
                    if verbose:
                        logger.debug(f"跳过非媒体扩展名: {raw_path}")
                    continue
                if result.status == PathStatus.DAMAGED_PATH:
                    _record_bad_path_sample(raw_path, f"damaged_path: {result.reason}")
                    continue
                if result.status == PathStatus.OUTSIDE_ROOT:
                    continue
                yield result.normalized_path
                yielded += 1
                if yielded % 500 == 0:
                    logger.info(f"  目录遍历进度: 已发现 {yielded} 个媒体文件" +
                                (f" (limit={limit})" if limit else ""))
                if limit and yielded >= limit:
                    logger.info(f"  目录遍历已达 limit={limit}，停止遍历")
                    return


def _discover_incremental_files(limit=None, prefer_everything=True, verbose=False, es_timeout=None):
    _reset_bad_path_stats()
    if prefer_everything:
        inst = _detect_instance()
        if inst != "__FAIL__":
            ext_query = _build_everything_source_query()
            logger.info("增量扫描 Everything 查询: %s" % ext_query)
            timeout = es_timeout or getattr(get_settings(), "everything_timeout_seconds", 20)
            files = _query_everything_source_files(limit=limit, timeout=timeout)
            if files:
                # _parse_es_csv 已返回规范化路径，无需再次 canonicalize
                logger.info("增量扫描 Everything 返回 %s 个媒体文件" % len(files))
                return files, "everything"
            if verbose:
                logger.info("Everything 返回结果未命中配置的照片源目录, 回退目录遍历")
        elif verbose:
            logger.info("Everything IPC 不可用, 回退目录遍历")

    files = list(_iter_walk_files(limit=limit, verbose=verbose))
    logger.info("增量扫描目录遍历发现 %s 个媒体文件" % len(files))
    return files, "walk"


def _build_file_row(filepath, settings, resolve_result=None):
    """构建 files 表插入行。

    Args:
        filepath: 规范化后的文件路径
        settings: 配置
        resolve_result: 可选的 PathResolveResult（如果已有 stat 结果）
    """
    folder = os.path.normpath(os.path.dirname(filepath))
    source_dir = _match_source_dir(filepath)
    if source_dir is None and settings.source_dirs:
        source_dir = settings.source_dirs[0]
    is_image = os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS

    if resolve_result is not None and resolve_result.file_size is not None:
        file_size = resolve_result.file_size
        file_mtime = resolve_result.file_mtime
    else:
        stat = os.stat(filepath)
        file_size = stat.st_size
        file_mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

    return {
        "file_path": filepath,
        "file_name": os.path.basename(filepath),
        "folder_path": folder,
        "folder_name": os.path.basename(folder),
        "file_size": file_size,
        "file_mtime": file_mtime,
        "file_hash": None,
        "is_image": 1 if is_image else 0,
        "scanned_at": datetime.now().isoformat(),
        "source_dir": source_dir,
        "canonical_key": compute_canonical_key(filepath),
        "normalized_path": filepath,
        "path_status": PathStatus.OK.value,
        "path_error": None,
    }


def _load_existing_file_index(db):
    """加载已有文件索引，按 canonical_key 索引用于去重匹配。

    如果 canonical_key 为空（旧数据），fallback 到 normalize_path_identity(file_path)。
    """
    existing = {}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, file_path, file_size, file_mtime, source_dir, canonical_key FROM files"
        ).fetchall()
    for row in rows:
        ck = row["canonical_key"] if row["canonical_key"] else compute_canonical_key(row["file_path"])
        if ck:
            existing[ck] = row
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

    # limit 处理：
    # - limit=-1 或 0 表示不限制（全量扫描）
    # - limit=None 时使用安全默认值（避免意外全量扫描阻塞）
    # - 正整数表示每批最大文件数
    requested_limit = limit
    if limit is None:
        limit = SCAN_DEFAULT_SAFE_LIMIT
        logger.info("limit 未指定，使用安全默认值: %s", limit)
    elif isinstance(limit, int) and limit <= 0:
        # limit=0 或负数 → 不限制，全量扫描
        limit = None
        logger.info("limit=%s → 全量扫描（不限制）", requested_limit)

    logger.info(
        "增量扫描开始: source_drive=%s limit=%s dry_run=%s prefer_everything=%s background_scan_limit=%s",
        _s.source_drive,
        limit,
        dry_run,
        prefer_everything,
        limit,
    )
    # 扫描根目录诊断
    for i, sd in enumerate(_s.source_dirs):
        sd_exists = os.path.isdir(sd)
        logger.info("  scan_root[%s]: %s exists=%s", i, sd, sd_exists)
    use_everything = prefer_everything and _detect_instance() != "__FAIL__"
    logger.info("  use_everything=%s everything_available=%s", prefer_everything, es_available())

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
    pending_changed_updates = []   # 真正 size/mtime 变化的文件 → 需重置 thumbnail
    pending_path_updates = []      # 仅 path_status/canonical_key 需补全 → 不重置 thumbnail
    seen_keys = set()

    total = len(file_list)
    source_dirs = _s.source_dirs
    logger.info(
        "scan processing: starting path normalize for %s files (log every %s)",
        total, SCAN_PROGRESS_LOG_INTERVAL,
    )
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

        # 对每条路径做完整 resolve（含 stat），捕获 stat_failed/missing
        # 单文件异常不得卡住全局
        try:
            resolve_result = resolve_file_path(raw_path, source_dirs, stat_file=True)
        except Exception as exc:
            stats["errors"] += 1
            if len(stats["samples"]["errors"]) < 20:
                stats["samples"]["errors"].append({"path": raw_path, "error": f"resolve_exception: {exc}"})
            _record_bad_path_sample(raw_path, f"resolve_exception: {exc}")
            logger.debug("scan resolve 异常: %s: %s", raw_path, exc)
            if (i + 1) % SCAN_PROGRESS_LOG_INTERVAL == 0:
                logger.info(
                    "scan processing: processed=%s/%s new=%s changed=%s existing=%s skipped=%s errors=%s",
                    i + 1, total, stats["new"], stats["changed"], stats["existing"],
                    stats["skipped"], stats["errors"],
                )
            if progress_callback:
                progress_callback(i + 1, total)
            if status_callback:
                status_callback(dict(stats))
            continue

        filepath = resolve_result.normalized_path
        canonical_key = resolve_result.canonical_key
        stats["scanned"] += 1

        # 过滤不可入库的状态
        if resolve_result.status in (PathStatus.DAMAGED_PATH, PathStatus.OUTSIDE_ROOT,
                                       PathStatus.UNSUPPORTED_EXT):
            stats["skipped"] += 1
            if verbose and len(stats["samples"]["skipped"]) < 20:
                stats["samples"]["skipped"].append({
                    "path": raw_path,
                    "reason": f"{resolve_result.status.value}: {resolve_result.reason}",
                })
            _record_bad_path_sample(raw_path, f"{resolve_result.status.value}: {resolve_result.reason}")
            if (i + 1) % SCAN_PROGRESS_LOG_INTERVAL == 0:
                logger.info(
                    "scan processing: processed=%s/%s new=%s changed=%s existing=%s skipped=%s errors=%s",
                    i + 1, total, stats["new"], stats["changed"], stats["existing"],
                    stats["skipped"], stats["errors"],
                )
            if progress_callback:
                progress_callback(i + 1, total)
            if status_callback:
                status_callback(dict(stats))
            continue

        if resolve_result.status in (PathStatus.MISSING, PathStatus.STAT_FAILED):
            stats["errors"] += 1
            if len(stats["samples"]["errors"]) < 20:
                stats["samples"]["errors"].append({
                    "path": filepath,
                    "error": resolve_result.reason,
                })
            _record_bad_path_sample(filepath, f"{resolve_result.status.value}: {resolve_result.reason}")
            logger.debug("增量扫描文件状态异常: %s: %s", filepath, resolve_result.reason)
            if (i + 1) % SCAN_PROGRESS_LOG_INTERVAL == 0:
                logger.info(
                    "scan processing: processed=%s/%s new=%s changed=%s existing=%s skipped=%s errors=%s",
                    i + 1, total, stats["new"], stats["changed"], stats["existing"],
                    stats["skipped"], stats["errors"],
                )
            if progress_callback:
                progress_callback(i + 1, total)
            if status_callback:
                status_callback(dict(stats))
            continue

        # seen_keys 去重（使用 canonical_key）
        if canonical_key in seen_keys:
            stats["skipped"] += 1
            if verbose and len(stats["samples"]["skipped"]) < 20:
                stats["samples"]["skipped"].append({"path": filepath, "reason": "duplicate_canonical_key"})
            continue
        seen_keys.add(canonical_key)

        # 构建文件行（传入已完成的 resolve_result 避免重复 stat）
        try:
            row = _build_file_row(filepath, _s, resolve_result=resolve_result)
        except OSError as exc:
            stats["errors"] += 1
            if len(stats["samples"]["errors"]) < 20:
                stats["samples"]["errors"].append({"path": filepath, "error": str(exc)})
            _record_bad_path_sample(filepath, f"stat_failed: {exc}")
            logger.debug("增量扫描读取文件状态失败: %s: %s", filepath, exc)
            continue
        except Exception as exc:
            # 兜底：任何意外异常都记录并继续，不卡全局
            stats["errors"] += 1
            if len(stats["samples"]["errors"]) < 20:
                stats["samples"]["errors"].append({"path": filepath, "error": f"build_row_exception: {exc}"})
            logger.debug("增量扫描构建文件行异常: %s: %s", filepath, exc)
            continue

        old = existing.get(canonical_key)
        if old is None:
            stats["new"] += 1
            stats["thumbnail_pending"] += 1 if row["is_image"] else 0
            stats["tag_pending"] += 1 if row["is_image"] else 0
            if len(stats["samples"]["new"]) < 20:
                stats["samples"]["new"].append(filepath)
            pending_inserts.append(row)
        elif old["file_size"] != row["file_size"] or old["file_mtime"] != row["file_mtime"]:
            stats["changed"] += 1
            stats["thumbnail_pending"] += 1 if row["is_image"] else 0
            stats["tag_pending"] += 1 if row["is_image"] else 0
            if len(stats["samples"]["changed"]) < 20:
                stats["samples"]["changed"].append(filepath)
            pending_changed_updates.append((row, old["id"]))
        else:
            stats["existing"] += 1
            # 即使文件未变，也更新 path_status / canonical_key（如果旧记录缺少）
            old_ck = old["canonical_key"] if "canonical_key" in old.keys() else None
            old_ps = old["path_status"] if "path_status" in old.keys() else None
            if not old_ck or old_ps != PathStatus.OK.value:
                # 仅补全路径元数据，不重置缩略图
                pending_path_updates.append((row, old["id"]))

        # 进度日志 + 回调
        if (i + 1) % SCAN_PROGRESS_LOG_INTERVAL == 0:
            logger.info(
                "scan processing: processed=%s/%s new=%s changed=%s existing=%s skipped=%s errors=%s",
                i + 1, total, stats["new"], stats["changed"], stats["existing"],
                stats["skipped"], stats["errors"],
            )
        if progress_callback:
            progress_callback(i + 1, total)
        if status_callback:
            status_callback(dict(stats))

    logger.info(
        "scan processing: path normalize complete. total=%s new=%s changed=%s existing=%s skipped=%s errors=%s",
        stats["scanned"], stats["new"], stats["changed"], stats["existing"],
        stats["skipped"], stats["errors"],
    )

    if dry_run:
        if stats["state"] == "running":
            stats["state"] = "done"
        logger.info(
            "增量扫描 dry-run 完成: scanned=%s new=%s existing=%s changed=%s skipped=%s errors=%s",
            stats["scanned"], stats["new"], stats["existing"], stats["changed"],
            stats["skipped"], stats["errors"],
        )
        logger.debug("增量扫描 dry-run 详情: %s", stats)
        return stats

    with scan_db.connect() as conn:
        # --- inserts ---
        logger.info(
            "scan db write: inserting %s new files (batch=%s)",
            len(pending_inserts), SCAN_DB_COMMIT_BATCH,
        )
        for idx, row in enumerate(pending_inserts):
            try:
                result = conn.execute(
                    """INSERT OR IGNORE INTO files
                       (file_path, file_name, folder_path, folder_name, file_size, file_mtime,
                        file_hash, is_image, scanned_at, source_dir,
                        canonical_key, normalized_path, path_status, path_error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["file_path"], row["file_name"], row["folder_path"], row["folder_name"],
                        row["file_size"], row["file_mtime"], row["file_hash"], row["is_image"],
                        row["scanned_at"], row["source_dir"],
                        row["canonical_key"], row["normalized_path"], row["path_status"], row["path_error"],
                    ),
                )
                stats["db_inserted"] += result.rowcount
            except Exception as exc:
                logger.debug("scan db insert 失败: %s: %s", row.get("file_path", "?"), exc)
                continue
            if (idx + 1) % SCAN_DB_COMMIT_BATCH == 0:
                conn.commit()
                logger.info(
                    "scan db write: inserts committed=%s/%s db_inserted=%s",
                    idx + 1, len(pending_inserts), stats["db_inserted"],
                )

        # --- changed updates (重置 thumbnail) ---
        logger.info(
            "scan db write: updating %s changed files (batch=%s)",
            len(pending_changed_updates), SCAN_DB_COMMIT_BATCH,
        )
        for idx, (row, file_id) in enumerate(pending_changed_updates):
            try:
                result = conn.execute(
                    """UPDATE files
                       SET file_path = ?, file_name = ?, folder_path = ?, folder_name = ?,
                           file_size = ?, file_mtime = ?, is_image = ?, scanned_at = ?, source_dir = ?,
                           canonical_key = ?, normalized_path = ?, path_status = ?, path_error = ?
                       WHERE id = ?""",
                    (
                        row["file_path"], row["file_name"], row["folder_path"], row["folder_name"],
                        row["file_size"], row["file_mtime"], row["is_image"], row["scanned_at"],
                        row["source_dir"],
                        row["canonical_key"], row["normalized_path"], row["path_status"], row["path_error"],
                        file_id,
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
            except Exception as exc:
                logger.debug("scan db changed update 失败: file_id=%s: %s", file_id, exc)
                continue
            if (idx + 1) % SCAN_DB_COMMIT_BATCH == 0:
                conn.commit()
                logger.info(
                    "scan db write: changed committed=%s/%s db_updated=%s",
                    idx + 1, len(pending_changed_updates), stats["db_updated"],
                )

        # --- path-only updates (不重置 thumbnail) ---
        logger.info(
            "scan db write: updating %s path-only files (batch=%s)",
            len(pending_path_updates), SCAN_DB_COMMIT_BATCH,
        )
        for idx, (row, file_id) in enumerate(pending_path_updates):
            try:
                conn.execute(
                    """UPDATE files
                       SET canonical_key = ?, normalized_path = ?, path_status = ?, path_error = ?,
                           scanned_at = ?
                       WHERE id = ?""",
                    (
                        row["canonical_key"], row["normalized_path"], row["path_status"],
                        row["path_error"], row["scanned_at"],
                        file_id,
                    ),
                )
                stats["db_updated"] += 1
            except Exception as exc:
                logger.debug("scan db path update 失败: file_id=%s: %s", file_id, exc)
                continue
            if (idx + 1) % SCAN_DB_COMMIT_BATCH == 0:
                conn.commit()
                logger.info(
                    "scan db write: path-only committed=%s/%s db_updated=%s",
                    idx + 1, len(pending_path_updates), stats["db_updated"],
                )

    logger.info(
        "scan db write: complete. db_inserted=%s db_updated=%s",
        stats["db_inserted"], stats["db_updated"],
    )

    if stats["state"] == "running":
        stats["state"] = "done"
    # 更新 bad_path 统计（包含扫描循环中发现的）
    final_bad_path_count, final_bad_path_samples = _get_bad_path_stats()
    stats["bad_path_count"] = final_bad_path_count
    stats["samples"]["bad_paths"] = final_bad_path_samples
    if status_callback:
        status_callback(dict(stats))
    # 路径合法性统计
    path_ok = stats["scanned"] - stats["skipped"] - stats["errors"]
    path_damaged = sum(1 for s in (stats["samples"].get("skipped", []) + stats["samples"].get("bad_paths", []))
                       if "damaged_path" in str(s.get("reason", "")))
    path_missing = sum(1 for s in stats["samples"].get("errors", [])
                       if "missing" in str(s.get("error", "")).lower() or "MISSING" in str(s.get("error", "")))
    logger.info(
        "scan result: new=%s changed=%s existing=%s batch_limit_reached=%s",
        stats["new"], stats["changed"], stats["existing"], stats["batch_limit_reached"],
    )
    logger.info(
        "path normalize: ok=%s damaged=%s missing=%s unsupported=%s stat_failed=%s",
        path_ok, path_damaged, path_missing,
        sum(1 for s in stats["samples"].get("skipped", []) if "unsupported" in str(s.get("reason", "")).lower()),
        sum(1 for s in stats["samples"].get("errors", []) if "stat" in str(s.get("error", "")).lower()),
    )
    logger.info(
        "增量扫描完成: scanned=%s new=%s existing=%s changed=%s skipped=%s errors=%s "
        "bad_paths=%s discovery=%s batch_limit_reached=%s limit=%s",
        stats["scanned"], stats["new"], stats["existing"], stats["changed"],
        stats["skipped"], stats["errors"], final_bad_path_count,
        discovery_source, stats["batch_limit_reached"], limit,
    )
    logger.debug("增量扫描写库详情: %s", stats)
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
