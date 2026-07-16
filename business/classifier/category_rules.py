import os

from config import CATEGORY_LIFE, CATEGORY_SAMPLE


STRONG_LIFE_SOURCE_KEYWORDS = ["mobilebackup", "mobile backup", "moments"]
STRONG_SAMPLE_SOURCE_KEYWORDS = ["电报色图", "nsfw", "nswf"]
STRONG_SAMPLE_SOURCE_COMPONENTS = ["nw"]
STRONG_SAMPLE_FILENAME_PREFIXES = ["jp-"]
STRONG_SAMPLE_FILENAME_LIKE_PATTERNS = [
    "photobook-____-__-__-%",
]
CAMERA_BACKUP_ROOT_COMPONENTS = ["mobilebackup", "mobile backup"]
CAMERA_BACKUP_ALBUM_ROOT_COMPONENTS = ["moments"]
CAMERA_BACKUP_ALBUM_CHILD_COMPONENTS = ["dcim", "camera"]
FORCED_LIFE_PATH_COMPONENT_CHAINS = [("photos", "moments")]
CONFIRMED_SAMPLE_TAG = "category:confirmed-sample"
CONFIRMED_SAMPLE_SOURCE = "manual"
CAMERA_BACKUP_FILENAME_GLOB_PATTERNS = [
    "img_[0-9][0-9][0-9][0-9]*",
    "img[_-][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][_-][0-9][0-9][0-9][0-9][0-9][0-9]*",
    "vid[_-][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][_-][0-9][0-9][0-9][0-9][0-9][0-9]*",
    "pxl[_-][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][_-][0-9][0-9][0-9][0-9][0-9][0-9]*",
    "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][_-][0-9][0-9][0-9][0-9][0-9][0-9]*",
    "originalimage_*_livephoto*",
]
LIFE_SOURCE_WITH_SAMPLE_CHILD_EXCEPTIONS = {
    "胶片成图": ["样片搜集"],
}
FILM_OUTPUT_LIFE_ROOT = "胶片成图"
FILM_OUTPUT_SAMPLE_CHILDREN = ["样片搜集"]

STRONG_LIFE_PRIORITY = 20000
STRONG_SAMPLE_PRIORITY = 10000


def is_same_or_child_path(path, parent):
    p = os.path.normpath(path).replace("\\", "/").rstrip("/")
    base = os.path.normpath(parent).replace("\\", "/").rstrip("/")
    return p == base or p.startswith(base + "/")


def relpath_from_source(folder_path, source_roots=None):
    norm_fp = os.path.normpath(folder_path)
    for source in source_roots or []:
        if not is_same_or_child_path(norm_fp, source):
            continue
        try:
            return os.path.relpath(norm_fp, source), source
        except ValueError:
            continue
    return None, None


def _source_candidates(folder_path, source_roots=None):
    norm_fp = os.path.normpath(folder_path)
    rel, source = relpath_from_source(norm_fp, source_roots)
    candidates = []
    parts = []

    if source:
        source_name = os.path.basename(os.path.normpath(source))
        if source_name:
            source_name = source_name.lower()
            candidates.append(source_name)
            parts.append(source_name)

    if rel and rel != ".":
        rel_parts = [
            part.lower()
            for part in rel.replace("/", os.sep).replace("\\", os.sep).split(os.sep)
            if part
        ]
        parts.extend(rel_parts)
        if rel_parts:
            candidates.append(rel_parts[0])
    else:
        folder_name = os.path.basename(norm_fp)
        if folder_name:
            folder_name = folder_name.lower()
            candidates.append(folder_name)
            parts.append(folder_name)

    return candidates, parts


def is_forced_life_path(folder_path):
    parts = [
        part.lower()
        for part in os.path.normpath(folder_path).replace("\\", "/").split("/")
        if part
    ]
    for chain in FORCED_LIFE_PATH_COMPONENT_CHAINS:
        chain_size = len(chain)
        if any(tuple(parts[index:index + chain_size]) == chain for index in range(len(parts) - chain_size + 1)):
            return True
    return False


def path_keyword_priority(folder_path, keywords, source_roots=None):
    if not keywords:
        return 0

    norm_fp = os.path.normpath(folder_path)
    rel, source = relpath_from_source(norm_fp, source_roots)
    if rel and rel != ".":
        raw_parts = rel.replace("/", os.sep).replace("\\", os.sep).split(os.sep)
    else:
        raw_parts = [os.path.basename(norm_fp)]
    if source:
        source_name = os.path.basename(os.path.normpath(source))
        if source_name:
            raw_parts.insert(0, source_name)

    parts = [part.lower() for part in raw_parts if part]
    best = 0
    for index, part in enumerate(parts):
        if any(kw in part for kw in keywords):
            best = max(best, 100 + index)
    return best


def strong_life_source_priority(folder_path, source_roots=None):
    if is_forced_life_path(folder_path):
        return STRONG_LIFE_PRIORITY
    candidates, parts = _source_candidates(folder_path, source_roots)
    if any(any(kw in candidate for kw in STRONG_LIFE_SOURCE_KEYWORDS) for candidate in candidates):
        return STRONG_LIFE_PRIORITY
    for life_root, sample_children in LIFE_SOURCE_WITH_SAMPLE_CHILD_EXCEPTIONS.items():
        if any(life_root in candidate for candidate in candidates):
            if not any(child in part for child in sample_children for part in parts):
                return STRONG_LIFE_PRIORITY
    return 0


def strong_sample_source_priority(folder_path, source_roots=None):
    candidates, parts = _source_candidates(folder_path, source_roots)
    if any(any(kw in candidate for kw in STRONG_SAMPLE_SOURCE_KEYWORDS) for candidate in candidates):
        return STRONG_SAMPLE_PRIORITY
    if any(part in STRONG_SAMPLE_SOURCE_COMPONENTS for part in parts):
        return STRONG_SAMPLE_PRIORITY
    return 0


def path_text_sql(folder_path_expr="f.folder_path"):
    return f"lower(replace(COALESCE({folder_path_expr}, ''), '\\', '/'))"


def _component_like_sql(path_sql, component):
    return (
        f"{path_sql} LIKE '%/{component}/%' "
        f"OR {path_sql} LIKE '%/{component}'"
    )


def _any_component_like_sql(path_sql, components):
    return "(" + " OR ".join(_component_like_sql(path_sql, component) for component in components) + ")"


def _component_chain_like_sql(path_sql, components):
    chain = "/".join(components)
    return (
        "("
        f"{path_sql} = '{chain}' OR {path_sql} LIKE '{chain}/%' "
        f"OR {path_sql} LIKE '%/{chain}' OR {path_sql} LIKE '%/{chain}/%'"
        ")"
    )


def forced_life_path_sql(folder_path_expr="f.folder_path"):
    path_sql = path_text_sql(folder_path_expr)
    return "(" + " OR ".join(
        _component_chain_like_sql(path_sql, chain)
        for chain in FORCED_LIFE_PATH_COMPONENT_CHAINS
    ) + ")"


def strong_life_source_sql(folder_path_expr="f.folder_path"):
    path_sql = path_text_sql(folder_path_expr)
    parts = [_component_like_sql(path_sql, kw) for kw in STRONG_LIFE_SOURCE_KEYWORDS]
    for life_root, sample_children in LIFE_SOURCE_WITH_SAMPLE_CHILD_EXCEPTIONS.items():
        parts.append(
            "("
            + "("
            + _component_like_sql(path_sql, life_root)
            + ")"
            + " AND NOT "
            + _any_component_like_sql(path_sql, sample_children)
            + ")"
        )
    return "(" + " OR ".join(parts) + ")"


def strong_sample_source_sql(folder_path_expr="f.folder_path"):
    path_sql = path_text_sql(folder_path_expr)
    parts = [_component_like_sql(path_sql, kw) for kw in STRONG_SAMPLE_SOURCE_KEYWORDS]
    parts.extend(_component_like_sql(path_sql, component) for component in STRONG_SAMPLE_SOURCE_COMPONENTS)
    return "(" + " OR ".join(parts) + ")"


def strong_sample_filename_sql(file_name_expr="f.file_name"):
    name_sql = f"lower(COALESCE({file_name_expr}, ''))"
    parts = []
    for prefix in STRONG_SAMPLE_FILENAME_PREFIXES:
        # Conservative photobook/site export pattern:
        # JP-Model-Name-Title-or-CJK-Series-Number.jpg
        parts.append(f"{name_sql} LIKE '{prefix}%-%-%-%'")
    parts.extend(f"{name_sql} LIKE '{pattern}'" for pattern in STRONG_SAMPLE_FILENAME_LIKE_PATTERNS)
    return "(" + " OR ".join(parts) + ")"


def camera_backup_source_sql(folder_path_expr="f.folder_path"):
    path_sql = path_text_sql(folder_path_expr)
    direct_backup = _any_component_like_sql(path_sql, CAMERA_BACKUP_ROOT_COMPONENTS)
    album_roots = _any_component_like_sql(path_sql, CAMERA_BACKUP_ALBUM_ROOT_COMPONENTS)
    album_children = _any_component_like_sql(path_sql, CAMERA_BACKUP_ALBUM_CHILD_COMPONENTS)
    return "(" + direct_backup + " OR (" + album_roots + " AND " + album_children + ")" + ")"


def camera_backup_filename_sql(file_name_expr="f.file_name"):
    name_sql = f"lower(COALESCE({file_name_expr}, ''))"
    return "(" + " OR ".join(f"{name_sql} GLOB '{pattern}'" for pattern in CAMERA_BACKUP_FILENAME_GLOB_PATTERNS) + ")"


def protected_camera_backup_sql(folder_path_expr="f.folder_path", file_name_expr="f.file_name"):
    return (
        "("
        + camera_backup_source_sql(folder_path_expr)
        + " AND "
        + camera_backup_filename_sql(file_name_expr)
        + " AND NOT "
        + strong_sample_filename_sql(file_name_expr)
        + ")"
    )


def protected_film_output_life_sql(folder_path_expr="f.folder_path"):
    path_sql = path_text_sql(folder_path_expr)
    return (
        "("
        + "("
        + _component_like_sql(path_sql, FILM_OUTPUT_LIFE_ROOT)
        + ")"
        + " AND NOT "
        + _any_component_like_sql(path_sql, FILM_OUTPUT_SAMPLE_CHILDREN)
        + ")"
    )


def protected_life_override_sql(folder_path_expr="f.folder_path", file_name_expr="f.file_name"):
    return (
        "("
        + forced_life_path_sql(folder_path_expr)
        + " OR "
        + protected_camera_backup_sql(folder_path_expr, file_name_expr)
        + " OR "
        + protected_film_output_life_sql(folder_path_expr)
        + ")"
    )


def sample_keyword_exists_sql(file_alias="f"):
    return (
        "EXISTS ("
        "SELECT 1 FROM sample_keywords sk "
        "WHERE sk.keyword IS NOT NULL "
        "AND sk.keyword != '' "
        "AND ("
        f"lower(COALESCE({file_alias}.file_name, '')) LIKE '%' || lower(sk.keyword) || '%' "
        f"OR lower(COALESCE({file_alias}.folder_name, '')) LIKE '%' || lower(sk.keyword) || '%' "
        f"OR lower(COALESCE({file_alias}.folder_path, '')) LIKE '%' || lower(sk.keyword) || '%'"
        ")"
        ")"
    )


def confirmed_sample_override_sql(file_alias="f"):
    return (
        "EXISTS ("
        "SELECT 1 FROM photo_tags confirmed_sample "
        f"WHERE confirmed_sample.file_id = {file_alias}.id "
        f"AND confirmed_sample.tag = '{CONFIRMED_SAMPLE_TAG}' "
        f"AND confirmed_sample.source = '{CONFIRMED_SAMPLE_SOURCE}'"
        ")"
    )


def category_match_sql(cat_id, file_alias="f", folder_alias="fc", metadata_alias="pm"):
    sample_keyword_match = sample_keyword_exists_sql(file_alias)
    strong_life_source = strong_life_source_sql(f"{file_alias}.folder_path")
    strong_sample_source = strong_sample_source_sql(f"{file_alias}.folder_path")
    strong_sample_filename = strong_sample_filename_sql(f"{file_alias}.file_name")
    protected_life_override = protected_life_override_sql(f"{file_alias}.folder_path", f"{file_alias}.file_name")
    forced_life_path = forced_life_path_sql(f"{file_alias}.folder_path")
    confirmed_sample_override = confirmed_sample_override_sql(file_alias)
    if cat_id == CATEGORY_SAMPLE:
        base_sample = (
            f"({strong_sample_filename} OR {metadata_alias}.category = ? OR (NOT {strong_life_source} AND "
            f"({strong_sample_source} OR "
            f"({metadata_alias}.category IS NULL AND "
            f"(COALESCE({folder_alias}.category, {CATEGORY_LIFE}) = {CATEGORY_SAMPLE} "
            f"OR {sample_keyword_match})))))"
        )
        return (
            f"({confirmed_sample_override} OR ((NOT {forced_life_path}) AND "
            f"((NOT {protected_life_override}) AND {base_sample})))"
        )
    if cat_id == CATEGORY_LIFE:
        base_life = (
            f"({protected_life_override} OR {metadata_alias}.category = ? OR "
            f"(NOT {strong_sample_filename} AND {metadata_alias}.category IS NULL "
            f"AND ({strong_life_source} OR (NOT {strong_sample_source} AND "
            f"(COALESCE({folder_alias}.category, {CATEGORY_LIFE}) = {CATEGORY_LIFE} "
            f"AND NOT {sample_keyword_match})))))"
        )
        return f"((NOT {confirmed_sample_override}) AND ({forced_life_path} OR {base_life}))"
    return f"{metadata_alias}.category = ?"


def category_match_without_folder_sql(cat_id, file_alias="f", metadata_alias="pm"):
    sample_keyword_match = sample_keyword_exists_sql(file_alias)
    strong_life_source = strong_life_source_sql(f"{file_alias}.folder_path")
    strong_sample_source = strong_sample_source_sql(f"{file_alias}.folder_path")
    strong_sample_filename = strong_sample_filename_sql(f"{file_alias}.file_name")
    protected_life_override = protected_life_override_sql(f"{file_alias}.folder_path", f"{file_alias}.file_name")
    forced_life_path = forced_life_path_sql(f"{file_alias}.folder_path")
    confirmed_sample_override = confirmed_sample_override_sql(file_alias)
    if cat_id == CATEGORY_SAMPLE:
        base_sample = (
            f"({strong_sample_filename} OR {metadata_alias}.category = {CATEGORY_SAMPLE} OR "
            f"(NOT {strong_life_source} AND "
            f"({strong_sample_source} OR "
            f"({metadata_alias}.category IS NULL AND {sample_keyword_match}))))"
        )
        return (
            f"({confirmed_sample_override} OR ((NOT {forced_life_path}) AND "
            f"((NOT {protected_life_override}) AND {base_sample})))"
        )
    if cat_id == CATEGORY_LIFE:
        base_life = (
            f"({protected_life_override} OR {metadata_alias}.category = {CATEGORY_LIFE} OR "
            f"(NOT {strong_sample_filename} AND "
            f"{metadata_alias}.category IS NULL AND ({strong_life_source} OR "
            f"(NOT {strong_sample_source} AND NOT {sample_keyword_match}))))"
        )
        return f"((NOT {confirmed_sample_override}) AND ({forced_life_path} OR {base_life}))"
    return "1 = 0"
