import os
import hashlib
import sqlite3
from datetime import datetime

from logger_setup import logger
from config import SOURCE_DRIVE, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, DATA_DIR
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState

ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
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
        "current_dir": data.get("current_dir", ""),
        "total_scanned": data.get("total_scanned", 0),
        "total_found": data.get("total_found", 0),
    }


def set_paused():
    _cp.request_pause()


def set_stopped():
    _cp.request_stop()


def compute_hash(filepath, block_size=65536):
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            hasher.update(block)
    return hasher.hexdigest()


def scan_drive(progress_callback=None):
    logger.info(f"开始扫描驱动器: {SOURCE_DRIVE}")
    logger.info("正式模式: 全量扫描")
    _db.init_tables()
    conn = _db.get_persistent_connection()
    cp = _cp.load()

    existing = set()
    for row in conn.execute("SELECT file_path FROM files"):
        existing.add(row[0])
    logger.info(f"数据库中已有 {len(existing)} 条文件记录")

    found = set()
    total_found = cp["total_found"] if cp else 0
    total_scanned = cp["total_scanned"] if cp else 0
    resume_dir = cp["current_dir"] if cp else None
    resume_file_idx = cp["current_file_index"] if cp else 0
    folder_counts = {}

    if resume_dir and not os.path.exists(resume_dir):
        logger.warning(f"断点续扫目录不存在: {resume_dir}, 从头开始")
        resume_dir = None
        resume_file_idx = 0

    is_new_scan = not cp
    if is_new_scan:
        _cp.save(CheckpointState.RUNNING, current_dir=SOURCE_DRIVE, current_file_index=0, total_scanned=0, total_found=0)
        logger.info("新扫描任务已创建检查点")
    else:
        logger.info(f"从断点恢复: dir={resume_dir}, idx={resume_file_idx}, scanned={total_scanned}, found={total_found}")

    new_added = 0

    for root, dirs, files in os.walk(SOURCE_DRIVE):
        if resume_dir is not None:
            if root != resume_dir:
                continue

        media_files = [f for f in files if os.path.splitext(f)[1].lower() in ALL_EXTENSIONS]

        if resume_dir is not None:
            media_files = media_files[resume_file_idx:]
            resume_dir = None
            resume_file_idx = 0

        for idx, fname in enumerate(media_files):

            filepath = os.path.join(root, fname)
            found.add(filepath)
            total_found += 1

            if filepath in existing:
                total_scanned += 1
                folder_counts[root] = folder_counts.get(root, 0) + 1
                if progress_callback and total_scanned % 200 == 0:
                    if _cp.is_pause_or_stop_requested():
                        logger.info(f"扫描暂停于 {root}, 已扫描 {total_scanned}, 已发现 {total_found}")
                        conn.commit()
                        conn.close()
                        return {"paused": True, "total_found": total_found, "total_scanned": total_scanned}
                continue

            total_scanned += 1

            try:
                stat = os.stat(filepath)
                is_image = os.path.splitext(fname)[1].lower() in IMAGE_EXTENSIONS
                if is_image:
                    file_hash = compute_hash(filepath)
                else:
                    file_hash = None
                conn.execute(
                    """INSERT OR IGNORE INTO files
                       (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        filepath,
                        fname,
                        root,
                        os.path.basename(root),
                        stat.st_size,
                        datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        file_hash,
                        1 if is_image else 0,
                        datetime.now().isoformat(),
                    ),
                )
                new_added += 1
                folder_counts[root] = folder_counts.get(root, 0) + 1

                if new_added % 50 == 0:
                    conn.commit()
            except Exception as e:
                logger.error(f"扫描文件失败 {filepath}: {e}")

            if progress_callback:
                progress_callback(total_scanned, total_found)

                if _cp.is_pause_or_stop_requested():
                    _cp.save(CheckpointState.PAUSED, current_dir=root, current_file_index=idx + 1, total_scanned=total_scanned, total_found=total_found)
                    logger.info(f"扫描暂停, 检查点已保存: dir={root}")
                    conn.commit()
                    conn.close()
                    return {"paused": True, "total_found": total_found, "total_scanned": total_scanned}

        _cp.save(CheckpointState.RUNNING, current_dir=root, current_file_index=0, total_scanned=total_scanned, total_found=total_found)

    removed = existing - found
    if removed:
        logger.info(f"检测到 {len(removed)} 个已移除文件, 清理数据库...")
        for path in removed:
            conn.execute("DELETE FROM files WHERE file_path = ?", (path,))

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    conn.close()
    _cp.clear()

    logger.info(f"扫描完成: 总计 {total} 文件, 新增 {new_added}, 移除 {len(removed)}")
    return {"total": total, "new": new_added, "removed": len(removed)}


if __name__ == "__main__":
    result = scan_drive()
    if result.get("paused"):
        print(f"扫描暂停: 已扫描 {result['total_scanned']}, 共发现 {result['total_found']}")
    else:
        print(f"扫描完成: 总计 {result['total']} 文件, 新增 {result['new']}, 移除 {result['removed']}")
