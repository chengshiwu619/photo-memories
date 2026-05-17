import json
from typing import Optional

from logger_setup import logger
from db_manager import Database
from infra.llm.client import get_llm_client
from infra.db.repositories.events_repo import EventsRepository
from infra.db.repositories.memories_repo import MemoriesRepository
from config import get_settings


def narrate_event(event_id: int) -> Optional[str]:
    db = Database()
    events_repo = EventsRepository(db)

    event = events_repo.get_by_id(event_id)
    if not event:
        return None

    prompt = f"""请根据以下照片事件信息，用中文写一段简短的回忆描述（2-3句话）：
- 时间：{event.start_date} 到 {event.end_date}
- 地点：{event.location_name or '未知'}
- 事件类型：{event.event_type}
- 照片数量：{len(event.get_photo_id_list())}

要求：温暖、感性、简洁，不要使用"也许""可能"等不确定词汇。"""

    try:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=get_settings().deepseek_classify_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"事件叙事生成失败 event_id={event_id}: {e}")
        return None


def narrate_memory(memory_id: int) -> Optional[str]:
    db = Database()
    memories_repo = MemoriesRepository(db)

    memory = memories_repo.get_by_id(memory_id)
    if not memory:
        return None

    prompt = f"""请根据以下回忆信息，用中文写一段温暖的回忆描述（2-3句话）：
- 标题：{memory.title}
- 类型：{memory.memory_type}
- 照片数量：{len(memory.get_photo_id_list())}

要求：温暖、感性、简洁，不要使用"也许""可能"等不确定词汇。"""

    try:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=get_settings().deepseek_classify_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"回忆叙事生成失败 memory_id={memory_id}: {e}")
        return None
