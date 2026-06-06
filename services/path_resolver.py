"""
统一路径规范化与路径健康检查模块。

职责：
- 规范化路径格式（slash/backslash、UNC、多余引号空白）
- 检测损坏路径（??、�、NUL）
- 检查路径是否在配置的 source_drive/photo root 下
- stat 文件获取 size/mtime，失败不抛异常
- 计算 canonical_key 用于去重/匹配

约束：
- 不删除、移动、重命名、修改原图
- 不覆盖旧 path 字段
- 不把 ?? 自动替换成猜测字符
- canonical_key 只用于去重和匹配，不替代用户可见路径
"""

import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PathStatus(str, Enum):
    OK = "ok"
    OUTSIDE_ROOT = "outside_root"
    DAMAGED_PATH = "damaged_path"
    MISSING = "missing"
    STAT_FAILED = "stat_failed"
    UNSUPPORTED_EXT = "unsupported_ext"


HEALTHY_STATUSES = frozenset({PathStatus.OK})
DISPLAYABLE_STATUSES = frozenset({PathStatus.OK})
# damaged/missing/stat_failed/outside_root 都不可展示
NON_DISPLAYABLE_STATUSES = frozenset({
    PathStatus.OUTSIDE_ROOT,
    PathStatus.DAMAGED_PATH,
    PathStatus.MISSING,
    PathStatus.STAT_FAILED,
    PathStatus.UNSUPPORTED_EXT,
})


@dataclass
class PathResolveResult:
    """统一路径解析结果。

    字段说明：
    - raw_path: 外部来源原始路径
    - normalized_path: 规范化后的展示/访问路径
    - canonical_key: 用于 DB 去重/比较的稳定 key（大小写不敏感）
    - source_root: 匹配到的照片根目录
    - status: ok / outside_root / damaged_path / missing / stat_failed / unsupported_ext
    - reason: 错误原因（status 非 ok 时有值）
    - file_size: 文件大小（stat 成功时）
    - file_mtime: 文件修改时间 ISO 字符串（stat 成功时）
    - is_media: 是否是支持的媒体扩展名
    """
    raw_path: str = ""
    normalized_path: str = ""
    canonical_key: str = ""
    source_root: str = ""
    status: PathStatus = PathStatus.OK
    reason: str = ""
    file_size: Optional[int] = None
    file_mtime: Optional[str] = None
    is_media: bool = False

    def is_healthy(self) -> bool:
        return self.status in HEALTHY_STATUSES

    def is_displayable(self) -> bool:
        return self.status in DISPLAYABLE_STATUSES


# ---- 损坏字符检测 ----

_DAMAGED_CHARS = frozenset({"\ufffd", "\x00"})
_DAMAGED_SUBSTRINGS = ("??",)  # 路径中出现 ?? 视为损坏（不猜测替换）


def _has_damaged_chars(path: str) -> bool:
    """检测路径是否包含损坏字符（??、�、NUL）。"""
    if not path:
        return False
    for ch in _DAMAGED_CHARS:
        if ch in path:
            return True
    for sub in _DAMAGED_SUBSTRINGS:
        if sub in path:
            return True
    return False


# ---- 扩展名检测 ----

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".heif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp"}
_ALL_MEDIA_EXTENSIONS = _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS


def is_media_extension(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in _ALL_MEDIA_EXTENSIONS


def is_image_extension(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in _IMAGE_EXTENSIONS


# ---- 路径规范化 ----

def normalize_path_slashes(path: str) -> str:
    r"""统一 slash/backslash，处理 UNC 和 \\?\ 前缀。"""
    if not path:
        return ""

    p = str(path).strip().strip("\"'")

    # 统一斜杠方向
    p = p.replace("/", "\\")

    # 去掉重复反斜杠（保留 UNC 开头的 \\）
    while "\\\\" in p and not p.startswith("\\\\"):
        p = p.replace("\\\\", "\\")

    # 处理 \\?\ 前缀
    if p.startswith("\\\\?\\UNC\\"):
        p = "\\" + p[7:]
    elif p.startswith("\\\\?\\"):
        p = p[4:]

    # os.path.normpath 完成最后的规范化
    try:
        p = os.path.normpath(p)
    except (ValueError, TypeError):
        pass

    return p


def compute_canonical_key(filepath: str) -> str:
    """计算用于 DB 去重/比较的稳定 canonical_key。

    Windows 下大小写不敏感。
    去除尾部反斜杠。
    """
    if not filepath:
        return ""
    key = normalize_path_slashes(str(filepath)).rstrip("\\")
    if sys.platform == "win32":
        key = key.casefold()
    return key


# ---- source_root 匹配 ----

def _match_source_root(normalized: str, source_dirs: list[str]) -> Optional[str]:
    """检查规范化路径是否在配置的 source_drive/photo root 下。

    返回匹配到的 source_dir，或 None（outside_root）。
    """
    if not normalized or not source_dirs:
        return None

    norm_lower = normalized.casefold()
    for sd in source_dirs:
        sd_norm = normalize_path_slashes(sd).rstrip("\\")
        if not sd_norm:
            continue
        sd_lower = sd_norm.casefold()
        # 检查 normalized 是否以 sd_norm + "\\" 开头
        if norm_lower == sd_lower or norm_lower.startswith(sd_lower + "\\"):
            return sd_norm

    return None


# ---- 主解析函数 ----

def resolve_file_path(
    raw_path: str,
    source_dirs: list[str],
    *,
    stat_file: bool = True,
) -> PathResolveResult:
    """解析并规范化文件路径，返回 PathResolveResult。

    Args:
        raw_path: 外部来源原始路径（Everything、目录遍历等）
        source_dirs: 配置的照片根目录列表
        stat_file: 是否执行 os.stat 获取文件信息

    Returns:
        PathResolveResult 包含规范化结果和健康状态
    """
    raw = str(raw_path or "")

    result = PathResolveResult(raw_path=raw)

    # 1. 检测损坏字符
    if _has_damaged_chars(raw):
        result.status = PathStatus.DAMAGED_PATH
        result.reason = "path contains damaged characters (?? / � / NUL)"
        result.normalized_path = normalize_path_slashes(raw)
        result.canonical_key = compute_canonical_key(raw)
        return result

    # 2. 路径规范化
    normalized = normalize_path_slashes(raw)
    result.normalized_path = normalized
    result.canonical_key = compute_canonical_key(normalized)

    if not normalized:
        result.status = PathStatus.DAMAGED_PATH
        result.reason = "path is empty after normalization"
        return result

    # 3. 扩展名检查
    ext = os.path.splitext(normalized)[1].lower()
    if ext not in _ALL_MEDIA_EXTENSIONS:
        result.status = PathStatus.UNSUPPORTED_EXT
        result.reason = f"unsupported extension: {ext}"
        result.is_media = False
        return result

    result.is_media = True

    # 4. source_root 匹配
    matched_root = _match_source_root(normalized, source_dirs)
    if matched_root is None:
        result.status = PathStatus.OUTSIDE_ROOT
        result.reason = "path not under any configured source_drive/photo root"
        return result
    result.source_root = matched_root

    # 5. stat 文件
    if stat_file:
        try:
            st = os.stat(normalized)
            result.file_size = st.st_size
            from datetime import datetime
            result.file_mtime = datetime.fromtimestamp(st.st_mtime).isoformat()
            result.status = PathStatus.OK
        except FileNotFoundError:
            # WinError 3: 系统找不到指定路径
            result.status = PathStatus.MISSING
            result.reason = "file not found (stat failed)"
        except OSError as e:
            result.status = PathStatus.STAT_FAILED
            result.reason = f"stat failed: {e}"
    else:
        # 不 stat 时，只要前面没有错误就视为 ok
        result.status = PathStatus.OK

    return result


def is_healthy_status(status) -> bool:
    """判断 path_status 是否健康（可用于扫描/索引/展示）。"""
    if isinstance(status, PathStatus):
        return status in HEALTHY_STATUSES
    if isinstance(status, str):
        return status == PathStatus.OK.value
    return False


def is_displayable_status(status) -> bool:
    """判断 path_status 是否可展示。"""
    if isinstance(status, PathStatus):
        return status in DISPLAYABLE_STATUSES
    if isinstance(status, str):
        return status == PathStatus.OK.value
    return False


def status_filter_condition(column: str = "f.path_status") -> str:
    """生成 SQL WHERE 条件，过滤不可展示/受损路径。

    使用 IS NULL OR 兼容旧数据（path_status 为 NULL 的记录仍可见）。
    """
    non_displayable = "', '".join(s.value for s in NON_DISPLAYABLE_STATUSES)
    return f"({column} IS NULL OR {column} NOT IN ('{non_displayable}'))"
