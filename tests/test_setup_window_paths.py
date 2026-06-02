from ui.components.setup_window import _normalize_source_input_path


def test_normalize_source_input_path_keeps_unc_paths_valid():
    assert _normalize_source_input_path(r"\server\share\Photos") == r"\\server\share\Photos"
    assert _normalize_source_input_path(r"\\server\share\Photos") == r"\\server\share\Photos"
    assert _normalize_source_input_path(r"D:\Photos") == r"D:\Photos"
