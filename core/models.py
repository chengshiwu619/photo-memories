from dataclasses import dataclass, asdict
from typing import Optional, List


@dataclass
class File:
    id: Optional[int] = None
    file_path: str = ""
    file_name: str = ""
    folder_path: str = ""
    folder_name: str = ""
    file_size: Optional[int] = None
    file_mtime: Optional[str] = None
    file_hash: Optional[str] = None
    is_image: int = 1
    scanned_at: Optional[str] = None

    def as_row(self) -> tuple:
        return (
            self.file_path,
            self.file_name,
            self.folder_path,
            self.folder_name,
            self.file_size,
            self.file_mtime,
            self.file_hash,
            self.is_image,
            self.scanned_at
        )


@dataclass
class FolderCategory:
    folder_path: str = ""
    category: int = 1
    confidence: Optional[str] = None
    classified_at: Optional[str] = None

    def as_row(self) -> tuple:
        return (self.folder_path, self.category, self.confidence, self.classified_at)


@dataclass
class PhotoMetadata:
    file_id: int = 0
    date_taken: Optional[str] = None
    camera_model: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail_path: Optional[str] = None
    exif_json: Optional[str] = None
    indexed_at: Optional[str] = None
    is_starred: int = 0

    def as_row(self) -> tuple:
        return (
            self.file_id,
            self.date_taken,
            self.camera_model,
            self.gps_lat,
            self.gps_lon,
            self.width,
            self.height,
            self.thumbnail_path,
            self.exif_json,
            self.indexed_at,
            self.is_starred
        )


@dataclass
class Memory:
    id: Optional[int] = None
    category: int = 1
    memory_type: str = "auto"
    title: str = ""
    description: str = ""
    photo_ids: str = ""
    cover_file_id: Optional[int] = None
    created_at: Optional[str] = None
    is_starred: int = 0

    def as_row(self) -> tuple:
        return (
            self.category,
            self.memory_type,
            self.title,
            self.description,
            self.photo_ids,
            self.cover_file_id,
            self.created_at,
            self.is_starred
        )

    def get_photo_id_list(self) -> List[int]:
        import json
        try:
            return [int(x) for x in json.loads(self.photo_ids)]
        except Exception:
            return []


@dataclass
class ClickHistory:
    id: Optional[int] = None
    file_id: int = 0
    folder_path: str = ""
    category: Optional[int] = None
    clicked_at: Optional[str] = None

    def as_row(self) -> tuple:
        return (self.file_id, self.folder_path, self.category, self.clicked_at)


@dataclass
class PhotoTag:
    id: Optional[int] = None
    file_id: int = 0
    tag: str = ""
    created_at: Optional[str] = None

    def as_row(self) -> tuple:
        return (self.file_id, self.tag, self.created_at)
