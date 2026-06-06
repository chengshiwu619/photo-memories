import os
import sqlite3
import json
import hashlib

from logger_setup import logger
from config import (
    CATEGORY_LIFE,
    CATEGORY_SAMPLE,
    CATEGORY_NAMES,
    get_settings,
)
from db_manager import Database

_db = Database()

MAX_USER_CLASSIFY = 10
CLASSIFIER_VERSION = "folder-classifier-v2"
PROMPT_VERSION = "folder-prompt-v2"

_SAMPLE_KEYWORDS = [
    "graphis", "g-area", "image.tv", "pure japan", "rq-star",
    "dmm", "fanza",
    "weekly playboy", "プレイボーイ",
    "flash", "フラッシュ",
    "friday", "フライデー",
    "ex大衆", "ex taishu",
    "sabra", "サブラ",
    "bubka", "ブブカ",
    "young jump", "ヤングジャンプ", "週刊ヤングジャンプ",
    "young magazine", "ヤングマガジン",
    "young champion", "ヤングチャンピオン",
    "young animal", "ヤングアニマル",
    "shonen sunday", "少年サンデー", "週刊少年サンデー",
    "big comic spirits", "ビッグコミックスピリッツ",
    "s1", "s1no.1style", "sod", "sodcreate",
    "faleno", "moodyz", "ideapocket", "アイポケ",
    "maxing", "kmp", "prestige",
    "caribbeancom", "加勒比", "一本道", "1pondo",
    "tokyo hot", "東京热", "天然むすめ",
    "muku", "無垢",
    "dogma", "abyss",
    "attackers",
    "venus",
    "kawaii", "エスワン",
    "das", "honnaka", "本中",
    "nampa", "ナンパ",
    "miman", "未満",
    "gra_", "cosplay", "コスプレ",
    "写真集", "写真館",
    "gravure", "グラビア",
    "idol", "アイドル",
    "av", "jav",
    "希威社", "xiweisha", "色图",
]
_LIFE_KEYWORDS = [
    "apple", "iphone", "ipad",
    "samsung", "galaxy", "sm-g", "sm-s", "sm-n", "sm-a", "sm-m", "sm-f",
    "huawei", "华为", "pura", "hwa",
    "xiaomi", "小米", "redmi", "mi ", "pocophone", "poco",
    "oppo", "vivo", "iqoo", "cph", "v23",
    "honor", "荣耀",
    "google pixel",
    "sony xperia", "xperia", "xq-",
    "oneplus", "一加",
    "motorola", "moto",
    "nokia",
    "realme", "rmx",
    "meizu", "魅族",
    "zte", "中兴",
    "lenovo", "联想",
    "asus", "rog phone",
    "wechat", "微信", "weixin",
    "screenshot", "截图",
    "dcim", "camera",
]


def _get_all_sample_keywords():
    keywords = list(_SAMPLE_KEYWORDS)
    try:
        with _db.connect() as conn:
            rows = conn.execute("SELECT keyword FROM sample_keywords ORDER BY id").fetchall()
        for row in rows:
            kw = row[0].lower().strip()
            if kw and kw not in keywords:
                keywords.append(kw)
    except Exception:
        pass
    return keywords


def _get_all_life_keywords():
    keywords = list(_LIFE_KEYWORDS)
    try:
        with _db.connect() as conn:
            rows = conn.execute("SELECT keyword FROM life_keywords ORDER BY id").fetchall()
        for row in rows:
            kw = row[0].lower().strip()
            if kw and kw not in keywords:
                keywords.append(kw)
    except Exception:
        pass
    return keywords


def _match_sample_keyword(name):
    lower = name.lower()
    for kw in _get_all_sample_keywords():
        if kw in lower:
            return True
    return False


def _match_life_keyword(name):
    lower = name.lower()
    for kw in _get_all_life_keywords():
        if kw in lower:
            return True
    return False


def _path_like_patterns(folder_path):
    norm = os.path.normpath(folder_path)
    slash = norm.replace("\\", "/")
    backslash = norm.replace("/", "\\")
    return [slash, slash + "/%", backslash, backslash + "\\%"]


def _is_same_or_child_path(path, parent):
    p = os.path.normpath(path).replace("\\", "/").rstrip("/")
    base = os.path.normpath(parent).replace("\\", "/").rstrip("/")
    return p == base or p.startswith(base + "/")


def _get_source_roots():
    settings = get_settings()
    roots = []
    for source in getattr(settings, "source_dirs", None) or []:
        if source:
            roots.append(os.path.normpath(source))
    if not roots and getattr(settings, "source_drive", ""):
        roots.append(os.path.normpath(settings.source_drive))

    deduped = []
    seen = set()
    for root in roots:
        key = root.replace("\\", "/").rstrip("/").lower()
        if key and key not in seen:
            deduped.append(root)
            seen.add(key)
    return deduped


def _relpath_from_source(folder_path, source_roots=None):
    norm_fp = os.path.normpath(folder_path)
    for source in source_roots or _get_source_roots():
        if not _is_same_or_child_path(norm_fp, source):
            continue
        try:
            return os.path.relpath(norm_fp, source), source
        except ValueError:
            continue
    return None, None


def _has_date_path_pattern(folder_path):
    import re
    parts = folder_path.replace("/", os.sep).replace("\\", os.sep).split(os.sep)
    for i in range(len(parts) - 1):
        if re.match(r"^(20[0-9]{2})$", parts[i]) and re.match(r"^(0[1-9]|1[0-2])$", parts[i + 1]):
            return True
    return False


def get_sample_keywords():
    builtin = list(_SAMPLE_KEYWORDS)
    try:
        with _db.connect() as conn:
            rows = conn.execute("SELECT keyword FROM sample_keywords ORDER BY id").fetchall()
        custom = [row[0] for row in rows]
    except Exception:
        custom = []
    return builtin, custom


def add_sample_keyword(keyword):
    kw = keyword.strip()
    if not kw:
        return False
    try:
        with _db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO sample_keywords (keyword) VALUES (?)", (kw,))
        apply_keyword_to_existing_folders(kw, CATEGORY_SAMPLE, "keyword-custom")
        logger.info(f"添加样片关键词: {kw}")
        return True
    except Exception as e:
        logger.error(f"添加关键词失败: {e}")
        return False


def remove_sample_keyword(keyword):
    kw = keyword.strip()
    if not kw:
        return False
    try:
        with _db.connect() as conn:
            conn.execute("DELETE FROM sample_keywords WHERE keyword = ?", (kw,))
        logger.info(f"移除样片关键词: {kw}")
        return True
    except Exception as e:
        logger.error(f"移除关键词失败: {e}")
        return False


def get_life_keywords():
    builtin = list(_LIFE_KEYWORDS)
    try:
        with _db.connect() as conn:
            rows = conn.execute("SELECT keyword FROM life_keywords ORDER BY id").fetchall()
        custom = [row[0] for row in rows]
    except Exception:
        custom = []
    return builtin, custom


def add_life_keyword(keyword):
    kw = keyword.strip()
    if not kw:
        return False
    try:
        with _db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO life_keywords (keyword) VALUES (?)", (kw,))
        apply_keyword_to_existing_folders(kw, CATEGORY_LIFE, "keyword-custom")
        logger.info(f"添加生活关键词: {kw}")
        return True
    except Exception as e:
        logger.error(f"添加关键词失败: {e}")
        return False


def remove_life_keyword(keyword):
    kw = keyword.strip()
    if not kw:
        return False
    try:
        with _db.connect() as conn:
            conn.execute("DELETE FROM life_keywords WHERE keyword = ?", (kw,))
        logger.info(f"移除生活关键词: {kw}")
        return True
    except Exception as e:
        logger.error(f"移除关键词失败: {e}")
        return False


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

    source_roots = _get_source_roots()
    branches = set()
    for fp in all_folders:
        rel, source = _relpath_from_source(fp, source_roots)
        if not rel or rel == '.':
            continue
        parts = rel.split(os.sep)
        branch = parts[0]
        branches.add(os.path.join(source, branch))

    result = sorted(branches)
    logger.info(f"从 {len(all_folders)} 个文件夹中提取 {len(result)} 个顶层分支")
    return result


def _folder_row_to_dict(row):
    if not row:
        return None
    return {key: row[key] for key in row.keys()}


def _get_folder_category_row(folder_path):
    with _db.connect() as conn:
        row = conn.execute(
            """SELECT folder_path, category, confidence, classified_at, fingerprint,
                      classifier_version, prompt_version, status, error
               FROM folder_categories WHERE folder_path = ?""",
            (folder_path,),
        ).fetchone()
    return _folder_row_to_dict(row)


def _is_manual_confidence(confidence):
    return bool(confidence and "manual" in confidence)


def build_folder_fingerprint(folder_path):
    norm_path = os.path.normpath(folder_path)
    like_path = norm_path + os.sep + "%"
    alt_like_path = norm_path.replace("\\", "/") + "/%"
    with _db.connect() as conn:
        rows = conn.execute(
            """
            SELECT file_name, folder_path, file_size, file_mtime
            FROM files
            WHERE folder_path = ? OR folder_path LIKE ? OR replace(folder_path, '\\', '/') LIKE ?
            ORDER BY folder_path, file_name
            """,
            (norm_path, like_path, alt_like_path),
        ).fetchall()

    media_count = len(rows)
    child_folders = {os.path.normpath(row["folder_path"]) for row in rows if os.path.normpath(row["folder_path"]) != norm_path}
    sample_names = [row["file_name"] or "" for row in rows[:20]]
    latest_mtime = max((row["file_mtime"] or "" for row in rows), default="")
    sample_payload = "\n".join(sample_names)
    sample_hash = hashlib.sha1(sample_payload.encode("utf-8", errors="replace")).hexdigest()
    payload = {
        "folder_path": norm_path,
        "media_count": media_count,
        "child_count": len(child_folders),
        "sample_filenames_hash": sample_hash,
        "latest_mtime": latest_mtime,
        "classifier_version": CLASSIFIER_VERSION,
        "prompt_version": PROMPT_VERSION,
    }
    fingerprint = hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    payload["fingerprint"] = fingerprint
    payload["sample_filenames"] = sample_names[:10]
    return payload


def _fingerprint_is_current(row, fingerprint_info):
    if not row:
        return False
    if row.get("fingerprint") != fingerprint_info["fingerprint"]:
        return False
    if row.get("classifier_version") != CLASSIFIER_VERSION:
        return False
    if row.get("prompt_version") != PROMPT_VERSION:
        return False
    return row.get("status") == "ok"


def _backfill_fingerprint_if_trusted(folder_path, row, fingerprint_info):
    if not row:
        return False
    if row.get("fingerprint"):
        return False
    if row.get("category") not in (CATEGORY_LIFE, CATEGORY_SAMPLE):
        return False
    status = row.get("status") or "ok"
    confidence = row.get("confidence") or ""
    if status in {"pending", "error"} or "pending" in confidence or "error" in confidence:
        return False
    set_folder_category(
        folder_path,
        row["category"],
        confidence,
        fingerprint=fingerprint_info["fingerprint"],
        status="ok",
    )
    return True


def set_folder_category(
    folder_path,
    category,
    confidence=None,
    fingerprint=None,
    status="ok",
    error=None,
    classifier_version=CLASSIFIER_VERSION,
    prompt_version=PROMPT_VERSION,
):
    with _db.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO folder_categories
               (folder_path, category, confidence, classified_at, fingerprint,
                classifier_version, prompt_version, status, error)
               VALUES (?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)""",
            (
                folder_path,
                category,
                confidence,
                fingerprint,
                classifier_version,
                prompt_version,
                status,
                error,
            ),
        )


def get_folder_category(folder_path):
    with _db.connect() as conn:
        row = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?", (folder_path,)
        ).fetchone()
    return row[0] if row else None


def apply_keyword_to_existing_folders(keyword, category, confidence="keyword-custom"):
    kw = (keyword or "").strip().lower()
    if not kw:
        return 0

    changes = {}
    old_categories = {}
    with _db.connect() as conn:
        rows = conn.execute("""
            SELECT DISTINCT f.folder_path, fc.category, fc.confidence
            FROM files f
            LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
            WHERE f.is_image = 1
              AND (
                  lower(f.folder_path) LIKE ?
                  OR lower(f.file_name) LIKE ?
              )
        """, (f"%{kw}%", f"%{kw}%")).fetchall()

    for folder_path, old_cat, old_conf in rows:
        if old_conf and "manual" in old_conf:
            continue
        if old_cat == category:
            continue
        changes[folder_path] = category
        old_categories[folder_path] = old_cat

    for folder_path in changes:
        set_folder_category(folder_path, category, confidence)

    if changes:
        build_classification_history()
        _cleanup_stale_category_data(changes, old_categories)
        logger.info(f"关键词立即应用: {keyword} -> {category}, 影响 {len(changes)} 个文件夹")

    return len(changes)


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

    _hist_file = get_settings().classification_history_file
    with open(_hist_file, "w", encoding="utf-8") as f:
        f.write(text)

    logger.info(f"分类历史已写入 {_hist_file}: {len(rows)} 条")
    return text


def _load_history_context():
    _hist_file = get_settings().classification_history_file
    if os.path.exists(_hist_file):
        with open(_hist_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return f"""

以下是已确认分类的历史记录，请作为参考：
{content}
"""
    return ""


def classify_branches_with_llm(branch_info):
    lines = []
    for i, (name, samples) in enumerate(branch_info):
        line = f"{i+1}. {name}"
        if samples:
            line += f" ({', '.join(samples)})"
        lines.append(line)
    branches_text = "\n".join(lines)
    history = _load_history_context()

    prompt = f"""照片文件夹分类。根据序号、分支名和示例判断。
1=生活 2=样片 0=不确定
只返回JSON数组，按顺序填1/2/0，不要解释。
{history}
{branches_text}

返回: {{"c":[1,2,0,...]}}"""

    for attempt in range(2):
        try:
            from infra.llm.client import get_llm_client
            llm = get_llm_client()
            response = llm.chat(
                model=get_settings().deepseek_classify_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1024,
            )
            result_text = response.choices[0].message.content.strip()
            if not result_text:
                logger.warning(f"LLM 返回空内容，尝试 {attempt+1}/2")
                continue
            parsed = json.loads(result_text)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
            if not isinstance(parsed, dict):
                logger.warning(f"LLM 返回非dict类型({type(parsed).__name__}), 尝试 {attempt+1}/2")
                continue
            categories = parsed.get("c", [])
            result = {}
            for i, (name, _) in enumerate(branch_info):
                if i < len(categories):
                    try:
                        result[name] = int(categories[i])
                    except (ValueError, TypeError):
                        result[name] = 0
                else:
                    result[name] = 0
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"LLM JSON解析失败(尝试 {attempt+1}/2): {e}, 原文: {result_text[:200] if result_text else 'empty'}")
        except Exception as e:
            logger.error(f"LLM 分类出错(尝试 {attempt+1}/2): {e}")
    return {}


def classify_folders(progress_callback=None):
    from db_manager import Database
    db = Database()
    db.init_tables()

    unclassified = get_unclassified_folders()
    if not unclassified:
        logger.info("没有未分类文件夹，继续检查 fingerprint 是否变化")

    build_classification_history()

    branches = _get_branch_folders()
    if not branches:
        return {"classified": 0, "unknown": 0, "skipped": 0, "llm_queued": 0, "needs_user": []}

    branch_names = [os.path.basename(b) for b in branches]

    sample_branches = []
    life_branches = []
    llm_branches = []
    llm_branch_names = []
    llm_fingerprints = {}
    skipped_count = 0
    for bp, bn in zip(branches, branch_names):
        if _match_sample_keyword(bn):
            sample_branches.append((bp, bn))
        elif _match_life_keyword(bn):
            life_branches.append((bp, bn))
        else:
            fp_info = build_folder_fingerprint(bp)
            current = _get_folder_category_row(bp)
            if current and _is_manual_confidence(current.get("confidence")):
                if not current.get("fingerprint"):
                    set_folder_category(
                        bp,
                        current["category"],
                        current.get("confidence"),
                        fingerprint=fp_info["fingerprint"],
                        status="ok",
                    )
                skipped_count += 1
                continue
            if _backfill_fingerprint_if_trusted(bp, current, fp_info):
                skipped_count += 1
                continue
            if _fingerprint_is_current(current, fp_info):
                skipped_count += 1
                continue
            llm_branches.append(bp)
            llm_branch_names.append(bn)
            llm_fingerprints[bp] = fp_info

    classified_count = 0
    if sample_branches:
        for bp, bn in sample_branches:
            set_folder_category(bp, CATEGORY_SAMPLE, "keyword-branch", fingerprint=build_folder_fingerprint(bp)["fingerprint"])
            sub_folders = [f for f in unclassified if _is_same_or_child_path(f, bp)]
            for sf in sub_folders:
                set_folder_category(sf, CATEGORY_SAMPLE, "keyword", fingerprint=build_folder_fingerprint(sf)["fingerprint"])
                classified_count += 1
        logger.info(f"样片关键词预分类: {len(sample_branches)} 个分支归为样片")

    if life_branches:
        for bp, bn in life_branches:
            set_folder_category(bp, CATEGORY_LIFE, "keyword-branch", fingerprint=build_folder_fingerprint(bp)["fingerprint"])
            sub_folders = [f for f in unclassified if _is_same_or_child_path(f, bp)]
            for sf in sub_folders:
                set_folder_category(sf, CATEGORY_LIFE, "keyword", fingerprint=build_folder_fingerprint(sf)["fingerprint"])
                classified_count += 1
        logger.info(f"生活关键词预分类: {len(life_branches)} 个分支归为生活")

    if not llm_branches:
        build_classification_history()
        return {"classified": classified_count, "unknown": 0, "skipped": skipped_count, "llm_queued": 0, "needs_user": []}

    branch_samples = {}
    try:
        with _db.connect() as conn:
            conditions = []
            params = []
            for bp in llm_branches:
                conditions.append("(folder_path = ? OR folder_path LIKE ?)")
                params.extend([bp, bp + os.sep + "%"])
            where_clause = " OR ".join(conditions)
            rows = conn.execute(
                f"SELECT file_name, folder_path FROM files WHERE ({where_clause}) AND is_image = 1",
                params
            ).fetchall()

        for bp in llm_branches:
            bp_norm = os.path.normpath(bp)
            bp_files = [(fn, fp) for fn, fp in rows if _is_same_or_child_path(fp, bp)]
            samples = []
            seen_sub = set()
            for fn, fp in bp_files:
                rel = os.path.relpath(os.path.normpath(fp), bp_norm)
                sub = rel.split(os.sep)[0] if os.sep in rel else ""
                if sub and sub not in seen_sub:
                    samples.append(sub)
                    seen_sub.add(sub)
                if len(seen_sub) >= 5:
                    break
            remaining = 10 - len(samples)
            if remaining > 0:
                for fn, fp in bp_files:
                    if fn not in samples:
                        name_no_ext = os.path.splitext(fn)[0]
                        if len(name_no_ext) > 30:
                            name_no_ext = name_no_ext[:30] + "..."
                        samples.append(name_no_ext)
                    if len(samples) >= 10:
                        break
            branch_samples[os.path.basename(bp)] = samples[:10]
    except Exception as e:
        logger.warning(f"采样文件信息失败: {e}")

    llm_branch_info = [(bn, branch_samples.get(bn, [])) for bn in llm_branch_names]

    logger.info(f"LLM 分类 {len(llm_branches)} 个顶层分支, fingerprint 跳过 {skipped_count} 个")
    if progress_callback:
        progress_callback(0, len(llm_branches))

    result = classify_branches_with_llm(llm_branch_info)
    if not result:
        logger.warning("LLM 分类返回空结果，标记待处理但不阻塞主界面")
        for branch_path in llm_branches:
            existing_row = _get_folder_category_row(branch_path)
            keep_category = existing_row["category"] if existing_row else CATEGORY_LIFE
            set_folder_category(
                branch_path,
                keep_category,
                "llm-error-pending",
                fingerprint=llm_fingerprints[branch_path]["fingerprint"],
                status="error",
                error="llm_empty_result",
            )
            sub_folders = [f for f in unclassified if _is_same_or_child_path(f, branch_path)]
            for sf in sub_folders:
                sf_fp = build_folder_fingerprint(sf)
                set_folder_category(
                    sf,
                    keep_category,
                    "llm-error-pending",
                    fingerprint=sf_fp["fingerprint"],
                    status="error",
                    error="llm_empty_result",
                )
        build_classification_history()
        return {
            "classified": classified_count,
            "unknown": len(llm_branches),
            "skipped": skipped_count,
            "llm_queued": len(llm_branches),
            "needs_user": [],
        }

    unknown_branches = []

    for branch_path, branch_name in zip(llm_branches, llm_branch_names):
        category = result.get(branch_name, 0)
        try:
            category = int(category)
        except (ValueError, TypeError):
            category = 0

        sub_folders = [f for f in unclassified if _is_same_or_child_path(f, branch_path)]

        if category in (1, 2):
            set_folder_category(
                branch_path,
                category,
                "llm-branch",
                fingerprint=llm_fingerprints[branch_path]["fingerprint"],
            )
            for sf in sub_folders:
                set_folder_category(sf, category, "llm-branch", fingerprint=build_folder_fingerprint(sf)["fingerprint"])
                classified_count += 1
        else:
            unknown_branches.append(branch_path)

    if progress_callback:
        progress_callback(len(llm_branches), len(llm_branches))

    unknown_count = len(unknown_branches)
    needs_user = unknown_branches[:MAX_USER_CLASSIFY]

    for branch_path in unknown_branches:
        set_folder_category(
            branch_path,
            CATEGORY_LIFE,
            "default-pending-refine",
            fingerprint=llm_fingerprints[branch_path]["fingerprint"],
            status="pending",
        )
        sub_folders = [f for f in unclassified if _is_same_or_child_path(f, branch_path)]
        for sf in sub_folders:
            set_folder_category(
                sf,
                CATEGORY_LIFE,
                "default-pending-refine",
                fingerprint=build_folder_fingerprint(sf)["fingerprint"],
                status="pending",
            )
            classified_count += 1

    build_classification_history()

    logger.info(
        f"分类完成: 已分类 {classified_count} 个子文件夹, 不确定 {unknown_count} 个分支, "
        f"fingerprint 跳过 {skipped_count}, LLM 队列 {len(llm_branches)}, 需用户确认 {len(needs_user)}"
    )
    return {
        "classified": classified_count,
        "unknown": unknown_count,
        "skipped": skipped_count,
        "llm_queued": len(llm_branches),
        "needs_user": needs_user,
    }


def _cleanup_stale_category_data(changes, old_categories):
    cleanup_items = []
    for folder_path, new_cat in changes.items():
        old_cat = old_categories.get(folder_path)
        if old_cat is not None and old_cat != new_cat:
            cleanup_items.append((folder_path, old_cat))

    if not cleanup_items:
        return

    try:
        changed_file_ids = set()
        with _db.connect() as conn:
            for folder_path, _old_cat in cleanup_items:
                patterns = _path_like_patterns(folder_path)
                rows = conn.execute(
                    f"SELECT id FROM files WHERE folder_path = ? OR folder_path LIKE ? OR folder_path = ? OR folder_path LIKE ?",
                    patterns,
                ).fetchall()
                for (fid,) in rows:
                    changed_file_ids.add(fid)

        if not changed_file_ids:
            return

        old_cats = {old_cat for _, old_cat in cleanup_items}

        with _db.connect() as conn:
            for old_cat in old_cats:
                mem_rows = conn.execute(
                    "SELECT id, photo_ids FROM memories WHERE category = ?",
                    (old_cat,),
                ).fetchall()
                mem_changed = 0
                mem_deleted = 0
                photo_refs_removed = 0
                for memory_id, photo_ids_text in mem_rows:
                    try:
                        ids = json.loads(photo_ids_text)
                    except Exception:
                        continue
                    kept = []
                    removed = 0
                    for pid in ids:
                        try:
                            if int(pid) in changed_file_ids:
                                removed += 1
                            else:
                                kept.append(pid)
                        except (ValueError, TypeError):
                            kept.append(pid)
                    if removed:
                        photo_refs_removed += removed
                        if kept:
                            conn.execute(
                                "UPDATE memories SET photo_ids = ? WHERE id = ?",
                                (json.dumps(kept, ensure_ascii=False), memory_id),
                            )
                            mem_changed += 1
                        else:
                            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                            mem_deleted += 1

                file_id_list = sorted(changed_file_ids)
                batch_size = 900
                shown_deleted = 0
                clicks_deleted = 0
                for i in range(0, len(file_id_list), batch_size):
                    batch = file_id_list[i : i + batch_size]
                    placeholders = ",".join("?" * len(batch))
                    shown_deleted += conn.execute(
                        f"DELETE FROM photo_shown_history WHERE category = ? AND file_id IN ({placeholders})",
                        [old_cat] + batch,
                    ).rowcount
                    clicks_deleted += conn.execute(
                        f"DELETE FROM click_history WHERE category = ? AND file_id IN ({placeholders})",
                        [old_cat] + batch,
                    ).rowcount

        logger.info(
            f"分类变更一致性清理: {len(changed_file_ids)} 个文件, "
            f"memories 更新{mem_changed}/删除{mem_deleted}/引用移除{photo_refs_removed}, "
            f"展示历史删除{shown_deleted}, 点击历史删除{clicks_deleted}"
        )
    except Exception as e:
        logger.error(f"分类变更一致性清理出错: {e}")


def refine_sample_keywords():
    PRIOR_PATH = 1
    PRIOR_FILENAME = 2
    PRIOR_EXIF = 3
    PRIOR_CONTENT = 4
    PRIOR_BRANCH = 5

    refined = 0
    try:
        sample_kws = _get_all_sample_keywords()
        life_kws = _get_all_life_keywords()
        if not sample_kws and not life_kws:
            return 0

        changes = {}

        with _db.connect() as conn:
            classified = conn.execute(
                "SELECT folder_path, category, confidence FROM folder_categories"
            ).fetchall()
            classified_map = {}
            for fp, cat, conf in classified:
                classified_map[fp] = (cat, conf)

        with _db.connect() as conn:
            all_distinct = conn.execute(
                "SELECT DISTINCT folder_path FROM files WHERE is_image = 1"
            ).fetchall()

        all_folders = []
        for (fp,) in all_distinct:
            entry = classified_map.get(fp)
            if entry:
                all_folders.append((fp, entry[0], entry[1]))
            else:
                all_folders.append((fp, None, None))

        if not all_folders:
            return 0

        with _db.connect() as conn:
            file_rows = conn.execute("""
                SELECT f.folder_path, f.file_name, pm.camera_model, pm.exif_json
                FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1
            """).fetchall()

        folder_info = {}
        for fp, fn, cam, exif_j in file_rows:
            folder_info.setdefault(fp, {"file_names": [], "camera_models": set(), "exif_texts": []})
            folder_info[fp]["file_names"].append(fn)
            if cam:
                folder_info[fp]["camera_models"].add(cam.lower())
            if exif_j:
                try:
                    exif_data = json.loads(exif_j)
                    for v in exif_data.values():
                        folder_info[fp]["exif_texts"].append(str(v).lower())
                except (json.JSONDecodeError, TypeError):
                    folder_info[fp]["exif_texts"].append(exif_j.lower())

        source_roots = _get_source_roots()

        branch_cat_map = {}
        for fp, (cat, conf) in classified_map.items():
            rel, _source = _relpath_from_source(fp, source_roots)
            if rel and (rel == '.' or os.sep not in rel):
                branch_cat_map[os.path.basename(os.path.normpath(fp)).lower()] = (cat, conf)

        for folder_path, current_cat, current_conf in all_folders:
            if current_conf and "manual" in current_conf:
                continue

            info = folder_info.get(folder_path)
            if not info:
                continue

            sample_priority = 0
            life_priority = 0

            folder_name = os.path.basename(folder_path).lower()
            parts = folder_path.replace("/", os.sep).replace("\\", os.sep).split(os.sep)

            norm_fp = os.path.normpath(folder_path)
            rel, _source = _relpath_from_source(norm_fp, source_roots)
            branch_name = rel.split(os.sep)[0].lower() if rel and rel != '.' else folder_name

            if sample_kws:
                if any(kw in branch_name for kw in sample_kws):
                    sample_priority = max(sample_priority, PRIOR_BRANCH)
                elif any(kw in folder_name for kw in sample_kws):
                    sample_priority = max(sample_priority, PRIOR_PATH)
                for part in parts:
                    if any(kw in part.lower() for kw in sample_kws):
                        if sample_priority < PRIOR_PATH:
                            sample_priority = max(sample_priority, PRIOR_PATH)
                        break
                for fn in info["file_names"]:
                    if any(kw in fn.lower() for kw in sample_kws):
                        sample_priority = max(sample_priority, PRIOR_CONTENT)
                        break

            if life_kws:
                if any(kw in branch_name for kw in life_kws):
                    life_priority = max(life_priority, PRIOR_BRANCH)
                elif any(kw in folder_name for kw in life_kws):
                    life_priority = max(life_priority, PRIOR_PATH)
                for part in parts:
                    if any(kw in part.lower() for kw in life_kws):
                        if life_priority < PRIOR_PATH:
                            life_priority = max(life_priority, PRIOR_PATH)
                        break
                for fn in info["file_names"]:
                    if any(kw in fn.lower() for kw in life_kws):
                        life_priority = max(life_priority, PRIOR_FILENAME)
                        break
                for cm in info["camera_models"]:
                    if any(kw in cm for kw in life_kws):
                        life_priority = max(life_priority, PRIOR_EXIF)
                        break
                for et in info["exif_texts"]:
                    if any(kw in et for kw in life_kws):
                        life_priority = max(life_priority, PRIOR_EXIF)
                        break

            if _has_date_path_pattern(folder_path):
                life_priority = max(life_priority, PRIOR_PATH)

            branch_entry = branch_cat_map.get(branch_name)
            if branch_entry:
                b_cat, b_conf = branch_entry
                if b_cat == CATEGORY_SAMPLE and b_conf and ("keyword" in b_conf or "llm" in b_conf):
                    sample_priority = max(sample_priority, PRIOR_BRANCH)
                elif b_cat == CATEGORY_LIFE and b_conf and ("keyword" in b_conf or "llm" in b_conf):
                    life_priority = max(life_priority, PRIOR_BRANCH)

            if sample_priority > life_priority and current_cat != CATEGORY_SAMPLE:
                changes[folder_path] = CATEGORY_SAMPLE
            elif life_priority > sample_priority and current_cat != CATEGORY_LIFE:
                changes[folder_path] = CATEGORY_LIFE
            elif sample_priority > 0 and life_priority > 0 and sample_priority == life_priority:
                if current_cat != CATEGORY_SAMPLE:
                    changes[folder_path] = CATEGORY_SAMPLE
            elif sample_priority == 0 and life_priority == 0 and current_cat is None:
                changes[folder_path] = CATEGORY_LIFE

        old_categories = {}
        for fp in changes:
            entry = classified_map.get(fp)
            old_categories[fp] = entry[0] if entry else None

        for fp, cat in changes.items():
            set_folder_category(fp, cat, "keyword-refine")
            refined += 1

        if changes:
            build_classification_history()
            _cleanup_stale_category_data(changes, old_categories)

        to_sample = sum(1 for c in changes.values() if c == CATEGORY_SAMPLE)
        to_life = sum(1 for c in changes.values() if c == CATEGORY_LIFE)
        logger.info(f"后台关键词精分类完成: {refined} 个文件夹重新分类 (→样片 {to_sample}, →生活 {to_life})")
    except Exception as e:
        logger.error(f"后台关键词精分类出错: {e}")

    return refined


def propagate_branch_category(branch_path, category):
    all_folders = get_all_folders()
    sub_folders = [f for f in all_folders if _is_same_or_child_path(f, branch_path)]
    for sf in sub_folders:
        set_folder_category(sf, category, "manual-branch")
    build_classification_history()
    logger.info(f"分支分类已传播: {branch_path} -> {category}, 影响 {len(sub_folders)} 个子文件夹")
    return len(sub_folders)
