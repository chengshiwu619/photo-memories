import os
import tempfile
import shutil
from unittest.mock import patch


def test_checkpoint_save_load_cycle():
    from checkpoint_manager import CheckpointManager, CheckpointState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "test_checkpoint.json")
    try:
        cp = CheckpointManager(cp_file)
        cp.save(CheckpointState.RUNNING, current_index=100, total=500, new_added=42)
        data = cp.load()
        assert data is not None
        assert data["state"] == "running"
        assert data["current_index"] == 100
        assert data["total"] == 500
        assert data["new_added"] == 42
    finally:
        shutil.rmtree(tmp)


def test_checkpoint_clear():
    from checkpoint_manager import CheckpointManager, CheckpointState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "test_checkpoint.json")
    try:
        cp = CheckpointManager(cp_file)
        cp.save(CheckpointState.RUNNING, current_index=0, total=100, new_added=0)
        assert cp.load() is not None
        cp.clear()
        assert cp.load() is None
    finally:
        shutil.rmtree(tmp)


def test_checkpoint_pause():
    from checkpoint_manager import CheckpointManager, CheckpointState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "test_checkpoint.json")
    try:
        cp = CheckpointManager(cp_file)
        cp.save(CheckpointState.RUNNING, current_index=50, total=200, new_added=10)
        cp.request_pause()
        data = cp.load()
        assert data["state"] == "paused"
    finally:
        shutil.rmtree(tmp)


def test_checkpoint_stop():
    from checkpoint_manager import CheckpointManager, CheckpointState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "test_checkpoint.json")
    try:
        cp = CheckpointManager(cp_file)
        cp.save(CheckpointState.RUNNING, current_index=50, total=200, new_added=10)
        cp.request_stop()
        data = cp.load()
        assert data["state"] == "stopped"
    finally:
        shutil.rmtree(tmp)


def test_checkpoint_get_status():
    from checkpoint_manager import CheckpointManager, CheckpointState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "test_checkpoint.json")
    try:
        cp = CheckpointManager(cp_file)
        status = cp.get_status()
        assert status["has_checkpoint"] is False
        cp.save(CheckpointState.RUNNING, current_index=10, total=100, new_added=5)
        status = cp.get_status()
        assert status["has_checkpoint"] is True
        assert status["state"] == "running"
    finally:
        shutil.rmtree(tmp)


def test_checkpoint_is_pause_or_stop_requested():
    from checkpoint_manager import CheckpointManager, CheckpointState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "test_checkpoint.json")
    try:
        cp = CheckpointManager(cp_file)
        cp.save(CheckpointState.RUNNING, current_index=10, total=100, new_added=5)
        assert cp.is_pause_or_stop_requested() is False
        cp.request_pause()
        assert cp.is_pause_or_stop_requested() is True
    finally:
        shutil.rmtree(tmp)


def test_scan_checkpoint_compat():
    from scanner.fast_scan import _cp, _db, clear_checkpoint, get_checkpoint_status, set_paused, set_stopped
    from checkpoint_manager import CheckpointState
    clear_checkpoint()
    status = get_checkpoint_status()
    assert status["has_checkpoint"] is False
    _cp.save(CheckpointState.RUNNING, current_index=100, total=500, new_added=42)
    status = get_checkpoint_status()
    assert status["has_checkpoint"] is True
    assert status["current_index"] == 100
    clear_checkpoint()


def test_index_checkpoint_compat():
    from indexer.photo_indexer import _cp, clear_checkpoint, get_checkpoint_status, set_paused, set_stopped
    from checkpoint_manager import CheckpointState
    clear_checkpoint()
    status = get_checkpoint_status()
    assert status["has_checkpoint"] is False
    _cp.save(CheckpointState.RUNNING, current_index=200, total=1000, indexed=150)
    status = get_checkpoint_status()
    assert status["has_checkpoint"] is True
    assert status["indexed"] == 150
    clear_checkpoint()
