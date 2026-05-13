import os
import sqlite3
import json

from logger_setup import logger
from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    CLASSIFICATION_HISTORY_FILE,
    CATEGORY_LIFE,
    CATEGORY_SAMPLE,
    CATEGORY_PHOTOGRAPHY,
    CATEGORY_ADULT,
    CATEGORY_NAMES,
    SOURCE_DRIVE,
    get_openai_client,
)
from db_manager import Database

_db = Database()

MAX_USER_CLASSIFY = 10


def get_unclassified_folders():
    with _db.connect() as conn:
        rows = conn.execute("""
            SELECT DISTINCT f.folder_path FROM files f
            LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
            WHERE fc.folder_path IS NULL
        """).fetchall()
    return [row[0] for row in rows]


def get_all_folders():
    with _db.connect() as conn:
        rows = conn.execute("SELECT DISTINCT folder_path FROM files").fetchall()
    return [row[0] for row in rows]


def _get_branch_folders():
    all_folders = get_all_folders()
    if not all_folders:
        return []

    source = SOURCE_DRIVE.rstrip("\\") + "\\"
    branches = set()
    for fp in all_folders:
        rel = fp[len(source):].lstrip("\\")
        if not rel:
            continue
        parts = rel.split("\\")
        branch = parts[0]
        branches.add(os.path.join(source, branch))

    result = sorted(branches)
    logger.info(f"从 {len(all_folders)} 个文件夹中提取 {len(result)} 个顶层分支")
    return result


def set_folder_category(folder_path, category, confidence=None):
    with _db.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO folder_categories (folder_path, category, confidence, classified_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (folder_path, category, confidence),
        )


def get_folder_category(folder_path):
    with _db.connect() as conn:
        row = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?", (folder_path,)
        ).fetchone()
    return row[0] if row else None


def build_classification_history():
    with _db.connect() as conn:
        rows = conn.execute("""
            SELECT folder_path, category, confidence
            FROM folder_categories
            ORDER BY category, folder_path
        """).fetchall()

    if not rows:
        return ""

    lines = ["# 已分类文件夹历史 (供 LLM 参考)", ""]
    for row in rows:
        folder = row[0]
        cat_id = row[1]
        conf = row[2] or ""
        name = os.path.basename(folder)
        cat_name = CATEGORY_NAMES.get(cat_id, "未知")
        parts = [f"{cat_id}", name, f"({cat_name})"]
        if conf:
            parts.append(f"[{conf}]")
        lines.append(" | ".join(parts))

    text = "\n".join(lines)

    with open(CLASSIFICATION_HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(text)

    logger.info(f"分类历史已写入 {CLASSASSIFICATION_HISTORY_FILE}: {len(rows)} 条")
    return text


def _load_history_context():
    if os.path.exists(CLASSIFICATION_HISTORY_FILE):
        with open(CLASSIFICATION_HISTORY_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return f"""

以下是已确认分类的历史记录，请作为参考：
{content}
"""
    return ""


def classify_branches_with_llm(branch_names):
    client = get_openai_client()

    names_text = "\n".join(f"- {name}" for name in branch_names)
    history = _load_history_context()

    prompt = f"""你是一个照片文件夹分类助手。以下是文件夹的顶层分支名称，请根据名称判断类别。

类别定义：
1 - 生活照片：日常手机拍摄、自拍、随手拍、微信保存等
2 - 拍摄样片：艺人写真、模特样片、cosplay、系列套图等
3 - 摄影照片：摄影作品、相机拍摄、风景街拍等
4 - 色情照片：成人内容、色情写真等

规则：
- 只根据文件夹名称判断，信息不足标记为 0
- 返回纯 JSON，不要其他文字
{history}

文件夹列表：
{names_text}

返回 JSON 对象，key=文件夹名，value=分类数字(0-4)："""

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        result_text = response.choices[0].message.content.strip()
        return json.loads(result_text)
    except Exception as e:
        logger.error(f"LLM 分类出错: {e}")
        return {}


def classify_folders(progress_callback=None):
    from db_manager import Database
    db = Database()
    db.init_tables()

    unclassified = get_unclassified_folders()
    if not unclassified:
        logger.info("没有待分类的文件夹")
        return {"classified": 0, "unknown": 0, "skipped": 0, "needs_user": []}

    build_classification_history()

    branches = _get_branch_folders()
    if not branches:
        return {"classified": 0, "unknown": 0, "skipped": 0, "needs_user": []}

    branch_names = [os.path.basename(b) for b in branches]
    logger.info(f"LLM 分类 {len(branches)} 个顶层分支")
    if progress_callback:
        progress_callback(0, len(branches))

    result = classify_branches_with_llm(branch_names)
    if not result:
        logger.warning("LLM 分类返回空结果，所有分支标记为不确定")
        needs_user = branches[:MAX_USER_CLASSIFY]
        return {"classified": 0, "unknown": len(unclassified), "skipped": 0, "needs_user": needs_user}

    classified_count = 0
    unknown_branches = []

    for branch_path, branch_name in zip(branches, branch_names):
        category = result.get(branch_name, 0)
        try:
            category = int(category)
        except (ValueError, TypeError):
            category = 0

        sub_folders = [f for f in unclassified if f.startswith(branch_path + "\\") or f == branch_path]

        if category in (1, 2, 3, 4):
            for sf in sub_folders:
                set_folder_category(sf, category, "llm-branch")
                classified_count += 1
        else:
            unknown_branches.append(branch_path)

    if progress_callback:
        progress_callback(len(branches), len(branches))

    unknown_count = len(unknown_branches)
    needs_user = unknown_branches[:MAX_USER_CLASSIFY]

    for branch_path in unknown_branches:
        sub_folders = [f for f in unclassified if f.startswith(branch_path + "\\") or f == branch_path]
        for sf in sub_folders:
            set_folder_category(sf, CATEGORY_LIFE, "default")
            classified_count += 1

    build_classification_history()

    logger.info(f"分类完成: 已分类 {classified_count} 个子文件夹, 不确定 {unknown_count} 个分支, 需用户确认 {len(needs_user)}")
    return {
        "classified": classified_count,
        "unknown": unknown_count,
        "skipped": 0,
        "needs_user": needs_user,
    }


def propagate_branch_category(branch_path, category):
    all_folders = get_all_folders()
    sub_folders = [f for f in all_folders if f.startswith(branch_path + "\\") or f == branch_path]
    for sf in sub_folders:
        set_folder_category(sf, category, "manual-branch")
    build_classification_history()
    logger.info(f"分支分类已传播: {branch_path} -> {category}, 影响 {len(sub_folders)} 个子文件夹")
    return len(sub_folders)


def find_similar_photos_in_folder(target_file_id, folder_path):
    import random as _random

    with _db.connect() as conn:
        target = conn.execute(
            "SELECT f.id, f.file_name, f.folder_name, pm.date_taken "
            "FROM files f LEFT JOIN photo_metadata pm ON f.id = pm.file_id WHERE f.id = ?",
            (target_file_id,)
        ).fetchone()
        if not target:
            return []

        siblings = conn.execute(
            "SELECT f.id, f.file_name, f.folder_name, pm.date_taken "
            "FROM files f "
            "JOIN folder_categories fc ON f.folder_path = fc.folder_path "
            "LEFT JOIN photo_metadata pm ON f.id = pm.file_id "
            "WHERE f.folder_path = ? AND f.is_image = 1 AND fc.category = ? AND f.id != ? "
            "ORDER BY pm.date_taken, f.file_name",
            (folder_path, CATEGORY_LIFE, target_file_id)
        ).fetchall()

    if len(siblings) < 3:
        return []

    if len(siblings) > 80:
        siblings = _random.sample(siblings, 80)

    target_info = f"ID={target[0]} | 文件:{target[1]} | 文件夹:{target[2]} | 日期:{target[3] or '无'}"
    sibling_lines = []
    for s in siblings:
        sibling_lines.append(f"ID={s[0]} | 文件:{s[1]} | 日期:{s[3] or '无'}")

    sibling_text = "\n".join(sibling_lines)

    prompt = f"""你是照片归类助手。用户要把一张照片从「生活照片」移到其他分类。请分析这张照片的特征，找出同文件夹里与其属于"同一组/同一场景/同一性质"的其他照片。

目标照片：
{target_info}

同文件夹候选照片（已排除目标）：
{sibling_text}

判断标准：
- 文件名是否有共同前缀/编号/模式（如 IMG_30xx 系列）
- 拍摄日期是否相邻（同一天或连续几天）
- 是否明显属于同一主题活动/同一拍摄对象

请返回纯 JSON，包含应该一起移走的照片 ID 列表：
{{"similar_ids": [id1, id2, ...]}}

注意：只返回高度确定属于同一组的照片。如果目标照片特征孤立，返回空列表。"""

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content.strip()
        result = json.loads(text)
        similar_ids = result.get("similar_ids", [])
        if not isinstance(similar_ids, list):
            similar_ids = []
        similar_ids = [int(x) for x in similar_ids if str(x).isdigit()]
        logger.info(f"LLM 相似分析: 目标={target_file_id}, 从{len(siblings)}张中找到{len(similar_ids)}张相似")
        return similar_ids
    except Exception as e:
        logger.warning(f"LLM 相似分析失败: {e}")
        return []


if __name__ == "__main__":
    result = classify_folders()
    print(f"分类完成: 已分类 {result['classified']}, 不确定 {result['unknown']}, 需用户确认 {len(result['needs_user'])}")
