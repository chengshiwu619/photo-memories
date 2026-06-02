from ui.app import photos_in_same_folder, safe_dirname, safe_path


def test_safe_path_handles_none_file_path():
    assert safe_path(None) == ""
    assert safe_dirname(None) == ""


def test_safe_dirname_handles_missing_file_path_key():
    photo = {}

    assert safe_dirname(photo.get("file_path")) == ""


def test_safe_dirname_handles_normal_file_path():
    assert safe_dirname(r"D:\photos\trip\a.jpg") == r"D:\photos\trip"


def test_photos_in_same_folder_skips_none_and_missing_file_paths():
    photos = [
        {"id": 1, "file_path": None},
        {"id": 2},
        {"id": 3, "file_path": r"D:\photos\trip\a.jpg"},
        {"id": 4, "file_path": r"D:\photos\trip\b.jpg"},
        {"id": 5, "file_path": r"D:\photos\other\c.jpg"},
    ]

    result = photos_in_same_folder(photos, r"D:\photos\trip")

    assert [p["id"] for p in result] == [3, 4]
