import os
import json
import random
from datetime import datetime, timedelta

from logger_setup import logger
from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    CATEGORY_LIFE,
    CATEGORY_SAMPLE,
    CATEGORY_NAMES,
    get_openai_client,
)
from db_manager import Database

_db = Database()


def get_photos_by_category(category, limit=500):
    with _db.connect() as conn:
        used_ids_rows = conn.execute(
            "SELECT DISTINCT photo_ids FROM memories WHERE category = ?",
            (category,),
        ).fetchall()
        used_ids = set()
        for row in used_ids_rows:
            try:
                used_ids.update(json.loads(row[0]))
            except Exception:
                pass

        rows = conn.execute("""
            SELECT f.id, f.file_path, f.file_name, f.folder_name,
                   pm.date_taken, pm.camera_model, pm.thumbnail_path
            FROM files f
            JOIN folder_categories fc ON f.folder_path = fc.folder_path
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE fc.category = ? AND f.is_image = 1
        """, (category,)).fetchall()

    if used_ids:
        rows = [r for r in rows if str(r[0]) not in used_ids]
        logger.info(f"分类 {category}: 排除 {len(used_ids)} 个已用照片, 剩余 {len(rows)} 张")

    return rows


def pick_focused_photos(photos, max_count=12):
    from collections import Counter

    if len(photos) <= max_count:
        return photos

    date_groups = {}
    for p in photos:
        date_taken = p[4]
        if date_taken and len(date_taken) >= 10:
            day = date_taken[:10]
        else:
            day = None
        date_groups.setdefault(day, []).append(p)

    folder_groups = {}
    for p in photos:
        folder = p[3] or "未知"
        folder_groups.setdefault(folder, []).append(p)

    valid_date_groups = {k: v for k, v in date_groups.items()
                         if k is not None and max_count >= len(v) >= 5}
    valid_folder_groups = {k: v for k, v in folder_groups.items()
                           if max_count >= len(v) >= 5}

    candidates = []
    if valid_date_groups:
        keys = list(valid_date_groups.keys())
        random.shuffle(keys)
        best_day = keys[0]
        candidates.append(valid_date_groups[best_day])
        logger.debug(f"聚焦日期: {best_day}, {len(valid_date_groups[best_day])} 张")

    if valid_folder_groups:
        folders = [k for k in valid_folder_groups
                   if not candidates or valid_folder_groups[k] != candidates[0]]
        if folders:
            best_folder = random.choice(folders)
            candidates.append(valid_folder_groups[best_folder])
            logger.debug(f"聚焦文件夹: {best_folder}, {len(valid_folder_groups[best_folder])} 张")

    if candidates:
        pick = random.choice(candidates)
        if len(pick) > max_count:
            pick = random.sample(pick, max_count)
        return pick

    logger.info("无法聚焦到单天/单文件夹, 使用随机采样")
    return random.sample(photos, min(max_count, len(photos)))


def build_photo_context(photos):
    lines = []
    for p in photos:
        file_id, file_path, file_name, folder_name, date_taken, camera, thumb = p
        parts = [file_name]
        if folder_name:
            parts.append(f"文件夹:{folder_name}")
        if date_taken:
            parts.append(f"拍摄:{date_taken[:10]}")
        if camera:
            parts.append(f"设备:{camera}")
        lines.append(" | ".join(parts))

    return "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))


def generate_memories_for_category(category):
    _db.init_tables()

    photos = get_photos_by_category(category)
    category_name = CATEGORY_NAMES[category]
    logger.info(f"为分类 '{category_name}' 生成回忆, 候选照片 {len(photos)} 张")
    if len(photos) < 5:
        logger.info(f"分类 '{category_name}' 照片不足 (<5), 跳过")
        return {"category": category_name, "generated": 0, "reason": "照片太少"}

    from infra.llm.client import get_llm_client
    llm = get_llm_client()

    focused = pick_focused_photos(photos)
    context = build_photo_context(focused)

    logger.info(f"聚焦后 {len(focused)} 张照片用于回忆生成")

    temp = round(random.uniform(0.8, 1.1), 2)
    seeds = ["温暖的", "安静的", "热烈的", "清澈的", "朦胧的", "欢快的", "宁静的", "生动的"]
    seed = random.choice(seeds)

    prompt = f"""你是一个照片回忆助手。根据以下照片信息，生成一条「回忆」。

照片类别：{category_name}
照片来源是 NAS 文件夹，文件名和文件夹名包含归类信息。

回忆规则：
- 为这组照片取一个有温度的标题（6-8字）
- 写一段{seed}描述（30-80字），像是对这些照片的感性回忆
- 不要编造照片中没有的信息

照片列表（格式：编号. 文件名 | 文件夹:xxx | 拍摄:日期 | 设备:xxx）：
{context}

请返回纯 JSON：
{{"title": "标题", "description": "描述"}}"""

    try:
        response = llm.chat(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temp,
        )
        text = response.choices[0].message.content.strip()
        result = json.loads(text)
    except Exception as e:
        logger.error(f"LLM 生成回忆失败 [{category_name}]: {e}")
        return {"category": category_name, "generated": 0}

    title = result.get("title", f"{category_name}回忆")
    description = result.get("description", "")

    photo_ids = [str(p[0]) for p in focused]
    cover_id = focused[0][0] if focused else None

    with _db.connect() as conn:
        conn.execute(
            """INSERT INTO memories (category, memory_type, title, description, photo_ids, cover_file_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                category,
                "auto",
                title,
                description,
                json.dumps(photo_ids),
                cover_id,
                datetime.now().isoformat(),
            ),
        )

    logger.info(f"回忆已生成 [{category_name}]: {title}")

    return {"category": category_name, "generated": 1, "title": title}


MEMORY_CATEGORIES = [CATEGORY_LIFE, CATEGORY_SAMPLE]


def generate_all_memories(progress_callback=None):
    results = []
    for i, cat in enumerate(MEMORY_CATEGORIES):
        if progress_callback:
            progress_callback(i, len(MEMORY_CATEGORIES), CATEGORY_NAMES[cat], "thinking")
        r = generate_memories_for_category(cat)
        if progress_callback:
            progress_callback(i + 1, len(MEMORY_CATEGORIES), CATEGORY_NAMES[cat], "done")
        results.append(r)
    return results


def star_memory(memory_id):
    with _db.connect() as conn:
        conn.execute("UPDATE memories SET is_starred = 1 WHERE id = ?", (memory_id,))


def unstar_memory(memory_id):
    with _db.connect() as conn:
        conn.execute("UPDATE memories SET is_starred = 0 WHERE id = ?", (memory_id,))


def get_memories(category=None, starred_only=False):
    with _db.connect() as conn:
        query = "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at FROM memories WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if starred_only:
            query += " AND is_starred = 1"
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()

    return [
        {
            "id": r[0],
            "category": r[1],
            "category_name": CATEGORY_NAMES.get(r[1], "未知"),
            "memory_type": r[2],
            "title": r[3],
            "description": r[4],
            "photo_ids": json.loads(r[5]) if r[5] else [],
            "cover_file_id": r[6],
            "is_starred": bool(r[7]),
            "created_at": r[8],
        }
        for r in rows
    ]


def get_photo_thumbnails(photo_ids):
    if not photo_ids:
        return []

    with _db.connect() as conn:
        placeholders = ",".join("?" * len(photo_ids))
        rows = conn.execute(
            f"SELECT f.id, f.file_path, f.file_name, f.folder_path, pm.thumbnail_path FROM files f LEFT JOIN photo_metadata pm ON f.id = pm.file_id WHERE f.id IN ({placeholders})",
            photo_ids,
        ).fetchall()

    return [
        {
            "id": r[0],
            "file_path": r[1],
            "file_name": r[2],
            "folder_path": r[3],
            "thumbnail_path": r[4],
        }
        for r in rows
    ]


if __name__ == "__main__":
    results = generate_all_memories()
    for r in results:
        print(f"{r['category']}: 生成 {r['generated']} 条回忆")
