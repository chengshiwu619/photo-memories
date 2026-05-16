from typing import List, Optional

from logger_setup import logger
from db_manager import Database
from core.models import Memory, PhotoMetadata
from infra.db.repositories import (
    MemoriesRepository, PhotoMetadataRepository, FilesRepository, PhotoTagsRepository
)


class DataService:
    def __init__(self, db=None):
        self.db = db or Database()
        self.memories_repo = MemoriesRepository(self.db)
        self.meta_repo = PhotoMetadataRepository(self.db)
        self.files_repo = FilesRepository(self.db)
        self.tags_repo = PhotoTagsRepository(self.db)

    def get_undismissed_memories(self, category: Optional[int] = None) -> List[Memory]:
        return self.memories_repo.get_undismissed(category)

    def get_all_memories(self, category: Optional[int] = None, starred_only: bool = False) -> List[Memory]:
        return self.memories_repo.get_all(category, starred_only)

    def set_memory_starred(self, memory_id: int, starred: bool):
        self.memories_repo.set_starred(memory_id, starred)

    def update_memory_shown(self, memory_id: int):
        self.memories_repo.update_shown(memory_id)

    def dismiss_memory(self, memory_id: int):
        self.memories_repo.dismiss(memory_id)
        logger.info(f"Dismissed memory {memory_id}")

    def get_photo_metadata(self, file_id: int) -> Optional[PhotoMetadata]:
        return self.meta_repo.get_by_file_id(file_id)


def get_data_service() -> DataService:
    return DataService()
