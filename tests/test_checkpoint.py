import os
import sqlite3
import tempfile
import shutil


def _make_db():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "photos.db")
    db = Database(db_path)
    db.init_tables()
    return db, tmp


def test_checkpoint_save_load_cycle():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=10, total=100)
        data = cp.load()
        assert data is not None
        assert data["state"] == "running"
        assert data["current_index"] == 10
        assert data["total"] == 100
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_clear():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        cp.clear()
        data = cp.load()
        assert data is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_pause():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        cp.request_pause()
        data = cp.load()
        assert data["state"] == "paused"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_stop():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        cp.request_stop()
        data = cp.load()
        assert data["state"] == "stopped"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_get_status():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        status = cp.get_status()
        assert status["has_checkpoint"] is False

        cp.save(CheckpointState.RUNNING, current_index=5)
        status = cp.get_status()
        assert status["has_checkpoint"] is True
        assert status["state"] == "running"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_is_pause_or_stop_requested():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        assert cp.is_pause_or_stop_requested() is False

        cp.request_pause()
        assert cp.is_pause_or_stop_requested() is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_scan_checkpoint_compat():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "scan")
        cp.save(CheckpointState.RUNNING, current_index=0, total=100, new_added=0)
        data = cp.load()
        assert data["state"] == "running"
        assert data["current_index"] == 0
        assert data["total"] == 100
        assert data["new_added"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_index_checkpoint_compat():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "index")
        cp.save(CheckpointState.RUNNING, current_index=0, total=50, indexed=0)
        data = cp.load()
        assert data["state"] == "running"
        assert data["current_index"] == 0
        assert data["total"] == 50
        assert data["indexed"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
