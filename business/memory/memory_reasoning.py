from typing import Optional

from logger_setup import logger
from db_manager import Database
from infra.db.repositories.memory_reasoning_repo import MemoryReasoningRepository
from infra.db.repositories.memories_repo import MemoriesRepository


def record_feedback(memory_id: int, feedback_type: str, reasoning: Optional[str] = None):
    db = Database()
    reasoning_repo = MemoryReasoningRepository(db)
    memories_repo = MemoriesRepository(db)

    reasoning_repo.insert_raw(memory_id, reasoning, feedback_type)

    if feedback_type == "dismiss":
        memories_repo.dismiss(memory_id)
    elif feedback_type == "like":
        memories_repo.increment_click(memory_id)

    logger.info(f"反馈记录: memory_id={memory_id}, type={feedback_type}")


def get_feedback_history(memory_id: int):
    db = Database()
    reasoning_repo = MemoryReasoningRepository(db)
    items = reasoning_repo.get_by_memory_id(memory_id)
    return [{"feedback_type": r.feedback_type, "reasoning": r.reasoning, "created_at": r.created_at} for r in items]


def get_negative_prompt_suffix() -> str:
    db = Database()
    reasoning_repo = MemoryReasoningRepository(db)
    reasons = reasoning_repo.get_negative_reasons(limit=20)

    if not reasons:
        return ""

    return "避免以下内容：" + "；".join(reasons[:5])
