import os
import json
import tempfile
import shutil
from unittest.mock import patch


def test_scan_checkpoint_save_load_cycle():
    from scanner.fast_scan import _save_checkpoint, _load_checkpoint, clear_checkpoint, ScanState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "scan_checkpoint.json")
    try:
        with patch("scanner.fast_scan.CHECKPOINT_FILE", cp_file):
            _save_checkpoint(ScanState.RUNNING, 100, 500, 42)
            cp = _load_checkpoint()
            assert cp is not None
            assert cp["state"] == "running"
            assert cp["current_index"] == 100
            assert cp["total"] == 500
            assert cp["new_added"] == 42
    finally:
        shutil.rmtree(tmp)


def test_scan_checkpoint_clear():
    from scanner.fast_scan import _save_checkpoint, _load_checkpoint, clear_checkpoint, ScanState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "scan_checkpoint.json")
    try:
        with patch("scanner.fast_scan.CHECKPOINT_FILE", cp_file):
            _save_checkpoint(ScanState.RUNNING, 0, 100, 0)
            assert _load_checkpoint() is not None
            clear_checkpoint()
            assert _load_checkpoint() is None
    finally:
        shutil.rmtree(tmp)


def test_scan_checkpoint_pause_state():
    from scanner.fast_scan import _save_checkpoint, _load_checkpoint, set_paused, ScanState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "scan_checkpoint.json")
    try:
        with patch("scanner.fast_scan.CHECKPOINT_FILE", cp_file):
            _save_checkpoint(ScanState.RUNNING, 50, 200, 10)
            set_paused()
            cp = _load_checkpoint()
            assert cp["state"] == "paused"
    finally:
        shutil.rmtree(tmp)


def test_index_checkpoint_save_load_cycle():
    from indexer.photo_indexer import _save_checkpoint, _load_checkpoint, clear_checkpoint, IndexState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "index_checkpoint.json")
    try:
        with patch("indexer.photo_indexer.CHECKPOINT_FILE", cp_file):
            _save_checkpoint(IndexState.RUNNING, 200, 1000, 150)
            cp = _load_checkpoint()
            assert cp is not None
            assert cp["state"] == "running"
            assert cp["current_index"] == 200
            assert cp["total"] == 1000
            assert cp["indexed"] == 150
    finally:
        shutil.rmtree(tmp)


def test_index_checkpoint_clear():
    from indexer.photo_indexer import _save_checkpoint, _load_checkpoint, clear_checkpoint, IndexState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "index_checkpoint.json")
    try:
        with patch("indexer.photo_indexer.CHECKPOINT_FILE", cp_file):
            _save_checkpoint(IndexState.RUNNING, 0, 100, 0)
            assert _load_checkpoint() is not None
            clear_checkpoint()
            assert _load_checkpoint() is None
    finally:
        shutil.rmtree(tmp)


def test_scan_checkpoint_status():
    from scanner.fast_scan import get_checkpoint_status, _save_checkpoint, clear_checkpoint, ScanState
    tmp = tempfile.mkdtemp()
    cp_file = os.path.join(tmp, "scan_checkpoint.json")
    try:
        with patch("scanner.fast_scan.CHECKPOINT_FILE", cp_file):
            assert get_checkpoint_status()["has_checkpoint"] is False
            _save_checkpoint(ScanState.RUNNING, 10, 100, 5)
            status = get_checkpoint_status()
            assert status["has_checkpoint"] is True
            assert status["state"] == "running"
    finally:
        shutil.rmtree(tmp)
