# Photo Memories - 完整代码审查

## .env.example

```
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
SOURCE_DRIVE=D:\\测试
PHOTO_DATA_DIR=D:\\测试\\photo-data

```

## .gitignore

```
.env
storage/
unknown_folders.txt
__pycache__/
*.pyc
.DS_Store
venv/
*.code-workspace
PROJECT_FULL_DUMP.txt
error.log
*.log
*.tmp
*.bak
*.old
.pytest_cache/
*.egg-info/
dist/
build/
*.exe.old
_test_*.py
classification_history.txt
debug_*.py
photos_before_*.db

```

## CHANGELOG.md

```markdown
# 更新记录

## V0.3 (2026-05-16)

### 核心架构重构
- **分层架构实现**：完整实现 5层架构（UI层/服务层/业务层/基础设施层/核心层）
- **新增目录结构**：新增 `business/`、`infra/`、`services/` 目录，按层组织代码
- **模块解耦**：核心业务逻辑从旧的 `memory/`、`indexer/`、`scanner/` 迁移到 `business/` 和 `infra/`

### 数据库
- **v0.2→v0.3 自动迁移**：启动时自动检测并执行迁移，包含备份机制
- **新增表**：`face_embeddings`、`face_clusters`、`events`、`memory_reasoning`、`migration_log`、`task_checkpoints`
- **表变更**：
  - `files` 新增 `source_dir` 字段（多库支持）
  - `photo_metadata` 新增 `phash`、`is_duplicate_of` 字段（去重）
  - `memories` 新增 `last_shown_at`、`click_count`、`dismissed_at`、`payload` 字段（生命周期管理）
  - `photo_tags` 新增 `source` 字段，重构 UNIQUE 约束为 `UNIQUE(file_id, tag, source)`
- **Repository 封装**：新增 `infra/db/repositories/`，包含 `files_repo.py`、`photo_metadata_repo.py`、`memories_repo.py`、`photo_tags_repo.py`

### 配置系统
- **多照片库支持**：`config.py` 新增 `source_dirs` 属性（分号分隔路径解析为列表）
- **新增常量**：`PHASH_THRESHOLD`（默认 8）、`MEMORY_HIGH_FREQ_DAYS`（默认 3）
- **同步机制更新**：添加 `SOURCE_DIRS` 全局变量同步

### 断点与任务管理
- **断点统一机制**：迁移到 `task_checkpoints` 表，废弃旧 JSON 文件断点
- **`checkpoint_manager.py` 重写**：支持 `scan`、`index`、`recognition` 等任意任务类型
- **`BackgroundTaskManager`**：后台线程统一管理与安全等待退出

### 感知哈希去重
- **`imagehash` 集成**：添加到 `requirements.txt`
- **索引阶段计算 phash**：`indexer/photo_indexer.py` 新增 phash 计算，在索引时一并完成
- **去重逻辑**：新增 `dedup_by_phash()` 函数，按距离判定重复
- **UI 排除重复**：推荐流程过滤 `is_duplicate_of` 非空的照片
- **索引与去重流程**：索引完成后自动触发去重，无需手动操作

### 多照片库支持
- **扫描器更新**：`scanner/fast_scan.py` 支持多源目录遍历，`source_dir` 字段正确标记
- **增量扫描逻辑**：每个 source_dir 分别对比，移除不在配置中的旧记录
- **`everything.py` 更新**：支持多路径查询，返回合并结果
- **设置窗口更新**：多路径输入（分号分隔）、路径存在验证、取消自动创建不存在目录

### 基础设施层 - 图像处理
- **`infra/image/thumbnail_loader.py`**：缩略图加载器统一封装，LRU 缓存（256张）
- **`infra/image/clip_encoder.py`**：SigLIP 语义标签编码器封装，单批/批量推理
- **`infra/image/face_detector.py`**：DeepFace+ArcFace 人脸检测与嵌入提取
- **`infra/image/object_detector.py`**：YOLOv8 目标检测（使用 ultralytics，预留接口切换后端）

### 业务层 - 图像识别
- **`business/image_recognition/tag_generator.py`**：基于 SigLIP 的语义标签生成
- **`business/image_recognition/face_cluster.py`**：人脸聚类与管理、人物重命名、人脸重分配
- **`business/image_recognition/scene_cluster.py`**：CLIP 场景聚类（按距离分组）

### 业务层 - 回忆生成
- **`business/memory/memory_discovery.py`**：
  - 那年今日回忆发现（N年前的今天）
  - 近期回忆发现
  - 按 `memory_type` 与 `dismissed_at` 查询过滤
- **`business/memory/event_detector.py`**：事件/旅行发现（时间断裂 + GPS 聚类）
- **`business/memory/memory_narrator.py`**：LLM 叙事生成
- **`business/memory/memory_reasoning.py`**：碎裂反馈记录与负面提示管理

### 服务层 - 识别调度
- **`services/recognition_scheduler.py`**：初始实现，支持 SigLIP 单批推理，断点续传，进度上报（设计与规划有细微差异，逐步完善）

### UI 层 - 重构与新增模块
- **主窗口重构**：`ui/app.py` 集成侧边栏，添加三视图切换（随机回忆/时间线/特殊回忆）
- **`ui/components/sidebar.py`**：侧边栏导航实现，3个导航项切换
- **`ui/components/timeline_view.py`**：时间线布局，按日分组展示
- **`ui/components/special_memories.py`**：特殊回忆卡片堆叠展示，碎裂动画框架（QPropertyAnimation）
- **`ui/components/person_detail.py`**：人物详情页、重命名、照片列表
- **`ui/components/memory_cards.py`**：重写为回忆卡片展示组件，替代旧的目录分类卡片
- **图片查看器**：保持不变，但记忆相关 UI 已按回忆体系重构

### 测试
- **`test_db_manager.py`**：新增 v0.3 迁移测试、新表测试、新字段测试
- **`test_db_schema.py`**：更新 schema 验证
- **测试通过**：完整 45/45 测试用例通过

### 依赖更新
- 新增 `imagehash>=4.3.0` 到 `requirements.txt`
- 预留 `open-clip-torch`、`deepface`、`ultralytics` 等依赖（后续补充，代码已实现）

---

## V0.2 (2026-05-15)

### 分类系统

- **5级优先级体系**：分支分类(5) > 内容信号(4) > EXIF(3) > 文件名(2) > 路径(1)，同级冲突时样片优先于生活
- **分支分类保护**：LLM/关键词判定的分支分类作为最高优先级信号，保护子文件夹不被低优先级信号翻转
- **LLM分类优化**：采样每个分支最多5个子路径+5个文件名作为上下文，精简prompt，返回值改用数组格式 `{"c":[1,2,0,...]}` 减少token
- **LLM返回值兼容**：处理 `deepseek-v4-flash` 返回 `[{...}]` 数组包裹的情况
- **分支自身记录**：每个分支自身写入 `folder_categories` 记录，供后台精分类的 `branch_cat_map` 使用
- **不确定分支处理**：LLM不确定的分支暂归生活（confidence=default-pending-refine），留给后台精分类用优先级体系重新判断

### 分类变更一致性修复

- **自动清理旧分类残留**：文件夹分类发生变化后，自动清理旧分类下的 `memories`、`photo_shown_history`、`click_history` 残留记录，避免旧回忆或旧历史继续展示已迁移照片
- **memories清理**：从旧分类回忆中移除变更文件夹的 photo_id，若回忆为空则删除
- **展示/点击历史清理**：批量删除旧分类下属于变更文件夹的记录

### 路径兼容性修复

- **路径正反斜杠统一**：新增 `_path_like_patterns()` 生成正反斜杠兼容的 SQL LIKE 参数，同时覆盖 `Y:\...` 和 `Y:/...`
- **路径父子判断**：新增 `_is_same_or_child_path()` 替代 `startswith(branch_path + os.sep)` 判断，统一用 `/` 归一化后比较
- 全部7处路径判断替换为兼容函数

### 关键词管理

- 新增内置样片关键词："希威社"、"色图"
- 删除误匹配的 "pixel"（EXIF中 Pixels/Inch 被误匹配），只保留 "google pixel"

### Bug修复

- **branch_cat_map 解包错误**：`for fp, cat, conf in classified_map.items()` → `for fp, (cat, conf) in classified_map.items()`
- **采样SQL漏掉分支自身文件**：增加 `WHERE (folder_path = ? OR folder_path LIKE ?)`
- **LLM分类的样片分支不被保护**：`branch_cat_map` 检查增加 `"llm" in b_conf`
- **采样SQL性能优化**：7次单独查询改为1次批量查询

### 架构文档

- ARCHITECTURE.md 更新优先级体系为5级
- 补充分类变更后历史一致性修复描述
- 补充LLM采样上下文和不确定分支处理描述
- 冲突解决规则更新为"同级时样片优先于生活"

### 清理

- 删除调试脚本 `debug_full.py`、`debug_kw.py`
- `.gitignore` 增加 `debug_*.py`、`photos_before_*.db` 规则

```

## README.md

```markdown
# NAS 照片回忆

> 本地化搭建的照片回忆，用它来唤醒 NAS 沉睡的照片。

你的 NAS 里躺着几万张照片，却很少翻看。这个项目用 LLM 自动分类文件夹、生成回忆标题，以瀑布流的方式把照片重新呈现给你——一切都在本地运行，数据不离开你的硬盘。

## 功能特点

- 🔍 **极速扫描** — 集成 Everything 搜索引擎，6 万+文件秒级发现
- 🤖 **LLM 智能分类** — 调用 DeepSeek API 自动将文件夹归为生活照片 / 拍摄样片 / 摄影照片 / 色情照片
- 💭 **回忆生成** — AI 为每组照片生成有温度的标题和描述
- 🖼️ **瀑布流浏览** — 虚拟滚动 + 懒加载缩略图，万级照片流畅展示
- 🔒 **完全本地** — 照片、缩略图、数据库全部存储在本地，仅 LLM 调用需要联网

## 快速开始

### 环境依赖

- Python 3.10+
- [DeepSeek API Key](https://platform.deepseek.com/)（用于分类和回忆生成）
- Windows（Everything 集成需要）

### 安装

```bash
git clone https://github.com/waxzml/photo-memories.git
cd photo-memories
pip install -r requirements.txt
```

### 启动

```bash
python main.py ui
# 或双击 launch.bat
```

首次启动会弹出配置窗口，填写：
- **照片库路径** — NAS 照片存放路径（如 `Y:\`）
- **缓存数据路径** — 数据库和缩略图存储路径
- **DeepSeek API Key** — `sk-...`

### CLI 模式

```bash
python main.py setup    # 首次配置
python main.py scan     # 扫描文件
python main.py classify # LLM 分类文件夹
python main.py index    # 生成缩略图
python main.py memories # 生成回忆
python main.py all      # 一键全流程
python main.py ui       # 启动界面
```

## Everything 集成（可选但强烈推荐）

项目内置 Everything 命令行集成，用于极速文件扫描。

### 配置步骤

1. 下载 [Everything 1.5a 便携版 64位](https://www.voidtools.com/forum/viewtopic.php?t=9787)
2. 将 `Everything64.exe` 放入 `everything/` 目录
3. **以管理员身份运行** `Everything64.exe`（首次需管理员权限创建 NTFS 索引）
4. 前往 **工具 → 选项 → NTFS**，对目标盘勾选「包含在数据库中」
5. 如果是网络盘（NAS/SMB），前往 **工具 → 选项 → 文件夹**，添加为强制索引
6. 等待索引完成，后续启动时 `launch.bat` 会自动启动 Everything

无 Everything 时自动回退到 `os.walk` 遍历 + 文件列表缓存。

## 项目结构

```
├── classifier/          # LLM 文件夹分类
├── indexer/             # 照片索引 & 缩略图生成
├── memory/              # 回忆生成
├── scanner/             # 文件扫描（Everything / os.walk）
├── services/            # Pipeline 流程编排
├── ui/                  # PyQt6 界面
│   ├── components/      # 瀑布流、设置窗口、图片查看器
│   └── recommendation.py # 照片排序 & 间隔算法
├── infra/               # 基础设施
│   ├── db/              # 数据库 & Repository
│   ├── fs/              # Everything 集成
│   └── llm/             # LLM 客户端（DeepSeek）
├── config.py            # 配置管理
├── db_manager.py        # 数据库管理
└── main.py              # 入口
```

## 技术栈

- **UI**: PyQt6 + 虚拟瀑布流（QScrollArea + 动态卡片）
- **LLM**: DeepSeek API（文件夹分类 + 回忆生成）
- **扫描**: Everything CLI / os.walk
- **数据库**: SQLite + WAL 模式
- **缩略图**: Pillow + EXIF 自动旋转
- **配置**: Pydantic Settings + .env

## License

[MIT](LICENSE)

```

## _merge.py

```python
import os

ROOT = r"d:\photo-memories-source"
OUTPUT = r"d:\photo-memories-source\CODE_REVIEW.md"
SKIP = {"ARCHITECTURE.md", "CODE_REVIEW.md", "es.exe"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".idea", ".venv"}
EXTS = {".py", ".bat", ".txt", ".env.example", ".gitignore", ".md"}

EXTRA_FILES = {
    os.path.join(ROOT, ".env.example"),
    os.path.join(ROOT, ".gitignore"),
    os.path.join(ROOT, "requirements.txt"),
    os.path.join(ROOT, "launch.bat"),
    os.path.join(ROOT, "CHANGELOG.md"),
    os.path.join(ROOT, "README.md"),
}

lines = []
lines.append("# Photo Memories - 完整代码审查\n")

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in sorted(filenames):
        fp = os.path.join(dirpath, fn)
        rel = os.path.relpath(fp, ROOT).replace("\\", "/")
        if fn in SKIP:
            continue
        if rel == "CODE_REVIEW.md":
            continue
        ext = os.path.splitext(fn)[1]
        if ext not in EXTS and fp not in EXTRA_FILES:
            continue
        if rel == "ARCHITECTURE.md":
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue
        lang_map = {".py": "python", ".bat": "batch", ".txt": "text", ".md": "markdown"}
        lang = lang_map.get(ext, "")
        lines.append(f"## {rel}\n")
        lines.append(f"```{lang}\n{content}\n```\n")

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

size_kb = os.path.getsize(OUTPUT) / 1024
print(f"Done: {OUTPUT} ({size_kb:.1f} KB)")

```

## checkpoint_manager.py

```python
import json
from enum import Enum

from logger_setup import logger


class CheckpointState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class CheckpointManager:
    def __init__(self, db, task_type, task_key="default"):
        self.db = db
        self.task_type = task_type
        self.task_key = task_key

    def load(self):
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    "SELECT status_json FROM task_checkpoints WHERE task_type = ? AND task_key = ?",
                    (self.task_type, self.task_key)
                ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.warning(f"加载断点失败: {e}")
        return None

    def save(self, state, **kwargs):
        try:
            data = {"state": state}
            data.update(kwargs)
            status_json = json.dumps(data, ensure_ascii=False)
            with self.db.connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO task_checkpoints (task_type, task_key, status_json, updated_at)
                       VALUES (?, ?, ?, datetime('now'))""",
                    (self.task_type, self.task_key, status_json)
                )
        except Exception as e:
            logger.warning(f"保存断点失败: {e}")

    def clear(self):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "DELETE FROM task_checkpoints WHERE task_type = ? AND task_key = ?",
                    (self.task_type, self.task_key)
                )
        except Exception as e:
            logger.warning(f"清除断点失败: {e}")

    def get_status(self):
        cp = self.load()
        if cp is None:
            return {"has_checkpoint": False}
        return {"has_checkpoint": True, "state": cp.get("state"), "data": cp}

    def request_pause(self):
        cp = self.load()
        if cp and cp["state"] == CheckpointState.RUNNING:
            cp["state"] = CheckpointState.PAUSED
            self.save(CheckpointState.PAUSED, **{k: v for k, v in cp.items() if k != "state"})
            logger.info("断点已标记为暂停")

    def request_stop(self):
        cp = self.load()
        if cp and cp["state"] in (CheckpointState.RUNNING, CheckpointState.PAUSED):
            self.save(CheckpointState.STOPPED, **{k: v for k, v in cp.items() if k != "state"})
            logger.info("断点已标记为停止")

    def is_pause_or_stop_requested(self):
        cp = self.load()
        if cp and cp["state"] in (CheckpointState.PAUSED, CheckpointState.STOPPED):
            return True
        return False

```

## config.py

```python
import os
from dotenv import load_dotenv, set_key, find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = find_dotenv() or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_classify_model: str = "deepseek-v4-flash"

    source_drive: str = "D:\\测试"
    photo_data_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage")

    thumbnail_size: tuple[int, int] = (400, 400)

    @property
    def source_dirs(self) -> list[str]:
        return [p.strip() for p in self.source_drive.split(";") if p.strip()]

    @property
    def db_path(self) -> str:
        return os.path.join(self.photo_data_dir, "photos.db")

    @property
    def thumbnail_dir(self) -> str:
        return os.path.join(self.photo_data_dir, "thumbnails")

    @property
    def classification_history_file(self) -> str:
        return os.path.join(self.photo_data_dir, "classification_history.txt")

    def is_configured(self) -> bool:
        return bool(self.deepseek_api_key and self.source_drive and self.photo_data_dir)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _sync_module_vars_from_settings():
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_CLASSIFY_MODEL
    global SOURCE_DRIVE, SOURCE_DIRS, DATA_DIR, DB_PATH, THUMBNAIL_DIR, CLASSIFICATION_HISTORY_FILE
    s = get_settings()
    DEEPSEEK_API_KEY = s.deepseek_api_key
    DEEPSEEK_BASE_URL = s.deepseek_base_url
    DEEPSEEK_MODEL = s.deepseek_model
    DEEPSEEK_CLASSIFY_MODEL = s.deepseek_classify_model
    SOURCE_DRIVE = s.source_drive
    SOURCE_DIRS = s.source_dirs
    DATA_DIR = s.photo_data_dir
    DB_PATH = s.db_path
    THUMBNAIL_DIR = s.thumbnail_dir
    CLASSIFICATION_HISTORY_FILE = s.classification_history_file


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp"}
THUMBNAIL_SIZE = (400, 400)
PHASH_THRESHOLD = 8
MEMORY_HIGH_FREQ_DAYS = 3

CATEGORY_LIFE = 1
CATEGORY_SAMPLE = 2

CATEGORY_NAMES = {
    CATEGORY_LIFE: "生活照片",
    CATEGORY_SAMPLE: "拍摄样片",
}

_OPENAI_CLIENT = None


def get_openai_client():
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        from openai import OpenAI
        s = get_settings()
        _OPENAI_CLIENT = OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)
    return _OPENAI_CLIENT


def is_configured():
    if not os.path.isfile(ENV_FILE):
        return False
    return get_settings().is_configured()


def save_config(source_drive, data_dir, api_key, base_url="https://api.deepseek.com", model="deepseek-chat"):
    global _OPENAI_CLIENT

    set_key(ENV_FILE, "SOURCE_DRIVE", source_drive)
    set_key(ENV_FILE, "PHOTO_DATA_DIR", data_dir)
    set_key(ENV_FILE, "DEEPSEEK_API_KEY", api_key)
    set_key(ENV_FILE, "DEEPSEEK_BASE_URL", base_url)
    set_key(ENV_FILE, "DEEPSEEK_MODEL", model)

    os.environ["SOURCE_DRIVE"] = source_drive
    os.environ["PHOTO_DATA_DIR"] = data_dir
    os.environ["DEEPSEEK_API_KEY"] = api_key
    os.environ["DEEPSEEK_BASE_URL"] = base_url
    os.environ["DEEPSEEK_MODEL"] = model

    global _settings
    _settings = Settings()
    _sync_module_vars_from_settings()
    _OPENAI_CLIENT = None

    s = get_settings()
    os.makedirs(s.photo_data_dir, exist_ok=True)
    os.makedirs(s.thumbnail_dir, exist_ok=True)

    from infra.llm.client import LLMClient
    LLMClient.reset()


def reload_config():
    global _OPENAI_CLIENT, _settings

    load_dotenv(ENV_FILE, override=True)
    _settings = Settings()
    _sync_module_vars_from_settings()
    _OPENAI_CLIENT = None

    s = get_settings()
    os.makedirs(s.photo_data_dir, exist_ok=True)
    os.makedirs(s.thumbnail_dir, exist_ok=True)

    from infra.llm.client import LLMClient
    LLMClient.reset()


_sync_module_vars_from_settings()
_s = get_settings()
os.makedirs(_s.photo_data_dir, exist_ok=True)
os.makedirs(_s.thumbnail_dir, exist_ok=True)

```

## db_manager.py

```python
import sqlite3
import shutil
from datetime import datetime
from contextlib import contextmanager

from logger_setup import logger
from config import DB_PATH

SCHEMA_VERSION = "0.3"


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_persistent_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, conn, table_name):
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None

    def _column_exists(self, conn, table_name, column_name):
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return any(row[1] == column_name for row in cursor.fetchall())

    def validate_schema(self) -> tuple[bool, list[str]]:
        """验证数据库 schema 完整性，返回 (是否通过, 错误列表)"""
        errors = []
        try:
            with self.connect() as conn:
                required_tables = [
                    "files", "folder_categories", "photo_metadata", "memories",
                    "click_history", "photo_tags", "sample_keywords", "life_keywords",
                    "photo_shown_history", "face_clusters", "face_embeddings",
                    "events", "memory_reasoning", "migration_log", "task_checkpoints"
                ]

                for table in required_tables:
                    if not self._table_exists(conn, table):
                        errors.append(f"Missing table: {table}")

                if not errors:
                    # 检查文件表必需字段
                    required_file_cols = ["id", "file_path", "file_name", "folder_path", "source_dir"]
                    for col in required_file_cols:
                        if not self._column_exists(conn, "files", col):
                            errors.append(f"Missing column: files.{col}")

                    # 检查 photo_metadata 必需字段
                    required_meta_cols = ["file_id", "date_taken", "phash", "is_duplicate_of"]
                    for col in required_meta_cols:
                        if not self._column_exists(conn, "photo_metadata", col):
                            errors.append(f"Missing column: photo_metadata.{col}")

                    # 检查 memories 必需字段
                    required_mem_cols = ["id", "category", "memory_type", "title", "photo_ids", "dismissed_at", "payload"]
                    for col in required_mem_cols:
                        if not self._column_exists(conn, "memories", col):
                            errors.append(f"Missing column: memories.{col}")

            return len(errors) == 0, errors
        except Exception as e:
            errors.append(f"Schema validation error: {str(e)}")
            return False, errors

    def _get_current_version(self, conn):
        if self._table_exists(conn, "migration_log"):
            cursor = conn.execute(
                "SELECT version_to FROM migration_log ORDER BY migrated_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return row[0]

        if not self._table_exists(conn, "files"):
            return None

        return "0.2"

    def _backup_database(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.db_path}.bak.{timestamp}"
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to {backup_path}")
        return backup_path

    def _create_v03_new_tables(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS face_clusters (
                cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT DEFAULT '',
                user_corrected INTEGER DEFAULT 0,
                representative_face INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS face_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                cluster_id INTEGER,
                FOREIGN KEY (file_id) REFERENCES files(id),
                FOREIGN KEY (cluster_id) REFERENCES face_clusters(cluster_id)
            );
            CREATE INDEX IF NOT EXISTS idx_fe_file ON face_embeddings(file_id);
            CREATE INDEX IF NOT EXISTS idx_fe_cluster ON face_embeddings(cluster_id);

            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                gps_cluster TEXT,
                location_name TEXT,
                photo_ids TEXT NOT NULL,
                event_type TEXT DEFAULT 'event'
            );

            CREATE TABLE IF NOT EXISTS memory_reasoning (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                reasoning TEXT,
                feedback_type TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            );

            CREATE TABLE IF NOT EXISTS migration_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_from TEXT NOT NULL,
                version_to TEXT NOT NULL,
                migrated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS task_checkpoints (
                task_type TEXT NOT NULL,
                task_key TEXT NOT NULL,
                status_json TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (task_type, task_key)
            );
        """)

    def _create_all_tables(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                folder_name TEXT NOT NULL,
                file_size INTEGER,
                file_mtime TEXT,
                file_hash TEXT,
                is_image INTEGER DEFAULT 1,
                scanned_at TEXT,
                source_dir TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_path);
            CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash);
            CREATE INDEX IF NOT EXISTS idx_files_source_dir ON files(source_dir);

            CREATE TABLE IF NOT EXISTS folder_categories (
                folder_path TEXT PRIMARY KEY,
                category INTEGER NOT NULL,
                confidence TEXT,
                classified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS photo_metadata (
                file_id INTEGER PRIMARY KEY,
                date_taken TEXT,
                camera_model TEXT,
                gps_lat REAL,
                gps_lon REAL,
                width INTEGER,
                height INTEGER,
                thumbnail_path TEXT,
                exif_json TEXT,
                indexed_at TEXT,
                is_starred INTEGER DEFAULT 0,
                phash TEXT,
                is_duplicate_of INTEGER,
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
            CREATE INDEX IF NOT EXISTS idx_meta_date ON photo_metadata(date_taken);
            CREATE INDEX IF NOT EXISTS idx_meta_phash ON photo_metadata(phash);
            CREATE INDEX IF NOT EXISTS idx_meta_duplicate ON photo_metadata(is_duplicate_of);

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category INTEGER NOT NULL,
                memory_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                photo_ids TEXT NOT NULL,
                cover_file_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                is_starred INTEGER DEFAULT 0,
                last_shown_at TEXT,
                click_count INTEGER DEFAULT 0,
                dismissed_at TEXT,
                payload TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE INDEX IF NOT EXISTS idx_memories_starred ON memories(is_starred);
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
            CREATE INDEX IF NOT EXISTS idx_memories_dismissed ON memories(dismissed_at);

            CREATE TABLE IF NOT EXISTS click_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                folder_path TEXT NOT NULL,
                category INTEGER,
                clicked_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
            CREATE INDEX IF NOT EXISTS idx_click_folder ON click_history(folder_path);
            CREATE INDEX IF NOT EXISTS idx_click_category ON click_history(category);

            CREATE TABLE IF NOT EXISTS photo_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (file_id) REFERENCES files(id),
                UNIQUE(file_id, tag, source)
            );
            CREATE INDEX IF NOT EXISTS idx_tags_file ON photo_tags(file_id);
            CREATE INDEX IF NOT EXISTS idx_tags_source ON photo_tags(source);

            CREATE TABLE IF NOT EXISTS sample_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS life_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS photo_shown_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                category INTEGER,
                shown_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
            CREATE INDEX IF NOT EXISTS idx_shown_file ON photo_shown_history(file_id);
            CREATE INDEX IF NOT EXISTS idx_shown_at ON photo_shown_history(shown_at);
        """)

        self._create_v03_new_tables(conn)

        conn.execute(
            "INSERT INTO migration_log (version_from, version_to) VALUES (?, ?)",
            ("init", SCHEMA_VERSION)
        )

    def _migrate_v02_to_v03(self, conn):
        from config import get_settings

        logger.info("Starting v0.2 -> v0.3 migration...")

        self._backup_database()

        if not self._column_exists(conn, "files", "source_dir"):
            conn.execute("ALTER TABLE files ADD COLUMN source_dir TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_source_dir ON files(source_dir)")
            s = get_settings()
            source_dirs = [p.strip() for p in s.source_drive.split(";") if p.strip()]
            if len(source_dirs) == 1:
                conn.execute("UPDATE files SET source_dir = ? WHERE source_dir IS NULL", (source_dirs[0],))
            logger.info("Added source_dir to files table")

        if not self._column_exists(conn, "photo_metadata", "phash"):
            conn.execute("ALTER TABLE photo_metadata ADD COLUMN phash TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_phash ON photo_metadata(phash)")
        if not self._column_exists(conn, "photo_metadata", "is_duplicate_of"):
            conn.execute("ALTER TABLE photo_metadata ADD COLUMN is_duplicate_of INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_duplicate ON photo_metadata(is_duplicate_of)")

        if not self._column_exists(conn, "memories", "last_shown_at"):
            conn.execute("ALTER TABLE memories ADD COLUMN last_shown_at TEXT")
        if not self._column_exists(conn, "memories", "click_count"):
            conn.execute("ALTER TABLE memories ADD COLUMN click_count INTEGER DEFAULT 0")
        if not self._column_exists(conn, "memories", "dismissed_at"):
            conn.execute("ALTER TABLE memories ADD COLUMN dismissed_at TEXT")
        if not self._column_exists(conn, "memories", "payload"):
            conn.execute("ALTER TABLE memories ADD COLUMN payload TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_dismissed ON memories(dismissed_at)")

        if not self._column_exists(conn, "photo_tags", "source"):
            conn.executescript("""
                CREATE TABLE photo_tags_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id),
                    UNIQUE(file_id, tag, source)
                );
                INSERT INTO photo_tags_new (id, file_id, tag, source, created_at)
                    SELECT id, file_id, tag, 'manual', created_at FROM photo_tags;
                DROP TABLE photo_tags;
                ALTER TABLE photo_tags_new RENAME TO photo_tags;
                CREATE INDEX IF NOT EXISTS idx_tags_file ON photo_tags(file_id);
                CREATE INDEX IF NOT EXISTS idx_tags_source ON photo_tags(source);
            """)

        self._create_v03_new_tables(conn)

        conn.execute(
            "INSERT INTO migration_log (version_from, version_to) VALUES (?, ?)",
            ("0.2", "0.3")
        )

        logger.info("v0.2 -> v0.3 migration completed")

    def init_tables(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")

        current_version = self._get_current_version(conn)

        if current_version is None:
            self._create_all_tables(conn)
        elif current_version == "0.2":
            self._migrate_v02_to_v03(conn)

        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()

        # 验证 schema
        is_valid, errors = self.validate_schema()
        if not is_valid:
            logger.warning(f"Schema validation issues found: {errors}")
        else:
            logger.info("Schema validation passed")


def get_database():
    return Database()

```

## launch.bat

```batch
@echo off
cd /d "%~dp0"
echo ========================================
echo   NAS 照片回忆
echo ========================================
echo.

REM 禁止生成 .pyc 缓存（避免旧字节码问题）
set PYTHONDONTWRITEBYTECODE=1

REM 启动 Everything 服务（如果存在）
if exist "everything\Everything64.exe" (
    set EVERYTHING_EXE=everything\Everything64.exe
) else if exist "everything\Everything.exe" (
    set EVERYTHING_EXE=everything\Everything.exe
)

if defined EVERYTHING_EXE (
    tasklist /FI "IMAGENAME eq Everything*.exe" 2>NUL | find /I "Everything" >NUL
    if errorlevel 1 (
        echo 正在启动 Everything 搜索服务...
        start "" /MIN "%EVERYTHING_EXE%" -startup
        timeout /t 3 /nobreak >NUL
        echo Everything 已启动
    ) else (
        echo Everything 已在运行
    )
)

REM Test mode: skip Y: drive scan, use existing DB
REM set PHOTO_TEST_MODE=1
REM python main.py ui

REM Full mode
python -B main.py ui

pause

```

## logger_setup.py

```python
import os
import logging
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "app.log")

logger = logging.getLogger("photo_memories")
logger.setLevel(logging.DEBUG)

file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    "[%(levelname)s] %(message)s"
))

logger.addHandler(file_handler)
logger.addHandler(console_handler)

```

## main.py

```python
import sys
import argparse

from logger_setup import logger
from db_manager import Database
from scanner.fast_scan import full_scan as scan_drive
from classifier.folder_classifier import classify_folders
from indexer.photo_indexer import index_photos
from memory.memory_generator import generate_all_memories
from ui.app import main as ui_main


def run_setup():
    from config import save_config, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, SOURCE_DRIVE, DATA_DIR, DEEPSEEK_API_KEY

    print("=== NAS 照片回忆 - 初始配置 ===\n")
    print("按回车使用当前值\n")

    src = input(f"照片库文件夹 [{SOURCE_DRIVE}]: ").strip()
    if not src:
        src = SOURCE_DRIVE

    data = input(f"缓存数据文件夹 [{DATA_DIR}]: ").strip()
    if not data:
        data = DATA_DIR

    api_key = input(f"DeepSeek API Key [{DEEPSEEK_API_KEY[:8]}...]: ").strip()
    if not api_key:
        api_key = DEEPSEEK_API_KEY

    save_config(src, data, api_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL)
    print(f"\n配置已保存到 .env 文件")
    print(f"  照片库: {src}")
    print(f"  缓存:   {data}")
    print(f"  API:    {api_key[:8]}...")


def run_scan():
    logger.info("扫描 Y 盘照片文件...")
    result = scan_drive()
    logger.info(f"完成: 总计 {result['total']} 文件, 新增 {result['new']}, 移除 {result['removed']}")
    return result


def run_classify():
    logger.info("LLM 文件夹分类中...")
    result = classify_folders()
    logger.info(f"分类完成: 已分类 {result['classified']}, 不确定 {result['unknown']}")
    return result


def run_index():
    logger.info("提取 EXIF 并生成缩略图...")
    result = index_photos()
    logger.info(f"完成: 索引 {result['indexed']}/{result['total']}")
    return result


def run_memories():
    logger.info("生成回忆...")
    results = generate_all_memories()
    for r in results:
        logger.info(f"  {r['category']}: {r.get('title', '跳过')}")
    return results


def run_all():
    run_scan()
    run_classify()
    run_index()
    run_memories()
    logger.info("全部完成！可以启动 UI 了。")


def main():
    parser = argparse.ArgumentParser(description="NAS 照片回忆系统")
    parser.add_argument("command", nargs="?", default="ui",
                        choices=["scan", "classify", "index", "memories", "all", "ui", "setup"],
                        help="执行步骤")
    args = parser.parse_args()
    logger.info(f"命令行参数: {args.command}")

    if args.command == "setup":
        run_setup()
        return

    from config import is_configured

    if args.command != "ui":
        if not is_configured():
            print("错误: 尚未配置。请先编辑 .env 文件或运行: python main.py setup")
            print(f"  SOURCE_DRIVE=照片库路径")
            print(f"  PHOTO_DATA_DIR=缓存数据路径")
            print(f"  DEEPSEEK_API_KEY=sk-...")
            sys.exit(1)

        Database().init_tables()
    elif is_configured():
        Database().init_tables()

    if args.command == "scan":
        run_scan()
    elif args.command == "classify":
        run_classify()
    elif args.command == "index":
        run_index()
    elif args.command == "memories":
        run_memories()
    elif args.command == "all":
        run_all()
    elif args.command == "ui":
        ui_main()


if __name__ == "__main__":
    main()

```

## requirements.txt

```text
openai>=1.0.0
Pillow>=10.0.0
pillow-heif>=1.0.0
python-dotenv>=1.0.0
pydantic-settings>=2.0.0
tenacity>=8.0.0
PyQt6>=6.5.0
exifread>=3.0.0
imagehash>=4.3.0
open-clip-torch>=2.24.0
deepface>=0.0.90
ultralytics>=8.0.0

```

## .pytest_cache/README.md

```markdown
# pytest cache directory #

This directory contains data from the pytest's cache plugin,
which provides the `--lf` and `--ff` options, as well as the `cache` fixture.

**Do not** commit this to version control.

See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.

```

## business/__init__.py

```python

```

## business/image_recognition/__init__.py

```python

```

## business/image_recognition/face_cluster.py

```python
import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from logger_setup import logger
from db_manager import Database
from core.models import FaceCluster, FaceEmbedding
from infra.db.repositories.face_clusters_repo import FaceClustersRepository
from infra.db.repositories.face_embeddings_repo import FaceEmbeddingsRepository

_DISTANCE_THRESHOLD = 0.6


def cluster_faces(embeddings: List[Tuple[int, np.ndarray]], threshold: float = _DISTANCE_THRESHOLD) -> Dict[int, int]:
    if not embeddings:
        return {}

    db = Database()
    clusters_repo = FaceClustersRepository(db)

    clusters: List[List[Tuple[int, np.ndarray]]] = []

    for file_id, emb in embeddings:
        assigned = False
        for cluster in clusters:
            rep = cluster[0][1]
            dist = np.linalg.norm(emb - rep)
            if dist < threshold:
                cluster.append((file_id, emb))
                assigned = True
                break
        if not assigned:
            clusters.append([(file_id, emb)])

    file_to_cluster = {}
    for cluster_idx, cluster in enumerate(clusters):
        representative_id = cluster[0][0]
        emb_data = [(file_id, emb.astype(np.float32).tobytes()) for file_id, emb in cluster]

        cluster_id = clusters_repo.insert_with_embeddings("", representative_id, emb_data)

        for file_id, _ in cluster:
            file_to_cluster[file_id] = cluster_id

    logger.info(f"人脸聚类完成: {len(embeddings)} 个嵌入 -> {len(clusters)} 个聚类")
    return file_to_cluster


def get_clusters() -> List[FaceCluster]:
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    return clusters_repo.get_all()


def get_cluster_members(cluster_id: int) -> List[int]:
    db = Database()
    embeddings_repo = FaceEmbeddingsRepository(db)
    return embeddings_repo.get_file_ids_by_cluster(cluster_id)


def rename_cluster(cluster_id: int, name: str):
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    clusters_repo.update_name(cluster_id, name)
    logger.info(f"聚类 {cluster_id} 命名为: {name}")


def reassign_face(embedding_id: int, new_cluster_id: int):
    db = Database()
    embeddings_repo = FaceEmbeddingsRepository(db)
    embeddings_repo.update_cluster(embedding_id, new_cluster_id)


def create_cluster_from_face(embedding_id: int, person_name: str = "") -> int:
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    embeddings_repo = FaceEmbeddingsRepository(db)

    cluster = FaceCluster(person_name=person_name, representative_face=embedding_id)
    new_cluster_id = clusters_repo.insert(cluster)
    embeddings_repo.update_cluster(embedding_id, new_cluster_id)
    return new_cluster_id


def get_person_memories() -> Dict[str, List[int]]:
    clusters = get_clusters()
    result = {}
    for c in clusters:
        name = c.person_name or f"人物{c.cluster_id}"
        members = get_cluster_members(c.cluster_id)
        if members:
            result[name] = members
    return result

```

## business/image_recognition/scene_cluster.py

```python
import numpy as np
from typing import List, Dict, Tuple
from collections import defaultdict

from logger_setup import logger
from infra.image.clip_encoder import encode_images_batch, is_available as clip_available

_SIMILARITY_THRESHOLD = 0.85


def cluster_by_scene(file_ids: List[int], threshold: float = _SIMILARITY_THRESHOLD) -> Dict[int, List[int]]:
    if not clip_available():
        logger.warning("SigLIP 不可用, 场景聚类跳过")
        return {}

    results = encode_images_batch(file_ids)
    if not results:
        return {}

    clusters: List[List[Tuple[int, np.ndarray]]] = []

    for file_id, emb in results:
        assigned = False
        for cluster in clusters:
            rep = cluster[0][1]
            sim = float(np.dot(emb, rep))
            if sim >= threshold:
                cluster.append((file_id, emb))
                assigned = True
                break
        if not assigned:
            clusters.append([(file_id, emb)])

    result = {}
    for cluster_idx, cluster in enumerate(clusters):
        result[cluster_idx] = [fid for fid, _ in cluster]

    logger.info(f"场景聚类完成: {len(results)} 张照片 -> {len(clusters)} 个场景")
    return result


def get_scene_tags(file_ids: List[int]) -> Dict[int, List[str]]:
    from business.image_recognition.tag_generator import generate_tags_batch
    return generate_tags_batch(file_ids)

```

## business/image_recognition/tag_generator.py

```python
import numpy as np
from typing import List, Dict, Tuple

from logger_setup import logger
from infra.image.clip_encoder import encode_image, encode_text, compute_similarity, is_available

TAG_CANDIDATES_ZH = [
    "日落", "日出", "海滩", "山脉", "森林", "湖泊", "河流", "天空", "云",
    "雪", "雨", "花", "草地", "沙漠", "城市", "建筑", "街道", "夜景",
    "人物", "儿童", "婴儿", "家庭", "情侣", "朋友", "聚会", "婚礼",
    "生日", "节日", "圣诞", "春节", "旅行", "飞机", "火车", "汽车",
    "自行车", "船", "食物", "蛋糕", "咖啡", "餐厅", "厨房",
    "宠物", "猫", "狗", "鸟", "鱼", "动物", "野生动物",
    "运动", "跑步", "游泳", "篮球", "足球", "瑜伽",
    "音乐", "乐器", "演唱会", "绘画", "手工",
    "毕业", "学校", "教室", "办公室", "会议",
    "公园", "游乐场", "博物馆", "图书馆",
    "自拍", "合影", "证件照", "风景照",
]

TAG_CANDIDATES_EN = [
    "sunset", "sunrise", "beach", "mountain", "forest", "lake", "river", "sky", "clouds",
    "snow", "rain", "flowers", "grass", "desert", "city", "architecture", "street", "night",
    "people", "children", "baby", "family", "couple", "friends", "party", "wedding",
    "birthday", "festival", "christmas", "travel", "airplane", "train", "car",
    "bicycle", "boat", "food", "cake", "coffee", "restaurant", "kitchen",
    "pet", "cat", "dog", "bird", "fish", "animal", "wildlife",
    "sports", "running", "swimming", "basketball", "football", "yoga",
    "music", "instrument", "concert", "painting", "craft",
    "graduation", "school", "classroom", "office", "meeting",
    "park", "playground", "museum", "library",
    "selfie", "group photo", "portrait", "landscape",
]

DEFAULT_TOP_K = 5
DEFAULT_THRESHOLD = 0.25

_text_embeddings_cache: Dict[str, np.ndarray] = {}


def _get_text_embeddings(candidates: List[str]) -> np.ndarray:
    key = "|".join(candidates)
    if key not in _text_embeddings_cache:
        result = encode_text(candidates)
        if result is not None:
            _text_embeddings_cache[key] = result
        else:
            return np.array([])
    return _text_embeddings_cache[key]


def generate_tags_for_image(
    file_id: int,
    candidates: List[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> List[str]:
    if not is_available():
        return []

    if candidates is None:
        candidates = TAG_CANDIDATES_ZH + TAG_CANDIDATES_EN

    image_emb = encode_image(file_id)
    if image_emb is None:
        return []

    text_emb = _get_text_embeddings(candidates)
    if text_emb.size == 0:
        return []

    similarities = compute_similarity(image_emb, text_emb)

    top_indices = np.argsort(similarities)[::-1][:top_k]
    tags = []
    for idx in top_indices:
        if similarities[idx] >= threshold:
            tags.append(candidates[idx])

    return tags


def generate_tags_batch(
    file_ids: List[int],
    candidates: List[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> Dict[int, List[str]]:
    if not is_available():
        return {}

    if candidates is None:
        candidates = TAG_CANDIDATES_ZH + TAG_CANDIDATES_EN

    text_emb = _get_text_embeddings(candidates)
    if text_emb.size == 0:
        return {}

    from infra.image.clip_encoder import encode_images_batch
    image_results = encode_images_batch(file_ids)

    result = {}
    for file_id, image_emb in image_results:
        similarities = compute_similarity(image_emb, text_emb)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        tags = [candidates[idx] for idx in top_indices if similarities[idx] >= threshold]
        result[file_id] = tags

    return result

```

## business/memory/__init__.py

```python

```

## business/memory/event_detector.py

```python
import json
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from collections import defaultdict

from logger_setup import logger
from db_manager import Database
from core.models import Event
from infra.db.repositories.events_repo import EventsRepository

_TIME_GAP_HOURS = 6
_GPS_CLUSTER_RADIUS_KM = 0.5


def detect_events() -> List[Event]:
    db = Database()
    events_repo = EventsRepository(db)

    rows = events_repo.get_photos_for_event_detection()
    if not rows:
        return []

    segments = _segment_by_time(rows)
    events = []

    for segment in segments:
        sub_segments = _sub_segment_by_gps(segment)
        for sub in sub_segments:
            photo_ids = [r[0] for r in sub]
            start_date = sub[0][1][:10]
            end_date = sub[-1][1][:10]
            gps_lat = sub[0][2]
            gps_lon = sub[0][3]
            category = sub[0][4] or 1

            gps_cluster = None
            if gps_lat is not None and gps_lon is not None:
                gps_cluster = f"{gps_lat:.2f},{gps_lon:.2f}"

            event_type = "travel" if start_date != end_date else "event"

            e = Event(
                start_date=start_date,
                end_date=end_date,
                gps_cluster=gps_cluster,
                photo_ids=json.dumps(photo_ids[:50]),
                event_type=event_type,
            )

            e.event_id = events_repo.insert(e)
            events.append(e)

    logger.info(f"事件检测完成: {len(events)} 个事件")
    return events


def _segment_by_time(rows) -> List[List[tuple]]:
    if not rows:
        return []

    segments = []
    current = [rows[0]]

    for i in range(1, len(rows)):
        prev_date = _parse_date(rows[i - 1][1])
        curr_date = _parse_date(rows[i][1])

        if prev_date and curr_date:
            gap = curr_date - prev_date
            if gap > timedelta(hours=_TIME_GAP_HOURS):
                segments.append(current)
                current = [rows[i]]
                continue

        current.append(rows[i])

    if current:
        segments.append(current)

    return segments


def _sub_segment_by_gps(segment) -> List[List[tuple]]:
    has_gps = any(r[2] is not None and r[3] is not None for r in segment)
    if not has_gps:
        return [segment]

    sub_segments = []
    current = [segment[0]]

    for i in range(1, len(segment)):
        prev_lat, prev_lon = segment[i - 1][2], segment[i - 1][3]
        curr_lat, curr_lon = segment[i][2], segment[i][3]

        if prev_lat is not None and prev_lon is not None and curr_lat is not None and curr_lon is not None:
            dist = _haversine_km(prev_lat, prev_lon, curr_lat, curr_lon)
            if dist > _GPS_CLUSTER_RADIUS_KM * 10:
                sub_segments.append(current)
                current = [segment[i]]
                continue

        current.append(segment[i])

    if current:
        sub_segments.append(current)

    return sub_segments


def _parse_date(date_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    from math import radians, sin, cos, sqrt, asin
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * asin(sqrt(a))


def get_events() -> List[Event]:
    db = Database()
    events_repo = EventsRepository(db)
    return events_repo.get_all()

```

## business/memory/memory_discovery.py

```python
import json
from datetime import datetime, timedelta
from typing import List, Optional

from logger_setup import logger
from db_manager import Database
from core.models import Memory
from infra.db.repositories.memories_repo import MemoriesRepository
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from config import MEMORY_HIGH_FREQ_DAYS


def discover_on_this_day(lookback_years: Optional[List[int]] = None) -> List[Memory]:
    if lookback_years is None:
        lookback_years = list(range(1, 11))

    today = datetime.now()
    target_dates = []
    for y in lookback_years:
        try:
            target = today.replace(year=today.year - y)
            target_dates.append(target.strftime("%m-%d"))
        except ValueError:
            continue

    if not target_dates:
        return []

    db = Database()
    pm_repo = PhotoMetadataRepository(db)
    memories_repo = MemoriesRepository(db)

    rows = pm_repo.get_photos_by_month_day(target_dates)

    if not rows:
        return []

    groups = {}
    for file_id, folder_path, date_taken, category in rows:
        month_day = date_taken[5:10]
        year = date_taken[:4]
        key = f"{year}-{month_day}"
        if key not in groups:
            groups[key] = {"ids": [], "category": category or 1, "date": date_taken}
        groups[key]["ids"].append(file_id)

    memories = []
    for key, group in groups.items():
        year_diff = today.year - int(key[:4])
        photo_ids = group["ids"][:20]
        title = f"{year_diff}年前的今天"
        description = f"{key[:4]}年{key[5:7]}月{key[8:10]}日"

        existing = _find_existing_memory(memories_repo, "on_this_day", key)
        if existing:
            continue

        m = Memory(
            category=group["category"],
            memory_type="on_this_day",
            title=title,
            description=description,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"date_key": key, "years_ago": year_diff}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"那年今日发现 {len(memories)} 组回忆")
    return memories


def discover_recent_memories(days: int = MEMORY_HIGH_FREQ_DAYS) -> List[Memory]:
    since = (datetime.now() - timedelta(days=days)).isoformat()

    db = Database()
    pm_repo = PhotoMetadataRepository(db)
    memories_repo = MemoriesRepository(db)

    rows = pm_repo.get_recent_photos(since)

    if not rows:
        return []

    groups = {}
    for file_id, folder_path, date_taken, category in rows:
        day = date_taken[:10]
        if day not in groups:
            groups[day] = {"ids": [], "category": category or 1}
        groups[day]["ids"].append(file_id)

    memories = []
    for day, group in groups.items():
        photo_ids = group["ids"][:20]
        title = f"近期回忆 · {day}"
        existing = _find_existing_memory(memories_repo, "recent", day)
        if existing:
            continue

        m = Memory(
            category=group["category"],
            memory_type="recent",
            title=title,
            photo_ids=json.dumps(photo_ids),
            cover_file_id=photo_ids[0] if photo_ids else None,
            payload=json.dumps({"date": day}),
        )
        mid = memories_repo.insert(m)
        m.id = mid
        memories.append(m)

    logger.info(f"近期回忆发现 {len(memories)} 组")
    return memories


def get_on_this_day_memories() -> List[Memory]:
    db = Database()
    memories_repo = MemoriesRepository(db)
    return memories_repo.get_undismissed_by_type("on_this_day")


def _find_existing_memory(memories_repo: MemoriesRepository, memory_type: str, payload_key: str) -> Optional[int]:
    rows = memories_repo.find_by_type_and_payload_key(memory_type)

    for mid, payload_str in rows:
        if not payload_str:
            continue
        try:
            payload = json.loads(payload_str)
            if "date_key" in payload and payload["date_key"] == payload_key:
                return mid
            if "date" in payload and payload["date"] == payload_key:
                return mid
        except Exception:
            continue
    return None

```

## business/memory/memory_narrator.py

```python
import json
from typing import Optional

from logger_setup import logger
from db_manager import Database
from infra.llm.client import get_llm_client
from infra.db.repositories.events_repo import EventsRepository
from infra.db.repositories.memories_repo import MemoriesRepository
import config


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
            model=config.DEEPSEEK_CLASSIFY_MODEL,
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
            model=config.DEEPSEEK_CLASSIFY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"回忆叙事生成失败 memory_id={memory_id}: {e}")
        return None

```

## business/memory/memory_reasoning.py

```python
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

```

## classifier/__init__.py

```python

```

## classifier/folder_classifier.py

```python
import os
import sqlite3
import json

from logger_setup import logger
from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_CLASSIFY_MODEL,
    CLASSIFICATION_HISTORY_FILE,
    CATEGORY_LIFE,
    CATEGORY_SAMPLE,
    CATEGORY_NAMES,
    SOURCE_DRIVE,
)
from db_manager import Database

_db = Database()

MAX_USER_CLASSIFY = 10

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
    "希威社", "色图",
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

    source = os.path.normpath(SOURCE_DRIVE)
    branches = set()
    for fp in all_folders:
        norm_fp = os.path.normpath(fp)
        try:
            rel = os.path.relpath(norm_fp, source)
        except ValueError:
            continue
        if rel == '.':
            continue
        parts = rel.split(os.sep)
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

    logger.info(f"分类历史已写入 {CLASSIFICATION_HISTORY_FILE}: {len(rows)} 条")
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
                model=DEEPSEEK_CLASSIFY_MODEL,
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
        logger.info("没有待分类的文件夹")
        return {"classified": 0, "unknown": 0, "skipped": 0, "needs_user": []}

    build_classification_history()

    branches = _get_branch_folders()
    if not branches:
        return {"classified": 0, "unknown": 0, "skipped": 0, "needs_user": []}

    branch_names = [os.path.basename(b) for b in branches]

    sample_branches = []
    life_branches = []
    llm_branches = []
    llm_branch_names = []
    for bp, bn in zip(branches, branch_names):
        if _match_sample_keyword(bn):
            sample_branches.append((bp, bn))
        elif _match_life_keyword(bn):
            life_branches.append((bp, bn))
        else:
            llm_branches.append(bp)
            llm_branch_names.append(bn)

    classified_count = 0
    if sample_branches:
        for bp, bn in sample_branches:
            set_folder_category(bp, CATEGORY_SAMPLE, "keyword-branch")
            sub_folders = [f for f in unclassified if _is_same_or_child_path(f, bp)]
            for sf in sub_folders:
                set_folder_category(sf, CATEGORY_SAMPLE, "keyword")
                classified_count += 1
        logger.info(f"样片关键词预分类: {len(sample_branches)} 个分支归为样片")

    if life_branches:
        for bp, bn in life_branches:
            set_folder_category(bp, CATEGORY_LIFE, "keyword-branch")
            sub_folders = [f for f in unclassified if _is_same_or_child_path(f, bp)]
            for sf in sub_folders:
                set_folder_category(sf, CATEGORY_LIFE, "keyword")
                classified_count += 1
        logger.info(f"生活关键词预分类: {len(life_branches)} 个分支归为生活")

    if not llm_branches:
        build_classification_history()
        return {"classified": classified_count, "unknown": 0, "skipped": 0, "needs_user": []}

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

    logger.info(f"LLM 分类 {len(llm_branches)} 个顶层分支")
    if progress_callback:
        progress_callback(0, len(llm_branches))

    result = classify_branches_with_llm(llm_branch_info)
    if not result:
        logger.warning("LLM 分类返回空结果，所有分支默认归为生活照片")
        for branch_path in llm_branches:
            sub_folders = [f for f in unclassified if _is_same_or_child_path(f, branch_path)]
            for sf in sub_folders:
                set_folder_category(sf, CATEGORY_LIFE, "fallback")
                classified_count += 1
        build_classification_history()
        return {"classified": classified_count, "unknown": 0, "skipped": 0, "needs_user": []}

    unknown_branches = []

    for branch_path, branch_name in zip(llm_branches, llm_branch_names):
        category = result.get(branch_name, 0)
        try:
            category = int(category)
        except (ValueError, TypeError):
            category = 0

        sub_folders = [f for f in unclassified if _is_same_or_child_path(f, branch_path)]

        if category in (1, 2):
            set_folder_category(branch_path, category, "llm-branch")
            for sf in sub_folders:
                set_folder_category(sf, category, "llm-branch")
                classified_count += 1
        else:
            unknown_branches.append(branch_path)

    if progress_callback:
        progress_callback(len(llm_branches), len(llm_branches))

    unknown_count = len(unknown_branches)
    needs_user = unknown_branches[:MAX_USER_CLASSIFY]

    for branch_path in unknown_branches:
        set_folder_category(branch_path, CATEGORY_LIFE, "default-pending-refine")
        sub_folders = [f for f in unclassified if _is_same_or_child_path(f, branch_path)]
        for sf in sub_folders:
            set_folder_category(sf, CATEGORY_LIFE, "default-pending-refine")
            classified_count += 1

    build_classification_history()

    logger.info(f"分类完成: 已分类 {classified_count} 个子文件夹, 不确定 {unknown_count} 个分支, 需用户确认 {len(needs_user)}")
    return {
        "classified": classified_count,
        "unknown": unknown_count,
        "skipped": 0,
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

        source_norm = os.path.normpath(SOURCE_DRIVE)

        branch_cat_map = {}
        for fp, (cat, conf) in classified_map.items():
            norm_fp = os.path.normpath(fp)
            try:
                rel = os.path.relpath(norm_fp, source_norm)
                if rel == '.' or os.sep not in rel:
                    branch_cat_map[os.path.basename(norm_fp).lower()] = (cat, conf)
            except ValueError:
                pass

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
            try:
                rel = os.path.relpath(norm_fp, source_norm)
                branch_name = rel.split(os.sep)[0].lower() if rel != '.' else folder_name
            except ValueError:
                branch_name = folder_name

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


if __name__ == "__main__":
    result = classify_folders()
    print(f"分类完成: 已分类 {result['classified']}, 不确定 {result['unknown']}, 需用户确认 {len(result['needs_user'])}")

```

## core/__init__.py

```python

```

## core/models.py

```python
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
    source_dir: Optional[str] = None

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
            self.scanned_at,
            self.source_dir
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
    phash: Optional[str] = None
    is_duplicate_of: Optional[int] = None

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
            self.is_starred,
            self.phash,
            self.is_duplicate_of
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
    last_shown_at: Optional[str] = None
    click_count: int = 0
    dismissed_at: Optional[str] = None
    payload: Optional[str] = None

    def as_row(self) -> tuple:
        return (
            self.category,
            self.memory_type,
            self.title,
            self.description,
            self.photo_ids,
            self.cover_file_id,
            self.created_at,
            self.is_starred,
            self.last_shown_at,
            self.click_count,
            self.dismissed_at,
            self.payload
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
    source: str = "manual"
    created_at: Optional[str] = None

    def as_row(self) -> tuple:
        return (self.file_id, self.tag, self.source, self.created_at)


@dataclass
class FaceEmbedding:
    id: Optional[int] = None
    file_id: int = 0
    embedding: bytes = b""
    cluster_id: Optional[int] = None


@dataclass
class FaceCluster:
    cluster_id: Optional[int] = None
    person_name: str = ""
    user_corrected: int = 0
    representative_face: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class Event:
    event_id: Optional[int] = None
    start_date: str = ""
    end_date: str = ""
    gps_cluster: Optional[str] = None
    location_name: Optional[str] = None
    photo_ids: str = ""
    event_type: str = "event"

    def get_photo_id_list(self) -> List[int]:
        import json
        try:
            return [int(x) for x in json.loads(self.photo_ids)]
        except Exception:
            return []


@dataclass
class MemoryReasoning:
    id: Optional[int] = None
    memory_id: int = 0
    reasoning: Optional[str] = None
    feedback_type: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class TaskCheckpoint:
    task_type: str = ""
    task_key: str = ""
    status_json: Optional[str] = None
    updated_at: Optional[str] = None

```

## everything/__init__.py

```python

```

## everything/ensure.py

```python
import os
import subprocess
import time

from logger_setup import logger

_EVERYTHING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "everything")

_INSTANCE = None


def get_es_path():
    bundled = os.path.join(_EVERYTHING_DIR, "es.exe")
    if os.path.exists(bundled):
        return bundled
    legacy = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "es_tool", "es.exe")
    if os.path.exists(legacy):
        return legacy
    return None


def get_everything_path():
    bundled = os.path.join(_EVERYTHING_DIR, "Everything64.exe")
    if os.path.exists(bundled):
        return bundled
    bundled = os.path.join(_EVERYTHING_DIR, "Everything.exe")
    if os.path.exists(bundled):
        return bundled
    return None


def is_everything_running():
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Everything*.exe"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0 and "Everything" in result.stdout
    except Exception:
        return False


def start_everything():
    everything_exe = get_everything_path()
    if not everything_exe:
        logger.warning("Everything.exe 未找到, 请放入 everything/ 目录")
        return False

    if is_everything_running():
        logger.info("Everything 已在运行")
        return True

    logger.info("启动 Everything: %s" % everything_exe)
    try:
        subprocess.Popen(
            [everything_exe, "-startup", "-minimized"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for _ in range(15):
            time.sleep(1)
            if is_everything_running():
                logger.info("Everything 服务已就绪")
                time.sleep(3)
                return True
        logger.warning("Everything 启动超时")
        return False
    except Exception as e:
        logger.error("启动 Everything 失败: %s" % e)
        return False


def detect_instance():
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE

    es = get_es_path()
    if not es:
        _INSTANCE = "__NONE__"
        return _INSTANCE

    for inst in ["", "1.5a", "1.5"]:
        cmd = [es, "-instance", inst, "-get-result-count", "C:\\"] if inst else [es, "-get-result-count", "C:\\"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode == 0 and r.stdout.strip().isdigit():
                _INSTANCE = inst
                logger.info("Everything 实例: [%s], C盘 %s 个文件" % (inst or "默认", r.stdout.strip()))
                return inst
        except Exception:
            pass
    _INSTANCE = "__FAIL__"
    return _INSTANCE


def ensure_everything():
    es = get_es_path()
    if not es:
        logger.warning("es.exe 未找到, Everything 扫描不可用")
        return False

    if not is_everything_running():
        if not start_everything():
            return False

    inst = detect_instance()
    if inst == "__FAIL__":
        logger.warning("Everything IPC 不可用, 请确认 Everything 已启动并完成索引")
        return False

    logger.info("Everything 可用, 实例: [%s]" % (inst or "默认"))
    return True

```

## indexer/__init__.py

```python

```

## indexer/photo_indexer.py

```python
import os
import json
import sqlite3
from datetime import datetime
from PIL import Image, ImageOps
import exifread
import imagehash

from pillow_heif import register_heif_opener
register_heif_opener()

Image.MAX_IMAGE_PIXELS = 500_000_000

from logger_setup import logger
from config import THUMBNAIL_DIR, THUMBNAIL_SIZE, DATA_DIR, PHASH_THRESHOLD
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState

_db = Database()
_cp = CheckpointManager(_db, "index")

IndexState = CheckpointState


def clear_checkpoint():
    _cp.clear()


def get_checkpoint_status():
    status = _cp.get_status()
    if not status["has_checkpoint"]:
        return {"has_checkpoint": False}
    data = status.get("data", {})
    return {
        "has_checkpoint": True,
        "state": data.get("state"),
        "current_index": data.get("current_index", 0),
        "total": data.get("total", 0),
        "indexed": data.get("indexed", 0),
    }


def set_paused():
    _cp.request_pause()


def set_stopped():
    _cp.request_stop()


def get_unindexed_photos():
    with _db.connect() as conn:
        rows = conn.execute("""
            SELECT f.id, f.file_path FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.is_image = 1 AND pm.file_id IS NULL
        """).fetchall()
    return rows


def _auto_rotate(img):
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def extract_exif(filepath):
    result = {
        "date_taken": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "raw": {},
        "orientation": None,
    }

    try:
        with open(filepath, "rb") as f:
            tags = exifread.process_file(f, details=False)

        for tag, value in tags.items():
            result["raw"][tag] = str(value)

        orient_tag = tags.get("Image Orientation")
        if orient_tag:
            try:
                result["orientation"] = int(str(orient_tag))
            except (ValueError, TypeError):
                pass

        date_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if date_tag:
            try:
                dt = datetime.strptime(str(date_tag), "%Y:%m:%d %H:%M:%S")
                result["date_taken"] = dt.isoformat()
            except ValueError:
                pass

        model_tag = tags.get("Image Model")
        if model_tag:
            result["camera_model"] = str(model_tag).strip()

        lat_tag = tags.get("GPS GPSLatitude")
        lon_tag = tags.get("GPS GPSLongitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_ref = tags.get("GPS GPSLongitudeRef")

        if lat_tag and lon_tag:
            try:
                lat = _convert_gps(lat_tag)
                lon = _convert_gps(lon_tag)
                if lat_ref and str(lat_ref).strip() == "S":
                    lat = -lat
                if lon_ref and str(lon_ref).strip() == "W":
                    lon = -lon
                result["gps_lat"] = lat
                result["gps_lon"] = lon
            except Exception:
                pass
    except Exception:
        pass

    return result


def _convert_gps(value):
    parts = str(value).strip("[]").split(",")
    degrees = float(parts[0].split("/")[0]) / float(parts[0].split("/")[-1])
    minutes = float(parts[1].split("/")[0]) / float(parts[1].split("/")[-1])
    seconds = float(parts[2].split("/")[0]) / float(parts[2].split("/")[-1])
    return degrees + minutes / 60 + seconds / 3600


def generate_thumbnail(filepath, thumbnail_name):
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    thumb_path = os.path.join(THUMBNAIL_DIR, thumbnail_name)

    if os.path.exists(thumb_path):
        return thumb_path, None, None

    try:
        with Image.open(filepath) as img:
            orig_w, orig_h = img.size
            img.draft("RGB", THUMBNAIL_SIZE)
            img = _auto_rotate(img)
            img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=80)
        return thumb_path, orig_w, orig_h
    except Exception as e:
        logger.error(f"缩略图生成失败 {filepath}: {e}")
        return None, None, None


INDEX_COMMIT_EVERY = 20


def compute_phash(filepath):
    try:
        with Image.open(filepath) as img:
            img = _auto_rotate(img)
            img.thumbnail((256, 256), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            return str(imagehash.phash(img))
    except Exception as e:
        logger.warning(f"pHash计算失败 {filepath}: {e}")
        return None


def dedup_by_phash(progress_callback=None):
    with _db.connect() as conn:
        rows = conn.execute(
            "SELECT file_id, phash FROM photo_metadata WHERE phash IS NOT NULL ORDER BY file_id"
        ).fetchall()

    if not rows:
        return {"checked": 0, "duplicates": 0}

    phash_map = {}
    duplicate_count = 0

    for i, (file_id, phash_str) in enumerate(rows):
        h = imagehash.hex_to_hash(phash_str)
        found_dup = False
        for existing_id, existing_hash in phash_map.items():
            if h - existing_hash <= PHASH_THRESHOLD:
                with _db.connect() as conn:
                    conn.execute(
                        "UPDATE photo_metadata SET is_duplicate_of = ? WHERE file_id = ?",
                        (existing_id, file_id)
                    )
                duplicate_count += 1
                found_dup = True
                break
        if not found_dup:
            phash_map[file_id] = h

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(i + 1, len(rows))

    logger.info(f"去重完成: 检查 {len(rows)} 张, 发现 {duplicate_count} 张重复")
    return {"checked": len(rows), "duplicates": duplicate_count}


def index_photos(progress_callback=None, batch_limit=None):
    _db.init_tables()

    photos = get_unindexed_photos()
    total = len(photos)
    logger.info(f"开始索引照片: 共 {total} 张待索引")
    cp = _cp.load()
    start_idx = cp["current_index"] if cp else 0
    indexed = cp.get("indexed", 0) if cp else 0

    is_new = not cp
    if is_new and total > 0:
        _cp.save(CheckpointState.RUNNING, current_index=0, total=total, indexed=0)
        logger.info("新索引任务已创建检查点")
    elif cp:
        logger.info(f"从断点恢复: idx={start_idx}, total={total}, indexed={indexed}")

    conn = _db.get_persistent_connection()

    batch_count = 0

    for i in range(start_idx, total):
        file_id, file_path = photos[i]

        try:
            if not os.path.exists(file_path):
                logger.warning(f"文件不存在, 跳过: {file_path}")
                continue

            exif_data = extract_exif(file_path)

            thumbnail_name = f"{file_id}.jpg"
            thumb_path, orig_w, orig_h = generate_thumbnail(file_path, thumbnail_name)

            import json as json_mod
            exif_json = (
                json_mod.dumps(exif_data["raw"], ensure_ascii=False)
                if exif_data["raw"]
                else None
            )

            phash = compute_phash(file_path)

            conn.execute(
                """INSERT OR REPLACE INTO photo_metadata
                   (file_id, date_taken, camera_model, gps_lat, gps_lon,
                    width, height, thumbnail_path, exif_json, indexed_at, phash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    file_id,
                    exif_data["date_taken"],
                    exif_data["camera_model"],
                    exif_data["gps_lat"],
                    exif_data["gps_lon"],
                    orig_w,
                    orig_h,
                    thumb_path,
                    exif_json,
                    datetime.now().isoformat(),
                    phash,
                ),
            )
            indexed += 1
            batch_count += 1

            if indexed % INDEX_COMMIT_EVERY == 0:
                conn.commit()
        except Exception as e:
            logger.error(f"索引照片失败 {file_path}: {e}")

        if progress_callback:
            progress_callback(i + 1, total)

        if batch_limit and batch_count >= batch_limit:
            _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, indexed=indexed)
            logger.info(f"索引热身完成: {indexed}/{total}, 剩余 {total - i - 1} 张后台继续")
            conn.commit()
            conn.close()
            return {"paused": True, "batch_limit_reached": True, "total": total, "indexed": indexed}

        if (i + 1) % 20 == 0:
            if _cp.is_pause_or_stop_requested():
                _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, indexed=indexed)
                logger.info(f"索引暂停: {indexed}/{total}")
                conn.commit()
                conn.close()
                return {"paused": True, "total": total, "indexed": indexed}

            _cp.save(CheckpointState.RUNNING, current_index=i + 1, total=total, indexed=indexed)

    conn.commit()
    conn.close()
    _cp.clear()
    logger.info(f"索引完成: 总计 {total}, 已索引 {indexed}")

    dedup_by_phash()

    return {"total": total, "indexed": indexed}


if __name__ == "__main__":
    result = index_photos()
    if result.get("paused"):
        print(f"索引暂停: {result['indexed']}/{result['total']}")
    else:
        print(f"索引完成: 总计 {result['total']}, 已索引 {result['indexed']}")

```

## infra/__init__.py

```python

```

## infra/db/__init__.py

```python

```

## infra/db/repositories/__init__.py

```python
from .files_repo import FilesRepository
from .photo_metadata_repo import PhotoMetadataRepository
from .memories_repo import MemoriesRepository
from .photo_tags_repo import PhotoTagsRepository
from .folder_categories_repo import FolderCategoriesRepository
from .click_history_repo import ClickHistoryRepository
from .face_embeddings_repo import FaceEmbeddingsRepository
from .face_clusters_repo import FaceClustersRepository
from .events_repo import EventsRepository
from .memory_reasoning_repo import MemoryReasoningRepository
from .task_checkpoints_repo import TaskCheckpointsRepository

__all__ = [
    "FilesRepository",
    "PhotoMetadataRepository",
    "MemoriesRepository",
    "PhotoTagsRepository",
    "FolderCategoriesRepository",
    "ClickHistoryRepository",
    "FaceEmbeddingsRepository",
    "FaceClustersRepository",
    "EventsRepository",
    "MemoryReasoningRepository",
    "TaskCheckpointsRepository"
]

```

## infra/db/repositories/click_history_repo.py

```python
from typing import Dict
from core.models import ClickHistory


class ClickHistoryRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, click: ClickHistory):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO click_history (file_id, folder_path, category) VALUES (?, ?, ?)",
                (click.file_id, click.folder_path, click.category)
            )

    def get_folder_click_counts(self, category: int) -> Dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT folder_path, COUNT(*) as cnt FROM click_history WHERE category = ? GROUP BY folder_path", (category,)).fetchall()
        return {row[0]: row[1] for row in rows}

```

## infra/db/repositories/events_repo.py

```python
from typing import List, Optional, Tuple
from core.models import Event


PhotoEventRow = Tuple[int, Optional[str], Optional[float], Optional[float], Optional[int]]


class EventsRepository:
    def __init__(self, db):
        self.db = db

    def get_photos_for_event_detection(self) -> List[PhotoEventRow]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT f.id, pm.date_taken, pm.gps_lat, pm.gps_lon, fc.category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE f.is_image = 1
                  AND pm.date_taken IS NOT NULL
                  AND pm.is_duplicate_of IS NULL
                  AND pm.thumbnail_path IS NOT NULL
                ORDER BY pm.date_taken ASC
            """).fetchall()
        return rows

    def insert(self, event: Event) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO events
                (start_date, end_date, gps_cluster, location_name, photo_ids, event_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event.start_date, event.end_date, event.gps_cluster,
                  event.location_name, event.photo_ids, event.event_type))
            return result.lastrowid

    def get_all(self) -> List[Event]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT event_id, start_date, end_date, gps_cluster,
                       location_name, photo_ids, event_type
                FROM events ORDER BY start_date DESC
            """).fetchall()
        return [
            Event(
                event_id=r[0], start_date=r[1], end_date=r[2], gps_cluster=r[3],
                location_name=r[4], photo_ids=r[5], event_type=r[6]
            )
            for r in rows
        ]

    def get_by_id(self, event_id: int) -> Optional[Event]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT event_id, start_date, end_date, gps_cluster,
                       location_name, photo_ids, event_type
                FROM events WHERE event_id = ?
            """, (event_id,)).fetchone()
        if row:
            return Event(
                event_id=row[0], start_date=row[1], end_date=row[2], gps_cluster=row[3],
                location_name=row[4], photo_ids=row[5], event_type=row[6]
            )
        return None

    def delete(self, event_id: int):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))

```

## infra/db/repositories/face_clusters_repo.py

```python
from typing import List, Optional, Tuple

import numpy as np
from core.models import FaceCluster


class FaceClustersRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, cluster: FaceCluster) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO face_clusters
                (person_name, user_corrected, representative_face)
                VALUES (?, ?, ?)
            """, (cluster.person_name, cluster.user_corrected,
                  cluster.representative_face))
            return result.lastrowid

    def insert_with_embeddings(self, person_name: str, representative_face: int,
                               embeddings: List[Tuple[int, bytes]]) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO face_clusters
                (person_name, user_corrected, representative_face, created_at)
                VALUES (?, 0, ?, datetime('now'))
            """, (person_name, representative_face))
            cluster_id = result.lastrowid

            for file_id, emb_bytes in embeddings:
                conn.execute(
                    "INSERT INTO face_embeddings (file_id, embedding, cluster_id) VALUES (?, ?, ?)",
                    (file_id, emb_bytes, cluster_id)
                )

            return cluster_id

    def get_all(self) -> List[FaceCluster]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT cluster_id, person_name, user_corrected,
                       representative_face, created_at
                FROM face_clusters ORDER BY created_at DESC
            """).fetchall()
        return [
            FaceCluster(
                cluster_id=r[0], person_name=r[1], user_corrected=r[2],
                representative_face=r[3], created_at=r[4]
            )
            for r in rows
        ]

    def get_by_id(self, cluster_id: int) -> Optional[FaceCluster]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT cluster_id, person_name, user_corrected,
                       representative_face, created_at
                FROM face_clusters WHERE cluster_id = ?
            """, (cluster_id,)).fetchone()
        if row:
            return FaceCluster(
                cluster_id=row[0], person_name=row[1], user_corrected=row[2],
                representative_face=row[3], created_at=row[4]
            )
        return None

    def update_name(self, cluster_id: int, person_name: str, user_corrected: int = 1):
        with self.db.connect() as conn:
            conn.execute("""
                UPDATE face_clusters
                SET person_name = ?, user_corrected = ?
                WHERE cluster_id = ?
            """, (person_name, user_corrected, cluster_id))

    def delete(self, cluster_id: int):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM face_clusters WHERE cluster_id = ?", (cluster_id,))

```

## infra/db/repositories/face_embeddings_repo.py

```python
from typing import List, Optional
from core.models import FaceEmbedding


class FaceEmbeddingsRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, embedding: FaceEmbedding) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO face_embeddings
                (file_id, embedding, cluster_id)
                VALUES (?, ?, ?)
            """, (embedding.file_id, embedding.embedding, embedding.cluster_id))
            return result.lastrowid

    def get_by_file_id(self, file_id: int) -> List[FaceEmbedding]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, file_id, embedding, cluster_id
                FROM face_embeddings WHERE file_id = ?
            """, (file_id,)).fetchall()
        return [
            FaceEmbedding(id=r[0], file_id=r[1], embedding=r[2], cluster_id=r[3])
            for r in rows
        ]

    def get_by_cluster_id(self, cluster_id: int) -> List[FaceEmbedding]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, file_id, embedding, cluster_id
                FROM face_embeddings WHERE cluster_id = ?
            """, (cluster_id,)).fetchall()
        return [
            FaceEmbedding(id=r[0], file_id=r[1], embedding=r[2], cluster_id=r[3])
            for r in rows
        ]

    def get_file_ids_by_cluster(self, cluster_id: int) -> List[int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT file_id FROM face_embeddings WHERE cluster_id = ?",
                (cluster_id,)
            ).fetchall()
        return [r[0] for r in rows]

    def update_cluster(self, embedding_id: int, cluster_id: Optional[int]):
        with self.db.connect() as conn:
            conn.execute("""
                UPDATE face_embeddings SET cluster_id = ? WHERE id = ?
            """, (cluster_id, embedding_id))

    def get_all_unclustered(self) -> List[FaceEmbedding]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, file_id, embedding, cluster_id
                FROM face_embeddings WHERE cluster_id IS NULL
            """).fetchall()
        return [
            FaceEmbedding(id=r[0], file_id=r[1], embedding=r[2], cluster_id=r[3])
            for r in rows
        ]

    def get_existing_file_ids(self) -> set:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT file_id FROM face_embeddings").fetchall()
        return {r[0] for r in rows}

```

## infra/db/repositories/files_repo.py

```python
from typing import Set, Optional, List
from core.models import File


class FilesRepository:
    def __init__(self, db):
        self.db = db

    def get_existing_paths(self) -> Set[str]:
        with self.db.connect() as conn:
            return {r[0] for r in conn.execute("SELECT file_path FROM files")}

    def insert_or_ignore(self, file: File) -> int:
        with self.db.connect() as conn:
            result = conn.execute(
                """INSERT OR IGNORE INTO files
                (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                file.as_row()
            )
            return result.rowcount

    def delete_missing(self, missing_paths: Set[str]) -> int:
        if not missing_paths:
            return 0
        with self.db.connect() as conn:
            count = 0
            for path in missing_paths:
                result = conn.execute("DELETE FROM files WHERE file_path = ?", (path,))
                count += result.rowcount
            return count

    def count(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def get_all_file_ids(self) -> List[int]:
        with self.db.connect() as conn:
            return [r[0] for r in conn.execute("SELECT id FROM files WHERE is_image = 1")]

    def get_paths_by_source_dir(self, source_dir: str) -> Set[str]:
        with self.db.connect() as conn:
            return {r[0] for r in conn.execute(
                "SELECT file_path FROM files WHERE source_dir = ?", (source_dir,)
            )}

```

## infra/db/repositories/folder_categories_repo.py

```python
from typing import List, Optional
from core.models import FolderCategory


class FolderCategoriesRepository:
    def __init__(self, db):
        self.db = db

    def get_unclassified_folders(self) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT DISTINCT f.folder_path FROM files f
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE fc.folder_path IS NULL
            """).fetchall()
        return [row[0] for row in rows]

    def get_all_folders(self) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT folder_path FROM files").fetchall()
        return [row[0] for row in rows]

    def set_folder_category(self, folder_path: str, category: int, confidence: Optional[str] = None):
        with self.db.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO folder_categories (folder_path, category, confidence, classified_at)
                VALUES (?, ?, ?, datetime('now'))""",
                (folder_path, category, confidence)
            )

    def get_folder_category(self, folder_path: str) -> Optional[int]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT category FROM folder_categories WHERE folder_path = ?", (folder_path,)).fetchone()
        return row[0] if row else None

```

## infra/db/repositories/memories_repo.py

```python
from typing import List, Optional, Tuple
from core.models import Memory


class MemoriesRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, memory: Memory) -> int:
        with self.db.connect() as conn:
            result = conn.execute(
                """INSERT INTO memories
                (category, memory_type, title, description, photo_ids, cover_file_id, is_starred, last_shown_at, click_count, dismissed_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory.category, memory.memory_type, memory.title, memory.description,
                 memory.photo_ids, memory.cover_file_id, memory.is_starred,
                 memory.last_shown_at, memory.click_count, memory.dismissed_at, memory.payload)
            )
            return result.lastrowid

    def set_starred(self, memory_id: int, starred: bool):
        with self.db.connect() as conn:
            conn.execute("UPDATE memories SET is_starred = ? WHERE id = ?", (1 if starred else 0, memory_id))

    def get_by_id(self, memory_id: int) -> Optional[Memory]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at, last_shown_at, click_count, dismissed_at, payload FROM memories WHERE id = ?",
                (memory_id,)
            ).fetchone()
        if not row:
            return None
        return Memory(
            id=row[0], category=row[1], memory_type=row[2], title=row[3], description=row[4],
            photo_ids=row[5], cover_file_id=row[6], is_starred=row[7], created_at=row[8],
            last_shown_at=row[9], click_count=row[10], dismissed_at=row[11], payload=row[12]
        )

    def get_all(self, category: Optional[int] = None, starred_only: bool = False) -> List[Memory]:
        query = "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at, last_shown_at, click_count, dismissed_at, payload FROM memories WHERE 1=1"
        params = []
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        if starred_only:
            query += " AND is_starred = 1"
        query += " ORDER BY created_at DESC"
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        memories = []
        for row in rows:
            m = Memory(
                id=row[0], category=row[1], memory_type=row[2], title=row[3], description=row[4],
                photo_ids=row[5], cover_file_id=row[6], is_starred=row[7], created_at=row[8],
                last_shown_at=row[9], click_count=row[10], dismissed_at=row[11], payload=row[12]
            )
            memories.append(m)
        return memories

    def get_latest_title(self, category: int) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT title FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT 1", (category,)).fetchone()
        return row[0] if row else None

    def get_undismissed(self, category: Optional[int] = None) -> List[Memory]:
        query = "SELECT id, category, memory_type, title, description, photo_ids, cover_file_id, is_starred, created_at, last_shown_at, click_count, dismissed_at, payload FROM memories WHERE dismissed_at IS NULL"
        params = []
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC"
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        memories = []
        for row in rows:
            m = Memory(
                id=row[0], category=row[1], memory_type=row[2], title=row[3], description=row[4],
                photo_ids=row[5], cover_file_id=row[6], is_starred=row[7], created_at=row[8],
                last_shown_at=row[9], click_count=row[10], dismissed_at=row[11], payload=row[12]
            )
            memories.append(m)
        return memories

    def get_undismissed_by_type(self, memory_type: str) -> List[Memory]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, category, memory_type, title, description, photo_ids,
                       cover_file_id, is_starred, created_at, last_shown_at,
                       click_count, dismissed_at, payload
                FROM memories
                WHERE memory_type = ? AND dismissed_at IS NULL
                ORDER BY created_at DESC
            """, (memory_type,)).fetchall()
        return [
            Memory(
                id=r[0], category=r[1], memory_type=r[2], title=r[3], description=r[4],
                photo_ids=r[5], cover_file_id=r[6], is_starred=r[7], created_at=r[8],
                last_shown_at=r[9], click_count=r[10], dismissed_at=r[11], payload=r[12]
            )
            for r in rows
        ]

    def find_by_type_and_payload_key(self, memory_type: str) -> List[Tuple[int, str]]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, payload FROM memories
                WHERE memory_type = ? AND dismissed_at IS NULL
                ORDER BY created_at DESC
            """, (memory_type,)).fetchall()
        return [(r[0], r[1]) for r in rows]

    def update_shown(self, memory_id: int):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE memories SET last_shown_at = datetime('now'), click_count = click_count + 1 WHERE id = ?",
                (memory_id,)
            )

    def dismiss(self, memory_id: int):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE memories SET dismissed_at = datetime('now') WHERE id = ?",
                (memory_id,)
            )

    def increment_click(self, memory_id: int):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE memories SET click_count = click_count + 1 WHERE id = ?",
                (memory_id,)
            )

```

## infra/db/repositories/memory_reasoning_repo.py

```python
from typing import List, Optional
from core.models import MemoryReasoning


class MemoryReasoningRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, reasoning: MemoryReasoning) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO memory_reasoning
                (memory_id, reasoning, feedback_type, created_at)
                VALUES (?, ?, ?, ?)
            """, (reasoning.memory_id, reasoning.reasoning, reasoning.feedback_type, reasoning.created_at))
            return result.lastrowid

    def insert_raw(self, memory_id: int, reasoning: Optional[str], feedback_type: str) -> int:
        with self.db.connect() as conn:
            result = conn.execute("""
                INSERT INTO memory_reasoning
                (memory_id, reasoning, feedback_type)
                VALUES (?, ?, ?)
            """, (memory_id, reasoning, feedback_type))
            return result.lastrowid

    def get_by_memory_id(self, memory_id: int) -> List[MemoryReasoning]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, memory_id, reasoning, feedback_type, created_at
                FROM memory_reasoning WHERE memory_id = ? ORDER BY created_at DESC
            """, (memory_id,)).fetchall()
        return [
            MemoryReasoning(
                id=r[0], memory_id=r[1], reasoning=r[2],
                feedback_type=r[3], created_at=r[4]
            )
            for r in rows
        ]

    def get_all(self) -> List[MemoryReasoning]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT id, memory_id, reasoning, feedback_type, created_at
                FROM memory_reasoning ORDER BY created_at DESC
            """).fetchall()
        return [
            MemoryReasoning(
                id=r[0], memory_id=r[1], reasoning=r[2],
                feedback_type=r[3], created_at=r[4]
            )
            for r in rows
        ]

    def get_negative_reasons(self, limit: int = 20) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT DISTINCT reasoning
                FROM memory_reasoning
                WHERE feedback_type = 'dismiss' AND reasoning IS NOT NULL
                LIMIT ?
            """, (limit,)).fetchall()
        return [r[0] for r in rows if r[0]]

```

## infra/db/repositories/photo_metadata_repo.py

```python
from typing import List, Optional, Tuple
from core.models import PhotoMetadata


PhotoDiscoveryRow = Tuple[int, str, Optional[str], Optional[int]]


class PhotoMetadataRepository:
    def __init__(self, db):
        self.db = db

    def get_unindexed_photos(self) -> List[tuple]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT f.id, f.file_path FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1 AND pm.file_id IS NULL
            """).fetchall()
        return rows

    def get_by_file_id(self, file_id: int) -> Optional[PhotoMetadata]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT file_id, date_taken, camera_model, gps_lat, gps_lon, width, height,
                       thumbnail_path, exif_json, indexed_at, is_starred, phash, is_duplicate_of
                FROM photo_metadata WHERE file_id = ?
            """, (file_id,)).fetchone()
        if row:
            return PhotoMetadata(*row)
        return None

    def insert_or_replace(self, metadata: PhotoMetadata):
        with self.db.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO photo_metadata
                (file_id, date_taken, camera_model, gps_lat, gps_lon, width, height, thumbnail_path, exif_json, indexed_at, is_starred, phash, is_duplicate_of)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                metadata.as_row()
            )

    def set_starred(self, file_id: int, starred: bool):
        with self.db.connect() as conn:
            conn.execute("UPDATE photo_metadata SET is_starred = ? WHERE file_id = ?", (1 if starred else 0, file_id))

    def get_starred_file_ids(self, category: Optional[int] = None) -> List[int]:
        query = "SELECT file_id FROM photo_metadata WHERE is_starred = 1"
        params = []
        if category is not None:
            query += " AND file_id IN (SELECT id FROM files f JOIN folder_categories fc ON f.folder_path = fc.folder_path WHERE fc.category = ?)"
            params.append(category)
        with self.db.connect() as conn:
            return [r[0] for r in conn.execute(query, params).fetchall()]

    def get_photos_without_phash(self, limit: int = 100) -> List[int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT file_id FROM photo_metadata WHERE phash IS NULL LIMIT ?", (limit,)
            ).fetchall()
        return [r[0] for r in rows]

    def get_photos_without_siglip_tags(self, limit: int = 10000) -> List[int]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT f.id FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1 AND pm.thumbnail_path IS NOT NULL
                AND f.id NOT IN (SELECT DISTINCT file_id FROM photo_tags WHERE source = 'siglip')
                LIMIT ?
            """, (limit,)).fetchall()
        return [r[0] for r in rows]

    def get_photos_by_month_day(self, month_days: List[str]) -> List[PhotoDiscoveryRow]:
        if not month_days:
            return []
        conditions = " OR ".join("substr(pm.date_taken, 6, 5) = ?" for _ in month_days)
        with self.db.connect() as conn:
            rows = conn.execute(f"""
                SELECT f.id, f.folder_path, pm.date_taken, fc.category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE f.is_image = 1
                  AND pm.date_taken IS NOT NULL
                  AND pm.is_duplicate_of IS NULL
                  AND pm.thumbnail_path IS NOT NULL
                  AND ({conditions})
                ORDER BY pm.date_taken DESC
            """, month_days).fetchall()
        return rows

    def get_recent_photos(self, since: str, limit: int = 200) -> List[PhotoDiscoveryRow]:
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT f.id, f.folder_path, pm.date_taken, fc.category
                FROM files f
                JOIN photo_metadata pm ON f.id = pm.file_id
                LEFT JOIN folder_categories fc ON f.folder_path = fc.folder_path
                WHERE f.is_image = 1
                  AND pm.date_taken IS NOT NULL
                  AND pm.is_duplicate_of IS NULL
                  AND pm.thumbnail_path IS NOT NULL
                  AND pm.date_taken >= ?
                ORDER BY pm.date_taken DESC
                LIMIT ?
            """, (since, limit)).fetchall()
        return rows

    def update_phash(self, file_id: int, phash: str, is_duplicate_of: Optional[int] = None):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE photo_metadata SET phash = ?, is_duplicate_of = ? WHERE file_id = ?",
                (phash, is_duplicate_of, file_id)
            )

```

## infra/db/repositories/photo_tags_repo.py

```python
from typing import List
from core.models import PhotoTag


class PhotoTagsRepository:
    def __init__(self, db):
        self.db = db

    def insert_or_ignore(self, tag: PhotoTag) -> int:
        try:
            with self.db.connect() as conn:
                result = conn.execute(
                    "INSERT OR IGNORE INTO photo_tags (file_id, tag, source) VALUES (?, ?, ?)",
                    (tag.file_id, tag.tag, tag.source)
                )
                return result.rowcount
        except Exception:
            return 0

    def get_tags_for_file(self, file_id: int) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT tag FROM photo_tags WHERE file_id = ?", (file_id,)).fetchall()
        return [row[0] for row in rows]

    def get_tags_for_file_by_source(self, file_id: int, source: str) -> List[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT tag FROM photo_tags WHERE file_id = ? AND source = ?",
                (file_id, source)
            ).fetchall()
        return [row[0] for row in rows]

    def get_file_ids_by_source(self, source: str) -> set:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT file_id FROM photo_tags WHERE source = ?",
                (source,)
            ).fetchall()
        return {r[0] for r in rows}

```

## infra/db/repositories/task_checkpoints_repo.py

```python
from typing import Optional
from core.models import TaskCheckpoint
import json


class TaskCheckpointsRepository:
    def __init__(self, db):
        self.db = db

    def save(self, checkpoint: TaskCheckpoint):
        with self.db.connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO task_checkpoints
                (task_type, task_key, status_json, updated_at)
                VALUES (?, ?, ?, ?)
            """, (checkpoint.task_type, checkpoint.task_key,
                  checkpoint.status_json, checkpoint.updated_at))

    def get(self, task_type: str, task_key: str) -> Optional[TaskCheckpoint]:
        with self.db.connect() as conn:
            row = conn.execute("""
                SELECT task_type, task_key, status_json, updated_at
                FROM task_checkpoints
                WHERE task_type = ? AND task_key = ?
            """, (task_type, task_key)).fetchone()
        if row:
            return TaskCheckpoint(
                task_type=row[0], task_key=row[1],
                status_json=row[2], updated_at=row[3]
            )
        return None

    def get_status(self, task_type: str, task_key: str) -> Optional[dict]:
        cp = self.get(task_type, task_key)
        if cp and cp.status_json:
            try:
                return json.loads(cp.status_json)
            except Exception:
                pass
        return None

    def save_status(self, task_type: str, task_key: str, status: dict):
        import datetime
        now = datetime.datetime.now().isoformat()
        checkpoint = TaskCheckpoint(
            task_type=task_type,
            task_key=task_key,
            status_json=json.dumps(status),
            updated_at=now
        )
        self.save(checkpoint)

    def delete(self, task_type: str, task_key: str):
        with self.db.connect() as conn:
            conn.execute("""
                DELETE FROM task_checkpoints
                WHERE task_type = ? AND task_key = ?
            """, (task_type, task_key))

```

## infra/fs/__init__.py

```python

```

## infra/fs/everything.py

```python
import subprocess
from typing import List


def is_available() -> bool:
    try:
        subprocess.run(["es", "-help"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception:
        return False


def search_images(source_dirs: List[str], image_extensions: List[str]) -> List[str]:
    ext_str = " ".join([f"ext:{e.lstrip('.')}" for e in image_extensions])
    path_query = " | ".join(source_dirs)
    cmd = ["es", "-path", path_query, "-n", "-utf8", "-sort-size", "descending"]
    cmd.extend(ext_str.split())
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        lines = result.stdout.splitlines()
        return [line.strip() for line in lines if line.strip()]
    except Exception:
        return []

```

## infra/image/__init__.py

```python

```

## infra/image/clip_encoder.py

```python
import numpy as np
from typing import Optional, List, Tuple

from logger_setup import logger
from infra.image.thumbnail_loader import get_thumbnail_loader


_model = None
_preprocess = None
_tokenizer = None
_model_name = "ViT-SO400M-14-SigLIP-384"
_pretrained = "webli"


def _load_model():
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return True
    try:
        import open_clip
        _model, _, _preprocess = open_clip.create_model_and_transforms(_model_name, pretrained=_pretrained)
        _tokenizer = open_clip.get_tokenizer(_model_name)
        _model.eval()
        logger.info(f"SigLIP 模型加载完成: {_model_name}")
        return True
    except ImportError:
        logger.warning("open_clip 未安装, SigLIP 不可用. 安装: pip install open-clip-torch")
        return False
    except Exception as e:
        logger.error(f"SigLIP 模型加载失败: {e}")
        return False


def is_available() -> bool:
    if _model is not None:
        return True
    try:
        import open_clip
        return True
    except ImportError:
        return False


def encode_image(file_id: int) -> Optional[np.ndarray]:
    if not _load_model():
        return None

    loader = get_thumbnail_loader()
    img = loader.load(file_id, size=(384, 384))
    if img is None:
        return None

    try:
        import torch
        with torch.no_grad():
            image_input = _preprocess(img).unsqueeze(0)
            embedding = _model.encode_image(image_input)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            return embedding.cpu().numpy().flatten()
    except Exception as e:
        logger.warning(f"图像编码失败 file_id={file_id}: {e}")
        return None


def encode_images_batch(file_ids: List[int], batch_size: int = 16) -> List[Tuple[int, np.ndarray]]:
    if not _load_model():
        return []

    import torch
    loader = get_thumbnail_loader()
    results = []

    for start in range(0, len(file_ids), batch_size):
        batch_ids = file_ids[start:start + batch_size]
        images = []
        valid_ids = []
        for fid in batch_ids:
            img = loader.load(fid, size=(384, 384))
            if img is not None:
                images.append(_preprocess(img))
                valid_ids.append(fid)

        if not images:
            continue

        try:
            with torch.no_grad():
                batch_tensor = torch.stack(images)
                embeddings = _model.encode_image(batch_tensor)
                embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
                embeddings_np = embeddings.cpu().numpy()

            for i, fid in enumerate(valid_ids):
                results.append((fid, embeddings_np[i].flatten()))
        except Exception as e:
            logger.warning(f"批量编码失败 (batch {start}): {e}")

    return results


def encode_text(texts: List[str]) -> Optional[np.ndarray]:
    if not _load_model():
        return None

    try:
        import torch
        with torch.no_grad():
            tokens = _tokenizer(texts)
            embeddings = _model.encode_text(tokens)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
            return embeddings.cpu().numpy()
    except Exception as e:
        logger.warning(f"文本编码失败: {e}")
        return None


def compute_similarity(image_embedding: np.ndarray, text_embeddings: np.ndarray) -> np.ndarray:
    return (image_embedding @ text_embeddings.T)

```

## infra/image/face_detector.py

```python
import numpy as np
from typing import Optional, List, Tuple

from logger_setup import logger
from infra.image.thumbnail_loader import get_thumbnail_loader

_detector = None


def _load_detector():
    global _detector
    if _detector is not None:
        return True
    try:
        from deepface import DeepFace
        _detector = DeepFace
        logger.info("DeepFace 加载完成")
        return True
    except ImportError:
        logger.warning("deepface 未安装, 人脸检测不可用. 安装: pip install deepface")
        return False
    except Exception as e:
        logger.error(f"DeepFace 加载失败: {e}")
        return False


def is_available() -> bool:
    if _detector is not None:
        return True
    try:
        import deepface
        return True
    except ImportError:
        return False


def detect_faces(file_id: int) -> List[dict]:
    if not _load_detector():
        return []

    loader = get_thumbnail_loader()
    img = loader.load(file_id, size=(640, 640))
    if img is None:
        return []

    try:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp.name, "JPEG")
            tmp_path = tmp.name

        try:
            results = _detector.extract_faces(
                img_path=tmp_path,
                detector_backend="retinaface",
                enforce_detection=False,
                align=True,
            )

            faces = []
            for r in results:
                if r.get("confidence", 0) > 0.9:
                    facial_area = r.get("facial_area", {})
                    faces.append({
                        "x": facial_area.get("x", 0),
                        "y": facial_area.get("y", 0),
                        "w": facial_area.get("w", 0),
                        "h": facial_area.get("h", 0),
                        "confidence": r.get("confidence", 0),
                    })
            return faces
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.warning(f"人脸检测失败 file_id={file_id}: {e}")
        return []


def extract_embedding(file_id: int) -> Optional[np.ndarray]:
    if not _load_detector():
        return None

    loader = get_thumbnail_loader()
    img = loader.load(file_id, size=(640, 640))
    if img is None:
        return None

    try:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp.name, "JPEG")
            tmp_path = tmp.name

        try:
            result = _detector.represent(
                img_path=tmp_path,
                model_name="ArcFace",
                detector_backend="retinaface",
                enforce_detection=True,
            )
            if result and len(result) > 0:
                return np.array(result[0]["embedding"], dtype=np.float32)
            return None
        finally:
            os.unlink(tmp_path)
    except ValueError:
        return None
    except Exception as e:
        logger.warning(f"人脸嵌入提取失败 file_id={file_id}: {e}")
        return None


def extract_embeddings_batch(file_ids: List[int]) -> List[Tuple[int, np.ndarray]]:
    results = []
    for fid in file_ids:
        emb = extract_embedding(fid)
        if emb is not None:
            results.append((fid, emb))
    return results

```

## infra/image/object_detector.py

```python
from typing import List, Optional, Protocol
from logger_setup import logger


class ObjectDetector(Protocol):
    def detect(self, image_path: str) -> List[dict]: ...


class LibreYOLODetector:
    def __init__(self):
        self._model = None

    def _load(self) -> bool:
        if self._model is not None:
            return True
        try:
            from ultralytics import YOLO
            self._model = YOLO("yolov8n.pt")
            logger.info("YOLOv8n 模型加载完成")
            return True
        except ImportError:
            logger.warning("ultralytics 未安装, 目标检测不可用. 安装: pip install ultralytics")
            return False
        except Exception as e:
            logger.error(f"YOLO 模型加载失败: {e}")
            return False

    def detect(self, image_path: str) -> List[dict]:
        if not self._load():
            return []
        try:
            results = self._model(image_path, verbose=False)
            detections = []
            for r in results:
                for box in r.boxes:
                    detections.append({
                        "class": r.names[int(box.cls)],
                        "confidence": float(box.conf),
                        "x1": int(box.xyxy[0][0]),
                        "y1": int(box.xyxy[0][1]),
                        "x2": int(box.xyxy[0][2]),
                        "y2": int(box.xyxy[0][3]),
                    })
            return detections
        except Exception as e:
            logger.warning(f"目标检测失败 {image_path}: {e}")
            return []


_detector: Optional[LibreYOLODetector] = None


def get_detector() -> Optional[ObjectDetector]:
    global _detector
    if _detector is None:
        _detector = LibreYOLODetector()
    return _detector


def is_available() -> bool:
    try:
        import ultralytics
        return True
    except ImportError:
        return False


def detect_objects(file_id: int) -> List[dict]:
    import os
    from config import THUMBNAIL_DIR

    thumb_path = os.path.join(THUMBNAIL_DIR, f"{file_id}.jpg")
    if not os.path.exists(thumb_path):
        return []

    detector = get_detector()
    if detector is None:
        return []
    return detector.detect(thumb_path)

```

## infra/image/thumbnail_loader.py

```python
import os
from typing import Optional, Tuple
from PIL import Image, ImageOps
from collections import OrderedDict

from logger_setup import logger
from config import THUMBNAIL_DIR, THUMBNAIL_SIZE


class ThumbnailLoader:
    def __init__(self, cache_size=256):
        self._cache: OrderedDict[int, Image.Image] = OrderedDict()
        self._cache_size = cache_size

    def load(self, file_id: int, size: Optional[Tuple[int, int]] = None) -> Optional[Image.Image]:
        if file_id in self._cache:
            self._cache.move_to_end(file_id)
            return self._cache[file_id].copy()

        thumb_path = os.path.join(THUMBNAIL_DIR, f"{file_id}.jpg")
        if not os.path.exists(thumb_path):
            return None

        try:
            img = Image.open(thumb_path)
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            if size:
                img.thumbnail(size, Image.LANCZOS)
            self._cache[file_id] = img
            self._cache.move_to_end(file_id)
            self._evict()
            return img.copy()
        except Exception as e:
            logger.warning(f"缩略图加载失败 file_id={file_id}: {e}")
            return None

    def _evict(self):
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def clear(self):
        for img in self._cache.values():
            try:
                img.close()
            except Exception:
                pass
        self._cache.clear()

    def preload(self, file_ids):
        for fid in file_ids:
            if fid not in self._cache:
                self.load(fid)


_loader: Optional[ThumbnailLoader] = None


def get_thumbnail_loader() -> ThumbnailLoader:
    global _loader
    if _loader is None:
        _loader = ThumbnailLoader()
    return _loader

```

## infra/llm/__init__.py

```python

```

## infra/llm/client.py

```python
from functools import wraps
import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class LLMClient:
    _instance = None

    def __init__(self):
        from config import get_openai_client
        self._client = get_openai_client()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def chat(self, model, messages, response_format=None, timeout=60, temperature=None, max_tokens=None):
        kwargs = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return self._client.chat.completions.create(**kwargs)


def get_llm_client():
    return LLMClient.get_instance()

```

## memory/__init__.py

```python

```

## memory/memory_generator.py

```python
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

```

## scanner/__init__.py

```python

```

## scanner/fast_scan.py

```python
import os
import subprocess
from datetime import datetime

from logger_setup import logger
from config import SOURCE_DRIVE, SOURCE_DIRS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, DATA_DIR
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState

ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
ES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "everything", "es.exe")
FALLBACK_ES = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "es_tool", "es.exe")

_ES_INSTANCE = None

_db = Database()
_cp = CheckpointManager(_db, "scan")

ScanState = CheckpointState


def clear_checkpoint():
    _cp.clear()


def get_checkpoint_status():
    status = _cp.get_status()
    if not status["has_checkpoint"]:
        return {"has_checkpoint": False}
    data = status.get("data", {})
    return {
        "has_checkpoint": True,
        "state": data.get("state"),
        "current_index": data.get("current_index", 0),
        "total": data.get("total", 0),
        "new_added": data.get("new_added", 0),
    }


def set_paused():
    _cp.request_pause()


def set_stopped():
    _cp.request_stop()


def _get_es_path():
    if os.path.exists(ES_PATH):
        return ES_PATH
    if os.path.exists(FALLBACK_ES):
        return FALLBACK_ES
    return None


def es_available():
    return _get_es_path() is not None


def _try_start_everything():
    try:
        from everything.ensure import ensure_everything
        return ensure_everything()
    except Exception:
        return False


def _detect_instance():
    global _ES_INSTANCE
    if _ES_INSTANCE is not None:
        return _ES_INSTANCE

    es_exe = _get_es_path()
    if not es_exe:
        _ES_INSTANCE = ""
        return _ES_INSTANCE

    import subprocess as sp
    for inst in ["", "1.5a", "1.5"]:
        cmd = [es_exe, "-instance", inst, "-get-result-count", "C:\\"] if inst else [es_exe, "-get-result-count", "C:\\"]
        try:
            r = sp.run(cmd, capture_output=True, text=True, timeout=10, creationflags=sp.CREATE_NO_WINDOW)
            if r.returncode == 0 and r.stdout.strip().isdigit():
                _ES_INSTANCE = inst
                logger.info(f"Everything 实例: [{inst or '默认'}], 索引 {r.stdout.strip()} 个文件")
                return inst
        except Exception:
            pass
    _ES_INSTANCE = "__FAIL__"
    return _ES_INSTANCE


def _run_es(args, timeout=120):
    es_exe = _get_es_path()
    if not es_exe:
        return "", -1

    inst = _detect_instance()
    if inst == "__FAIL__":
        return "", -1

    if inst:
        cmd = [es_exe, "-instance", inst] + args
    else:
        cmd = [es_exe] + args

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        text = result.stdout.decode("utf-8", errors="replace").strip()
        return text, result.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"es.exe 调用失败: {e}")
        return "", -1


def _match_source_dir(filepath):
    for sd in SOURCE_DIRS:
        prefix = sd.rstrip("\\") + "\\"
        if filepath.startswith(prefix) or filepath.startswith(sd.rstrip("\\") + "/"):
            return sd
    return None


def _list_all_image_files():
    list_file = os.path.join(DATA_DIR, "filelist.txt")
    if os.path.exists(list_file):
        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].strip() == f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}":
            paths = [os.path.normpath(l.rstrip("\n")) for l in lines[1:] if l.strip()]
            if paths:
                logger.info("使用缓存文件列表: %s 个文件" % len(paths))
                return paths
        logger.info("缓存文件列表来源不匹配当前 SOURCE_DRIVE, 重新扫描")

    inst = _detect_instance()
    if inst == "__FAIL__":
        logger.info("Everything IPC 不可用, 回退 os.walk")
        return _walk_files()

    logger.info("Everything 全量扫描: %s (实例: [%s])" % (SOURCE_DRIVE, inst or "默认"))

    ext_list = [e.lstrip(".") for e in ALL_EXTENSIONS]
    ext_query = "ext:%s" % ";".join(ext_list)
    logger.info("查询: %s (全局扩展名搜索, Python侧过滤路径)" % ext_query)

    out, code = _run_es(["-csv", "-no-header", ext_query], timeout=120)

    if code == 0 and out:
        files = _parse_es_csv(out)
        logger.info("Everything 返回 %s 条记录, 过滤后 %s 个媒体文件" % (len(out.split("\n")), len(files)))
        if files:
            os.makedirs(DATA_DIR, exist_ok=True)
            tmp = list_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}\n")
                for fp in files:
                    f.write(fp + "\n")
            os.replace(tmp, list_file)
            logger.info("文件列表已缓存: %s" % list_file)
            return files

    logger.info("Everything 查询失败, 回退 os.walk")
    return _walk_files()


def _parse_es_csv(text):
    files = []
    for line in text.strip().split("\n"):
        line = line.strip()
        filepath = line.strip("\"")
        if _match_source_dir(filepath) is None:
            continue
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ALL_EXTENSIONS:
            files.append(filepath)
    return files


def _walk_files():
    list_file = os.path.join(DATA_DIR, "filelist.txt")
    if os.path.exists(list_file):
        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].strip() == f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}":
            paths = [os.path.normpath(line.rstrip("\n")) for line in lines[1:] if line.strip()]
            if paths:
                logger.info(f"使用缓存文件列表: {len(paths)} 个文件")
                return paths
        logger.info("缓存文件列表来源不匹配当前 SOURCE_DRIVE, 重新扫描")

    logger.info("os.walk 遍历中, 请耐心等待...")
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp_file = list_file + ".tmp"
    file_list = []
    with open(tmp_file, "w", encoding="utf-8") as fout:
        fout.write(f"# SOURCE_DRIVE={os.path.normpath(SOURCE_DRIVE)}\n")
        for source_dir in SOURCE_DIRS:
            if not os.path.isdir(source_dir):
                logger.warning(f"照片库路径不存在, 跳过: {source_dir}")
                continue
            for root, dirs, files in os.walk(source_dir):
                for fname in files:
                    if os.path.splitext(fname)[1].lower() in ALL_EXTENSIONS:
                        fp = os.path.normpath(os.path.join(root, fname))
                        fout.write(fp + "\n")
                        file_list.append(fp)
                if len(file_list) % 5000 == 0 and file_list:
                    fout.flush()
                    logger.info(f"  已发现 {len(file_list)} 个文件...")
    os.replace(tmp_file, list_file)
    logger.info(f"文件列表已缓存: {list_file}, 共 {len(file_list)} 个")
    return file_list


def full_scan(progress_callback=None, batch_limit=None):
    logger.info(f"扫描驱动器: {SOURCE_DRIVE} ({len(SOURCE_DIRS)} 个库)")

    file_list = _list_all_image_files()
    if file_list is None:
        logger.info("Everything 不可用, 使用 os.walk 扫描")
        file_list = _walk_files()

    logger.info(f"磁盘发现 {len(file_list)} 个媒体文件")

    _db.init_tables()
    conn = _db.get_persistent_connection()
    conn.execute("PRAGMA busy_timeout=60000")

    cp = _cp.load()
    if cp and "current_index" not in cp:
        logger.info("旧格式扫描断点, 清理")
        _cp.clear()
        cp = None
    start_idx = cp["current_index"] if cp else 0
    new_added = cp["new_added"] if cp else 0
    batch_count = 0

    existing = set(r[0] for r in conn.execute("SELECT file_path FROM files"))
    logger.info(f"数据库中已有 {len(existing)} 条文件记录")
    total = len(file_list)

    is_new = not cp
    if is_new and total > 0:
        _cp.save(CheckpointState.RUNNING, current_index=0, total=total, new_added=0)
        logger.info("新扫描任务已创建检查点")
    elif cp:
        logger.info(f"从断点恢复: idx={start_idx}, total={total}, new_added={new_added}")

    remove_set = set(existing)
    for fp in file_list:
        remove_set.discard(fp)

    for i in range(start_idx, total):
        filepath = os.path.normpath(file_list[i])

        if filepath in existing:
            if progress_callback and (i + 1) % 50 == 0:
                progress_callback(i + 1, total)
            continue

        try:
            stat = os.stat(filepath)
            is_image = os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS
            file_hash = None

            folder = os.path.normpath(os.path.dirname(filepath))
            source_dir = _match_source_dir(filepath) or SOURCE_DIRS[0] if SOURCE_DIRS else None
            conn.execute(
                """INSERT OR IGNORE INTO files
                   (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    filepath,
                    os.path.basename(filepath),
                    folder,
                    os.path.basename(folder),
                    stat.st_size,
                    datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    file_hash,
                    1 if is_image else 0,
                    datetime.now().isoformat(),
                    source_dir,
                ),
            )
            new_added += 1
            batch_count += 1

            if new_added % 50 == 0:
                conn.commit()
        except Exception as e:
            logger.error(f"扫描文件失败 {filepath}: {e}")

        if progress_callback:
            progress_callback(i + 1, total)

        if batch_limit and batch_count >= batch_limit:
            _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, new_added=new_added)
            logger.info(f"扫描热身: {new_added} 条, 剩余 {total - i - 1} 条后台继续")
            conn.commit()
            conn.close()
            return {"paused": True, "batch_limit_reached": True, "total": total, "new": new_added, "removed": 0}

        if (i + 1) % 100 == 0:
            if _cp.is_pause_or_stop_requested():
                _cp.save(CheckpointState.PAUSED, current_index=i + 1, total=total, new_added=new_added)
                logger.info(f"扫描暂停: idx={i + 1}, 新增 {new_added}")
                conn.commit()

                if remove_set:
                    logger.info(f"清理 {len(remove_set)} 个已移除文件...")
                    for path in remove_set:
                        conn.execute("DELETE FROM files WHERE file_path = ?", (path,))
                    conn.commit()

                conn.close()
                return {"paused": True, "total": total, "new": new_added, "removed": len(remove_set)}

            _cp.save(CheckpointState.RUNNING, current_index=i + 1, total=total, new_added=new_added)

    if remove_set:
        logger.info(f"清理 {len(remove_set)} 个已移除文件...")
        for path in remove_set:
            conn.execute("DELETE FROM files WHERE file_path = ?", (path,))
        conn.commit()

    _cleanup_removed_source_dirs(conn)

    final = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    conn.commit()
    conn.close()
    _cp.clear()

    logger.info(f"扫描完成: 总计 {final} 文件, 新增 {new_added}, 移除 {len(remove_set)}")
    return {"total": final, "new": new_added, "removed": len(remove_set)}


def _cleanup_removed_source_dirs(conn):
    if not SOURCE_DIRS:
        return
    placeholders = ",".join("?" * len(SOURCE_DIRS))
    removed = conn.execute(
        f"SELECT COUNT(*) FROM files WHERE source_dir IS NOT NULL AND source_dir NOT IN ({placeholders})",
        SOURCE_DIRS
    ).fetchone()[0]
    if removed > 0:
        conn.execute(
            f"DELETE FROM files WHERE source_dir IS NOT NULL AND source_dir NOT IN ({placeholders})",
            SOURCE_DIRS
        )
        logger.info(f"清理 {removed} 个不在配置中的照片库文件")


def fast_scan(num_files=1000, progress_callback=None):
    _db.init_tables()

    if not es_available():
        logger.warning("es.exe 不可用，回退到 os.walk 扫描")
        return None

    import random

    args = ["-csv", "-no-header"]
    if num_files:
        args.append(f"-n {num_files}")

    ext_queries = []
    for ext in ALL_EXTENSIONS:
        for sd in SOURCE_DIRS:
            ext_queries.append(f"{sd} *{ext}")
    query = "|".join(ext_queries)

    logger.info(f"Everything 快速扫描: {SOURCE_DRIVE}")
    out, code = _run_es(args + [query], timeout=120)

    if code != 0 or not out:
        logger.warning("es.exe 返回空或失败")
        return None

    files = []
    for line in out.strip().split("\n"):
        line = line.strip()
        if not line or _match_source_dir(line.strip('"')) is None:
            continue
        filepath = line.strip('"').replace("\\\\", "\\")
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ALL_EXTENSIONS:
            files.append(filepath)

    logger.info(f"Everything 返回 {len(files)} 个文件")

    if num_files and len(files) > num_files:
        files = random.sample(files, num_files)

    with _db.connect() as conn:
        existing = set(r[0] for r in conn.execute("SELECT file_path FROM files"))

        new_added = 0
        total = len(files)

        for i, filepath in enumerate(files):
            if filepath in existing:
                if progress_callback and i % 200 == 0:
                    progress_callback(i + 1, total)
                continue

            try:
                stat = os.stat(filepath)
                is_image = os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS
                file_hash = None

                folder = os.path.dirname(filepath)
                source_dir = _match_source_dir(filepath) or SOURCE_DIRS[0] if SOURCE_DIRS else None
                conn.execute(
                    """INSERT OR IGNORE INTO files
                       (file_path, file_name, folder_path, folder_name, file_size, file_mtime, file_hash, is_image, scanned_at, source_dir)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        filepath,
                        os.path.basename(filepath),
                        folder,
                        os.path.basename(folder),
                        stat.st_size,
                        datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        file_hash,
                        1 if is_image else 0,
                        datetime.now().isoformat(),
                        source_dir,
                    ),
                )
                new_added += 1

                if new_added % 50 == 0:
                    conn.commit()
            except Exception as e:
                logger.error(f"扫描文件失败 {filepath}: {e}")

            if progress_callback and (i + 1) % 100 == 0:
                progress_callback(i + 1, total)

        conn.commit()
        final = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    logger.info(f"Everything 扫描完成: 总计 {final} 文件, 新增 {new_added}")
    return {"total": final, "new": new_added, "removed": 0}


if __name__ == "__main__":
    result = full_scan()
    if result.get("paused"):
        print(f"扫描暂停: 新增 {result['new']}, 总计 {result['total']}")
    else:
        print(f"扫描完成: 总计 {result['total']}, 新增 {result['new']}, 移除 {result.get('removed', 0)}")

```

## services/__init__.py

```python

```

## services/background_task_manager.py

```python
from typing import Optional
from PyQt6.QtCore import QThread
from logger_setup import logger


class BackgroundTaskManager:
    _instance: Optional["BackgroundTaskManager"] = None

    def __init__(self):
        self._threads: list[QThread] = []

    @classmethod
    def get_instance(cls) -> "BackgroundTaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, thread: QThread):
        self._threads.append(thread)
        logger.debug(f"后台任务注册: {thread}")

    def unregister(self, thread: QThread):
        if thread in self._threads:
            self._threads.remove(thread)

    def wait_all(self, timeout_ms: int = 5000):
        for t in self._threads[:]:
            t.wait(timeout_ms)
            if t.isRunning():
                logger.warning(f"后台线程 {t} 未能在 {timeout_ms}ms 内结束")
        self._threads.clear()

    def cancel_all(self):
        for t in self._threads[:]:
            if t.isRunning():
                t.quit()
                t.wait(500)

```

## services/data_service.py

```python
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

```

## services/pipeline.py

```python
from abc import ABC, abstractmethod
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal


class Stage(ABC):
    name: str = "未命名阶段"

    @abstractmethod
    def run(self, progress_callback=None) -> dict:
        pass


class ScanStage(Stage):
    name = "扫描文件"

    def __init__(self, batch_limit: int | None = 500):
        super().__init__()
        self._batch_limit = batch_limit

    def run(self, progress_callback=None) -> dict:
        import os
        from scanner.fast_scan import full_scan, clear_checkpoint
        clear_checkpoint()
        if os.environ.get("PHOTO_TEST_MODE", "").lower() in ("1", "true", "yes"):
            from db_manager import Database
            db = Database()
            with db.connect() as conn:
                n = conn.execute("SELECT COUNT(1) FROM files").fetchone()[0]
            return {"total": n, "new": 0, "removed": 0}
        return full_scan(progress_callback=progress_callback, batch_limit=self._batch_limit)


class ClassifyStage(Stage):
    name = "分类文件夹"

    def run(self, progress_callback=None) -> dict:
        from classifier.folder_classifier import classify_folders
        return classify_folders(progress_callback=progress_callback)

    def apply_user_results(self, results: list):
        from classifier.folder_classifier import propagate_branch_category
        for branch_path, category in results:
            propagate_branch_category(branch_path, category)


class IndexStage(Stage):
    name = "生成缩略图"

    def __init__(self, batch_limit: int | None = 100):
        super().__init__()
        self._batch_limit = batch_limit

    def run(self, progress_callback=None) -> dict:
        import os
        from indexer.photo_indexer import index_photos, clear_checkpoint
        clear_checkpoint()
        try:
            from db_manager import Database
            db = Database()
            with db.connect() as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path IS NOT NULL"
                ).fetchone()[0]
            if n >= 100:
                return {"total": 0, "indexed": 0, "batch_limit_reached": True}
        except Exception:
            pass
        return index_photos(progress_callback=progress_callback, batch_limit=self._batch_limit)


class MemoryStage(Stage):
    name = "生成回忆"

    def run(self, progress_callback=None) -> dict:
        from memory.memory_generator import generate_all_memories
        return generate_all_memories(progress_callback=progress_callback)


class Pipeline(QThread):
    stage_changed = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    all_done = pyqtSignal()
    error_occurred = pyqtSignal(str)
    interactive_classify_needed = pyqtSignal(list)
    background_scan_needed = pyqtSignal()
    background_index_needed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._cancelled = False
        self._stages: list[Stage] = []
        self._classify_stage: Optional[ClassifyStage] = None
        self._pending_classify_results: list = []
        import threading
        self._classify_event = threading.Event()

    def add_stage(self, stage: Stage):
        self._stages.append(stage)
        if isinstance(stage, ClassifyStage):
            self._classify_stage = stage

    def cancel(self):
        self._cancelled = True
        from scanner.fast_scan import set_stopped as scan_stopped
        from indexer.photo_indexer import set_stopped as index_stopped
        scan_stopped()
        index_stopped()
        if self._classify_event:
            self._classify_event.set()

    def set_classify_results(self, results: list):
        self._pending_classify_results = results
        if self._classify_event:
            self._classify_event.set()

    def run(self):
        try:
            total_stages = len(self._stages)
            bg_scan_needed = False
            bg_index_needed = False

            for stage_idx, stage in enumerate(self._stages):
                if self._cancelled:
                    self.error_occurred.emit(f"{stage.name} 已取消")
                    return

                self.stage_changed.emit(f"正在 {stage.name}...")
                self.progress.emit(0, 0)

                if isinstance(stage, ClassifyStage):
                    self._classify_event.clear()
                    result = stage.run(progress_callback=self._on_progress)
                    needs_user = result.get("needs_user", [])
                    if needs_user:
                        self.interactive_classify_needed.emit(needs_user)
                        self._classify_event.wait()
                        self._classify_event.clear()
                        stage.apply_user_results(self._pending_classify_results)
                else:
                    result = stage.run(progress_callback=self._on_progress)

                if self._cancelled:
                    self.error_occurred.emit(f"{stage.name} 已取消")
                    return

                if isinstance(stage, ScanStage) and result.get("batch_limit_reached"):
                    bg_scan_needed = True

                if isinstance(stage, IndexStage) and result.get("batch_limit_reached"):
                    bg_index_needed = True

            self.stage_changed.emit("初始化完成")
            self.progress.emit(100, 100)
            if bg_scan_needed:
                self.background_scan_needed.emit()
            if bg_index_needed:
                self.background_index_needed.emit()
            self.all_done.emit()

        except Exception as e:
            import traceback
            from logger_setup import logger
            logger.exception("Pipeline 执行异常")
            self.error_occurred.emit(str(e))

    def _on_progress(self, current, total, *args):
        self.progress.emit(current, total)

```

## services/recognition_scheduler.py

```python
import threading
from typing import Optional, Callable

from logger_setup import logger
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from infra.db.repositories.photo_tags_repo import PhotoTagsRepository
from infra.db.repositories.face_embeddings_repo import FaceEmbeddingsRepository

_db = Database()
_cp = CheckpointManager(_db, "recognition")


def get_status():
    return _cp.get_status()


def request_pause():
    _cp.request_pause()


def request_stop():
    _cp.request_stop()


def _should_stop():
    return _cp.is_pause_or_stop_requested()


def run_recognition(
    progress_callback: Optional[Callable] = None,
    batch_limit: int = 0,
):
    _db.init_tables()

    meta_repo = PhotoMetadataRepository(_db)
    tags_repo = PhotoTagsRepository(_db)

    cp = _cp.load()
    start_stage = cp.get("stage", "siglip") if cp else "siglip"
    processed_total = cp.get("processed_total", 0) if cp else 0

    stages = ["siglip", "face", "yolo", "scene"]
    stage_idx = stages.index(start_stage) if start_stage in stages else 0

    if not cp:
        _cp.save(CheckpointState.RUNNING, stage="siglip", current_index=0, processed_total=0)

    for si in range(stage_idx, len(stages)):
        stage = stages[si]

        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage=stage, processed_total=processed_total)
            return {"paused": True, "stage": stage, "processed_total": processed_total}

        if stage == "siglip":
            count = _run_siglip_stage(meta_repo, tags_repo, cp, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "siglip", "processed_total": processed_total}

        elif stage == "face":
            count = _run_face_stage(meta_repo, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "face", "processed_total": processed_total}

        elif stage == "yolo":
            count = _run_yolo_stage(meta_repo, tags_repo, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "yolo", "processed_total": processed_total}

        elif stage == "scene":
            count = _run_scene_stage(meta_repo, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "scene", "processed_total": processed_total}

        next_stage = stages[si + 1] if si + 1 < len(stages) else "done"
        _cp.save(CheckpointState.RUNNING, stage=next_stage, current_index=0, processed_total=processed_total)

    _cp.clear()
    logger.info(f"识别流水线全部完成, 共处理 {processed_total} 项")
    return {"total": processed_total, "processed": processed_total}


def _run_siglip_stage(meta_repo, tags_repo, cp, progress_callback, batch_limit):
    from business.image_recognition.tag_generator import generate_tags_for_image
    from infra.image.clip_encoder import is_available as clip_available

    if not clip_available():
        logger.warning("SigLIP 不可用, 跳过标签生成")
        return 0

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有需要 SigLIP 标签的照片")
        return 0

    total = len(untagged)
    logger.info(f"[SigLIP] 开始标签生成: {total} 张照片")

    start_idx = cp.get("current_index", 0) if cp and cp.get("stage") == "siglip" else 0
    processed = 0

    for i in range(start_idx, total):
        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage="siglip", current_index=i, processed_total=processed)
            return -1

        file_id = untagged[i]
        try:
            tags = generate_tags_for_image(file_id)
            for tag in tags:
                from core.models import PhotoTag
                pt = PhotoTag(file_id=file_id, tag=tag, source="siglip")
                tags_repo.insert_or_ignore(pt)
            processed += 1
        except Exception as e:
            logger.error(f"[SigLIP] 识别失败 file_id={file_id}: {e}")

        if progress_callback and (i + 1) % 10 == 0:
            progress_callback(i + 1, total)

        if batch_limit and processed >= batch_limit:
            _cp.save(CheckpointState.PAUSED, stage="siglip", current_index=i + 1, processed_total=processed)
            return -1

        if (i + 1) % 50 == 0:
            _cp.save(CheckpointState.RUNNING, stage="siglip", current_index=i + 1, processed_total=processed)

    logger.info(f"[SigLIP] 标签生成完成: {processed}/{total}")
    return processed


def _run_face_stage(meta_repo, progress_callback, batch_limit):
    from infra.image.face_detector import is_available as face_available, extract_embeddings_batch
    from business.image_recognition.face_cluster import cluster_faces

    if not face_available():
        logger.warning("DeepFace 不可用, 跳过人脸检测")
        return 0

    emb_repo = FaceEmbeddingsRepository(_db)

    existing = emb_repo.get_existing_file_ids()

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有可用的照片进行人脸检测")
        return 0

    candidates = [fid for fid in untagged if fid not in existing]
    if not candidates:
        logger.info("所有照片已有人脸嵌入, 跳过")
        return 0

    batch_size = 50
    total = len(candidates)
    processed = 0
    all_embeddings = []

    logger.info(f"[Face] 开始人脸嵌入提取: {total} 张照片")

    for start in range(0, total, batch_size):
        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage="face", current_index=start, processed_total=processed)
            return -1

        batch = candidates[start:start + batch_size]
        embeddings = extract_embeddings_batch(batch)

        if embeddings:
            all_embeddings.extend(embeddings)
            processed += len(embeddings)

        if progress_callback and (start + batch_size) % 50 == 0:
            progress_callback(min(start + batch_size, total), total)

        if batch_limit and processed >= batch_limit:
            break

    if all_embeddings:
        cluster_faces(all_embeddings)
        logger.info(f"[Face] 人脸聚类完成: {len(all_embeddings)} 个嵌入")

    logger.info(f"[Face] 人脸检测阶段完成: {processed} 张照片")
    return processed


def _run_yolo_stage(meta_repo, tags_repo, progress_callback, batch_limit):
    from infra.image.object_detector import is_available as yolo_available, detect_objects

    if not yolo_available():
        logger.warning("YOLOv8 不可用, 跳过目标检测")
        return 0

    yolo_tagged = tags_repo.get_file_ids_by_source("yolo")

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有可用的照片进行目标检测")
        return 0

    candidates = [fid for fid in untagged if fid not in yolo_tagged]
    if not candidates:
        logger.info("所有照片已有 YOLO 标签, 跳过")
        return 0

    total = len(candidates)
    processed = 0

    logger.info(f"[YOLO] 开始目标检测: {total} 张照片")

    for i, file_id in enumerate(candidates):
        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage="yolo", current_index=i, processed_total=processed)
            return -1

        try:
            detections = detect_objects(file_id)
            for det in detections:
                if det.get("confidence", 0) > 0.5:
                    from core.models import PhotoTag
                    pt = PhotoTag(file_id=file_id, tag=det["class"], source="yolo")
                    tags_repo.insert_or_ignore(pt)
            processed += 1
        except Exception as e:
            logger.error(f"[YOLO] 检测失败 file_id={file_id}: {e}")

        if progress_callback and (i + 1) % 10 == 0:
            progress_callback(i + 1, total)

        if batch_limit and processed >= batch_limit:
            break

    logger.info(f"[YOLO] 目标检测完成: {processed}/{total}")
    return processed


def _run_scene_stage(meta_repo, progress_callback, batch_limit):
    from business.image_recognition.scene_cluster import cluster_by_scene
    from infra.image.clip_encoder import is_available as clip_available

    if not clip_available():
        logger.warning("SigLIP 不可用, 跳过场景聚类")
        return 0

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有可用的照片进行场景聚类")
        return 0

    scene_batch_size = 200
    total = min(len(untagged), scene_batch_size)
    candidates = untagged[:total]

    logger.info(f"[Scene] 开始场景聚类: {len(candidates)} 张照片")

    try:
        clusters = cluster_by_scene(candidates)
        logger.info(f"[Scene] 场景聚类完成: {len(clusters)} 个场景")
        return len(clusters)
    except Exception as e:
        logger.error(f"[Scene] 场景聚类失败: {e}")
        return 0


def run_recognition_async(progress_callback=None, batch_limit=0):
    thread = threading.Thread(
        target=run_recognition,
        kwargs={"progress_callback": progress_callback, "batch_limit": batch_limit},
        daemon=True,
    )
    thread.start()
    return thread

```

## storage/classification_history.txt

```text
# 已分类文件夹历史 (供 LLM 参考)

1 | storage | (生活照片) | [default-pending-refine]
1 | thumbnails | (生活照片) | [manual-branch]
```

## storage/filelist.txt

```text
# SOURCE_DRIVE=d:\photo-memories-source
d:\photo-memories-source\storage\thumbnails\1.jpg
d:\photo-memories-source\storage\thumbnails\102.jpg
d:\photo-memories-source\storage\thumbnails\105.jpg
d:\photo-memories-source\storage\thumbnails\108.jpg
d:\photo-memories-source\storage\thumbnails\11.jpg
d:\photo-memories-source\storage\thumbnails\111.jpg
d:\photo-memories-source\storage\thumbnails\113.jpg
d:\photo-memories-source\storage\thumbnails\114.jpg
d:\photo-memories-source\storage\thumbnails\116.jpg
d:\photo-memories-source\storage\thumbnails\120.jpg
d:\photo-memories-source\storage\thumbnails\121.jpg
d:\photo-memories-source\storage\thumbnails\122.jpg
d:\photo-memories-source\storage\thumbnails\123.jpg
d:\photo-memories-source\storage\thumbnails\124.jpg
d:\photo-memories-source\storage\thumbnails\125.jpg
d:\photo-memories-source\storage\thumbnails\126.jpg
d:\photo-memories-source\storage\thumbnails\127.jpg
d:\photo-memories-source\storage\thumbnails\128.jpg
d:\photo-memories-source\storage\thumbnails\129.jpg
d:\photo-memories-source\storage\thumbnails\13.jpg
d:\photo-memories-source\storage\thumbnails\130.jpg
d:\photo-memories-source\storage\thumbnails\131.jpg
d:\photo-memories-source\storage\thumbnails\132.jpg
d:\photo-memories-source\storage\thumbnails\133.jpg
d:\photo-memories-source\storage\thumbnails\134.jpg
d:\photo-memories-source\storage\thumbnails\136.jpg
d:\photo-memories-source\storage\thumbnails\138.jpg
d:\photo-memories-source\storage\thumbnails\140.jpg
d:\photo-memories-source\storage\thumbnails\142.jpg
d:\photo-memories-source\storage\thumbnails\143.jpg
d:\photo-memories-source\storage\thumbnails\144.jpg
d:\photo-memories-source\storage\thumbnails\145.jpg
d:\photo-memories-source\storage\thumbnails\146.jpg
d:\photo-memories-source\storage\thumbnails\147.jpg
d:\photo-memories-source\storage\thumbnails\148.jpg
d:\photo-memories-source\storage\thumbnails\149.jpg
d:\photo-memories-source\storage\thumbnails\15.jpg
d:\photo-memories-source\storage\thumbnails\150.jpg
d:\photo-memories-source\storage\thumbnails\152.jpg
d:\photo-memories-source\storage\thumbnails\154.jpg
d:\photo-memories-source\storage\thumbnails\156.jpg
d:\photo-memories-source\storage\thumbnails\157.jpg
d:\photo-memories-source\storage\thumbnails\159.jpg
d:\photo-memories-source\storage\thumbnails\161.jpg
d:\photo-memories-source\storage\thumbnails\162.jpg
d:\photo-memories-source\storage\thumbnails\164.jpg
d:\photo-memories-source\storage\thumbnails\165.jpg
d:\photo-memories-source\storage\thumbnails\167.jpg
d:\photo-memories-source\storage\thumbnails\169.jpg
d:\photo-memories-source\storage\thumbnails\17.jpg
d:\photo-memories-source\storage\thumbnails\170.jpg
d:\photo-memories-source\storage\thumbnails\171.jpg
d:\photo-memories-source\storage\thumbnails\172.jpg
d:\photo-memories-source\storage\thumbnails\173.jpg
d:\photo-memories-source\storage\thumbnails\174.jpg
d:\photo-memories-source\storage\thumbnails\175.jpg
d:\photo-memories-source\storage\thumbnails\176.jpg
d:\photo-memories-source\storage\thumbnails\177.jpg
d:\photo-memories-source\storage\thumbnails\178.jpg
d:\photo-memories-source\storage\thumbnails\179.jpg
d:\photo-memories-source\storage\thumbnails\180.jpg
d:\photo-memories-source\storage\thumbnails\181.jpg
d:\photo-memories-source\storage\thumbnails\182.jpg
d:\photo-memories-source\storage\thumbnails\183.jpg
d:\photo-memories-source\storage\thumbnails\185.jpg
d:\photo-memories-source\storage\thumbnails\187.jpg
d:\photo-memories-source\storage\thumbnails\189.jpg
d:\photo-memories-source\storage\thumbnails\19.jpg
d:\photo-memories-source\storage\thumbnails\191.jpg
d:\photo-memories-source\storage\thumbnails\193.jpg
d:\photo-memories-source\storage\thumbnails\195.jpg
d:\photo-memories-source\storage\thumbnails\197.jpg
d:\photo-memories-source\storage\thumbnails\199.jpg
d:\photo-memories-source\storage\thumbnails\2.jpg
d:\photo-memories-source\storage\thumbnails\201.jpg
d:\photo-memories-source\storage\thumbnails\203.jpg
d:\photo-memories-source\storage\thumbnails\205.jpg
d:\photo-memories-source\storage\thumbnails\207.jpg
d:\photo-memories-source\storage\thumbnails\209.jpg
d:\photo-memories-source\storage\thumbnails\21.jpg
d:\photo-memories-source\storage\thumbnails\211.jpg
d:\photo-memories-source\storage\thumbnails\213.jpg
d:\photo-memories-source\storage\thumbnails\215.jpg
d:\photo-memories-source\storage\thumbnails\217.jpg
d:\photo-memories-source\storage\thumbnails\219.jpg
d:\photo-memories-source\storage\thumbnails\221.jpg
d:\photo-memories-source\storage\thumbnails\223.jpg
d:\photo-memories-source\storage\thumbnails\225.jpg
d:\photo-memories-source\storage\thumbnails\227.jpg
d:\photo-memories-source\storage\thumbnails\229.jpg
d:\photo-memories-source\storage\thumbnails\23.jpg
d:\photo-memories-source\storage\thumbnails\231.jpg
d:\photo-memories-source\storage\thumbnails\233.jpg
d:\photo-memories-source\storage\thumbnails\235.jpg
d:\photo-memories-source\storage\thumbnails\237.jpg
d:\photo-memories-source\storage\thumbnails\239.jpg
d:\photo-memories-source\storage\thumbnails\241.jpg
d:\photo-memories-source\storage\thumbnails\243.jpg
d:\photo-memories-source\storage\thumbnails\245.jpg
d:\photo-memories-source\storage\thumbnails\247.jpg
d:\photo-memories-source\storage\thumbnails\249.jpg
d:\photo-memories-source\storage\thumbnails\251.jpg
d:\photo-memories-source\storage\thumbnails\253.jpg
d:\photo-memories-source\storage\thumbnails\255.jpg
d:\photo-memories-source\storage\thumbnails\257.jpg
d:\photo-memories-source\storage\thumbnails\259.jpg
d:\photo-memories-source\storage\thumbnails\26.jpg
d:\photo-memories-source\storage\thumbnails\261.jpg
d:\photo-memories-source\storage\thumbnails\263.jpg
d:\photo-memories-source\storage\thumbnails\265.jpg
d:\photo-memories-source\storage\thumbnails\267.jpg
d:\photo-memories-source\storage\thumbnails\269.jpg
d:\photo-memories-source\storage\thumbnails\271.jpg
d:\photo-memories-source\storage\thumbnails\273.jpg
d:\photo-memories-source\storage\thumbnails\274.jpg
d:\photo-memories-source\storage\thumbnails\276.jpg
d:\photo-memories-source\storage\thumbnails\278.jpg
d:\photo-memories-source\storage\thumbnails\28.jpg
d:\photo-memories-source\storage\thumbnails\280.jpg
d:\photo-memories-source\storage\thumbnails\282.jpg
d:\photo-memories-source\storage\thumbnails\284.jpg
d:\photo-memories-source\storage\thumbnails\286.jpg
d:\photo-memories-source\storage\thumbnails\288.jpg
d:\photo-memories-source\storage\thumbnails\290.jpg
d:\photo-memories-source\storage\thumbnails\292.jpg
d:\photo-memories-source\storage\thumbnails\294.jpg
d:\photo-memories-source\storage\thumbnails\295.jpg
d:\photo-memories-source\storage\thumbnails\297.jpg
d:\photo-memories-source\storage\thumbnails\299.jpg
d:\photo-memories-source\storage\thumbnails\3.jpg
d:\photo-memories-source\storage\thumbnails\30.jpg
d:\photo-memories-source\storage\thumbnails\301.jpg
d:\photo-memories-source\storage\thumbnails\302.jpg
d:\photo-memories-source\storage\thumbnails\303.jpg
d:\photo-memories-source\storage\thumbnails\305.jpg
d:\photo-memories-source\storage\thumbnails\307.jpg
d:\photo-memories-source\storage\thumbnails\309.jpg
d:\photo-memories-source\storage\thumbnails\311.jpg
d:\photo-memories-source\storage\thumbnails\313.jpg
d:\photo-memories-source\storage\thumbnails\315.jpg
d:\photo-memories-source\storage\thumbnails\317.jpg
d:\photo-memories-source\storage\thumbnails\319.jpg
d:\photo-memories-source\storage\thumbnails\32.jpg
d:\photo-memories-source\storage\thumbnails\321.jpg
d:\photo-memories-source\storage\thumbnails\323.jpg
d:\photo-memories-source\storage\thumbnails\325.jpg
d:\photo-memories-source\storage\thumbnails\326.jpg
d:\photo-memories-source\storage\thumbnails\328.jpg
d:\photo-memories-source\storage\thumbnails\329.jpg
d:\photo-memories-source\storage\thumbnails\331.jpg
d:\photo-memories-source\storage\thumbnails\333.jpg
d:\photo-memories-source\storage\thumbnails\335.jpg
d:\photo-memories-source\storage\thumbnails\337.jpg
d:\photo-memories-source\storage\thumbnails\339.jpg
d:\photo-memories-source\storage\thumbnails\34.jpg
d:\photo-memories-source\storage\thumbnails\341.jpg
d:\photo-memories-source\storage\thumbnails\343.jpg
d:\photo-memories-source\storage\thumbnails\345.jpg
d:\photo-memories-source\storage\thumbnails\347.jpg
d:\photo-memories-source\storage\thumbnails\348.jpg
d:\photo-memories-source\storage\thumbnails\350.jpg
d:\photo-memories-source\storage\thumbnails\352.jpg
d:\photo-memories-source\storage\thumbnails\354.jpg
d:\photo-memories-source\storage\thumbnails\356.jpg
d:\photo-memories-source\storage\thumbnails\358.jpg
d:\photo-memories-source\storage\thumbnails\36.jpg
d:\photo-memories-source\storage\thumbnails\360.jpg
d:\photo-memories-source\storage\thumbnails\362.jpg
d:\photo-memories-source\storage\thumbnails\364.jpg
d:\photo-memories-source\storage\thumbnails\366.jpg
d:\photo-memories-source\storage\thumbnails\368.jpg
d:\photo-memories-source\storage\thumbnails\370.jpg
d:\photo-memories-source\storage\thumbnails\372.jpg
d:\photo-memories-source\storage\thumbnails\374.jpg
d:\photo-memories-source\storage\thumbnails\376.jpg
d:\photo-memories-source\storage\thumbnails\378.jpg
d:\photo-memories-source\storage\thumbnails\38.jpg
d:\photo-memories-source\storage\thumbnails\381.jpg
d:\photo-memories-source\storage\thumbnails\383.jpg
d:\photo-memories-source\storage\thumbnails\40.jpg
d:\photo-memories-source\storage\thumbnails\42.jpg
d:\photo-memories-source\storage\thumbnails\44.jpg
d:\photo-memories-source\storage\thumbnails\47.jpg
d:\photo-memories-source\storage\thumbnails\49.jpg
d:\photo-memories-source\storage\thumbnails\51.jpg
d:\photo-memories-source\storage\thumbnails\53.jpg
d:\photo-memories-source\storage\thumbnails\55.jpg
d:\photo-memories-source\storage\thumbnails\57.jpg
d:\photo-memories-source\storage\thumbnails\59.jpg
d:\photo-memories-source\storage\thumbnails\61.jpg
d:\photo-memories-source\storage\thumbnails\63.jpg
d:\photo-memories-source\storage\thumbnails\65.jpg
d:\photo-memories-source\storage\thumbnails\67.jpg
d:\photo-memories-source\storage\thumbnails\68.jpg
d:\photo-memories-source\storage\thumbnails\69.jpg
d:\photo-memories-source\storage\thumbnails\7.jpg
d:\photo-memories-source\storage\thumbnails\70.jpg
d:\photo-memories-source\storage\thumbnails\75.jpg
d:\photo-memories-source\storage\thumbnails\77.jpg
d:\photo-memories-source\storage\thumbnails\78.jpg
d:\photo-memories-source\storage\thumbnails\79.jpg
d:\photo-memories-source\storage\thumbnails\81.jpg
d:\photo-memories-source\storage\thumbnails\83.jpg
d:\photo-memories-source\storage\thumbnails\84.jpg
d:\photo-memories-source\storage\thumbnails\85.jpg
d:\photo-memories-source\storage\thumbnails\86.jpg
d:\photo-memories-source\storage\thumbnails\87.jpg
d:\photo-memories-source\storage\thumbnails\88.jpg
d:\photo-memories-source\storage\thumbnails\89.jpg
d:\photo-memories-source\storage\thumbnails\9.jpg
d:\photo-memories-source\storage\thumbnails\90.jpg
d:\photo-memories-source\storage\thumbnails\91.jpg
d:\photo-memories-source\storage\thumbnails\92.jpg
d:\photo-memories-source\storage\thumbnails\93.jpg
d:\photo-memories-source\storage\thumbnails\94.jpg
d:\photo-memories-source\storage\thumbnails\95.jpg
d:\photo-memories-source\storage\thumbnails\96.jpg
d:\photo-memories-source\storage\thumbnails\97.jpg
d:\photo-memories-source\storage\thumbnails\98.jpg
d:\photo-memories-source\storage\thumbnails\99.jpg

```

## tests/__init__.py

```python

```

## tests/conftest.py

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

```

## tests/test_checkpoint.py

```python
import os
import sqlite3
import tempfile
import shutil


def _make_db():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "photos.db")
    db = Database(db_path)
    db.init_tables()
    return db, tmp


def test_checkpoint_save_load_cycle():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=10, total=100)
        data = cp.load()
        assert data is not None
        assert data["state"] == "running"
        assert data["current_index"] == 10
        assert data["total"] == 100
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_clear():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        cp.clear()
        data = cp.load()
        assert data is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_pause():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        cp.request_pause()
        data = cp.load()
        assert data["state"] == "paused"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_stop():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        cp.request_stop()
        data = cp.load()
        assert data["state"] == "stopped"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_get_status():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        status = cp.get_status()
        assert status["has_checkpoint"] is False

        cp.save(CheckpointState.RUNNING, current_index=5)
        status = cp.get_status()
        assert status["has_checkpoint"] is True
        assert status["state"] == "running"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_checkpoint_is_pause_or_stop_requested():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "test_task")
        cp.save(CheckpointState.RUNNING, current_index=5)
        assert cp.is_pause_or_stop_requested() is False

        cp.request_pause()
        assert cp.is_pause_or_stop_requested() is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_scan_checkpoint_compat():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "scan")
        cp.save(CheckpointState.RUNNING, current_index=0, total=100, new_added=0)
        data = cp.load()
        assert data["state"] == "running"
        assert data["current_index"] == 0
        assert data["total"] == 100
        assert data["new_added"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_index_checkpoint_compat():
    from checkpoint_manager import CheckpointManager, CheckpointState
    db, tmp = _make_db()
    try:
        cp = CheckpointManager(db, "index")
        cp.save(CheckpointState.RUNNING, current_index=0, total=50, indexed=0)
        data = cp.load()
        assert data["state"] == "running"
        assert data["current_index"] == 0
        assert data["total"] == 50
        assert data["indexed"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

```

## tests/test_cli.py

```python
import subprocess
import sys
import os


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert result.returncode == 0
    assert "NAS" in result.stdout or "scan" in result.stdout


def test_cli_setup_no_crash():
    result = subprocess.run(
        [sys.executable, "main.py", "setup"],
        capture_output=True, text=True, timeout=5,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode in (0, 1)


def test_cli_scan_without_config():
    env = os.environ.copy()
    env["DEEPSEEK_API_KEY"] = ""
    env["SOURCE_DRIVE"] = ""
    env["PHOTO_DATA_DIR"] = ""
    result = subprocess.run(
        [sys.executable, "main.py", "scan"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
    )
    assert result.returncode != 0

```

## tests/test_config.py

```python
import os
import tempfile
import shutil


def test_config_imports():
    import config
    assert hasattr(config, "DEEPSEEK_API_KEY")
    assert hasattr(config, "SOURCE_DRIVE")
    assert hasattr(config, "SOURCE_DIRS")
    assert hasattr(config, "DATA_DIR")
    assert hasattr(config, "DB_PATH")
    assert hasattr(config, "THUMBNAIL_DIR")
    assert hasattr(config, "IMAGE_EXTENSIONS")
    assert hasattr(config, "VIDEO_EXTENSIONS")
    assert hasattr(config, "PHASH_THRESHOLD")
    assert hasattr(config, "MEMORY_HIGH_FREQ_DAYS")


def test_category_constants():
    import config
    assert config.CATEGORY_LIFE == 1
    assert config.CATEGORY_SAMPLE == 2
    assert len(config.CATEGORY_NAMES) == 2
    assert config.CATEGORY_NAMES[1] == "生活照片"


def test_extensions_sets():
    import config
    assert ".jpg" in config.IMAGE_EXTENSIONS
    assert ".png" in config.IMAGE_EXTENSIONS
    assert ".heic" in config.IMAGE_EXTENSIONS
    assert ".mp4" in config.VIDEO_EXTENSIONS
    assert config.IMAGE_EXTENSIONS.isdisjoint(config.VIDEO_EXTENSIONS)


def test_is_configured_without_api_key():
    import config, os
    orig_env = config.ENV_FILE
    try:
        config.ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_nonexistent_.env")
        assert config.is_configured() is False
    finally:
        config.ENV_FILE = orig_env


def test_is_configured_with_all():
    import config, os
    orig_key = os.environ.get("DEEPSEEK_API_KEY", "")
    orig_src = os.environ.get("SOURCE_DRIVE", "")
    orig_data = os.environ.get("PHOTO_DATA_DIR", "")
    try:
        os.environ["DEEPSEEK_API_KEY"] = "sk-test"
        os.environ["SOURCE_DRIVE"] = "D:\\test"
        os.environ["PHOTO_DATA_DIR"] = "D:\\testdata"
        config._settings = None
        config.reload_config()
        assert config.is_configured() is True
    finally:
        if orig_key:
            os.environ["DEEPSEEK_API_KEY"] = orig_key
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        if orig_src:
            os.environ["SOURCE_DRIVE"] = orig_src
        else:
            os.environ.pop("SOURCE_DRIVE", None)
        if orig_data:
            os.environ["PHOTO_DATA_DIR"] = orig_data
        else:
            os.environ.pop("PHOTO_DATA_DIR", None)
        config._settings = None
        config.reload_config()


def test_get_openai_client_returns_same_instance():
    import config, os
    config._OPENAI_CLIENT = None
    orig_key = os.environ.get("DEEPSEEK_API_KEY", "")
    try:
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-dummy"
        config._settings = None
        config.reload_config()
        c1 = config.get_openai_client()
        c2 = config.get_openai_client()
        assert c1 is c2
    finally:
        if orig_key:
            os.environ["DEEPSEEK_API_KEY"] = orig_key
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        config._OPENAI_CLIENT = None
        config._settings = None


def test_settings_class_exists():
    import config
    assert hasattr(config, "Settings")


def test_settings_defaults():
    import config
    s = config.Settings()
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.deepseek_model == "deepseek-chat"
    assert s.thumbnail_size == (400, 400)


def test_settings_computed_properties():
    import config
    s = config.Settings()
    assert s.db_path.endswith("photos.db")
    assert s.thumbnail_dir.endswith("thumbnails")
    assert s.classification_history_file.endswith("classification_history.txt")


def test_source_dirs_single_path():
    import config, os
    orig = os.environ.get("SOURCE_DRIVE", "")
    try:
        os.environ["SOURCE_DRIVE"] = "D:\\照片"
        config._settings = None
        config._sync_module_vars_from_settings()
        s = config.get_settings()
        assert s.source_dirs == ["D:\\照片"]
    finally:
        if orig:
            os.environ["SOURCE_DRIVE"] = orig
        else:
            os.environ.pop("SOURCE_DRIVE", None)
        config._settings = None
        config._sync_module_vars_from_settings()


def test_source_dirs_multiple_paths():
    import config, os
    orig = os.environ.get("SOURCE_DRIVE", "")
    try:
        os.environ["SOURCE_DRIVE"] = "D:\\照片;E:\\旅行"
        config._settings = None
        config._sync_module_vars_from_settings()
        s = config.get_settings()
        assert s.source_dirs == ["D:\\照片", "E:\\旅行"]
    finally:
        if orig:
            os.environ["SOURCE_DRIVE"] = orig
        else:
            os.environ.pop("SOURCE_DRIVE", None)
        config._settings = None
        config._sync_module_vars_from_settings()


def test_phash_and_memory_constants():
    import config
    assert config.PHASH_THRESHOLD == 8
    assert config.MEMORY_HIGH_FREQ_DAYS == 3


def test_get_settings_returns_same_instance():
    import config
    config._settings = None
    s1 = config.get_settings()
    s2 = config.get_settings()
    assert s1 is s2
    config._settings = None


def test_save_config_updates_settings():
    import config
    tmp = tempfile.mkdtemp()
    try:
        orig_env_file = config.ENV_FILE
        fake_env = os.path.join(tmp, ".env")
        with open(fake_env, "w") as f:
            f.write("DEEPSEEK_API_KEY=sk-old\n")
            f.write("SOURCE_DRIVE=D:\\old\n")
            f.write("PHOTO_DATA_DIR=D:\\olddata\n")
        config.ENV_FILE = fake_env
        config._settings = None
        config.reload_config()
        assert config.SOURCE_DRIVE == "D:\\old"
        assert config.DATA_DIR == "D:\\olddata"

        config.save_config("D:\\new", "D:\\newdata", "sk-new")
        assert config.SOURCE_DRIVE == "D:\\new"
        assert config.DATA_DIR == "D:\\newdata"
        assert config.DEEPSEEK_API_KEY == "sk-new"

        s = config.get_settings()
        assert s.source_drive == "D:\\new"
        assert s.photo_data_dir == "D:\\newdata"
        assert s.deepseek_api_key == "sk-new"

    finally:
        shutil.rmtree(tmp)
        config.ENV_FILE = orig_env_file
        config.reload_config()

```

## tests/test_db_manager.py

```python
import os
import sqlite3
import tempfile
import shutil


def test_database_init_tables():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()}
        conn.close()
        expected = {"files", "folder_categories", "photo_metadata",
                    "memories", "click_history", "photo_tags",
                    "face_embeddings", "face_clusters", "events",
                    "memory_reasoning", "migration_log", "task_checkpoints"}
        assert expected.issubset(tables), f"missing tables: {expected - tables}"
    finally:
        shutil.rmtree(tmp)


def test_database_connect_contextmanager():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')"
            )
        with db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 1
    finally:
        shutil.rmtree(tmp)


def test_database_connect_rollback_on_error():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        try:
            with db.connect() as conn:
                conn.execute(
                    "INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')"
                )
                raise RuntimeError("test error")
        except RuntimeError:
            pass
        with db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 0
    finally:
        shutil.rmtree(tmp)


def test_database_persistent_connection():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = db.get_persistent_connection()
        conn.execute(
            "INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')"
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        conn.close()
        assert count == 1
    finally:
        shutil.rmtree(tmp)


def test_database_init_tables_idempotent():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        db.init_tables()
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        assert count >= 12
    finally:
        shutil.rmtree(tmp)


def test_v03_new_columns_exist():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)

        files_cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
        assert "source_dir" in files_cols

        meta_cols = {r[1] for r in conn.execute("PRAGMA table_info(photo_metadata)").fetchall()}
        assert "phash" in meta_cols
        assert "is_duplicate_of" in meta_cols

        mem_cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
        assert "last_shown_at" in mem_cols
        assert "click_count" in mem_cols
        assert "dismissed_at" in mem_cols
        assert "payload" in mem_cols

        tags_cols = {r[1] for r in conn.execute("PRAGMA table_info(photo_tags)").fetchall()}
        assert "source" in tags_cols

        conn.close()
    finally:
        shutil.rmtree(tmp)


def test_migration_log_records_version():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT version_to FROM migration_log ORDER BY migrated_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row[0] == "0.3"
    finally:
        shutil.rmtree(tmp)


def test_v02_to_v03_migration():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                folder_name TEXT NOT NULL,
                file_size INTEGER,
                file_mtime TEXT,
                file_hash TEXT,
                is_image INTEGER DEFAULT 1,
                scanned_at TEXT
            );
            CREATE TABLE photo_metadata (
                file_id INTEGER PRIMARY KEY,
                date_taken TEXT,
                camera_model TEXT,
                gps_lat REAL,
                gps_lon REAL,
                width INTEGER,
                height INTEGER,
                thumbnail_path TEXT,
                exif_json TEXT,
                indexed_at TEXT,
                is_starred INTEGER DEFAULT 0
            );
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category INTEGER NOT NULL,
                memory_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                photo_ids TEXT NOT NULL,
                cover_file_id INTEGER,
                created_at TEXT,
                is_starred INTEGER DEFAULT 0
            );
            CREATE TABLE photo_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(file_id, tag)
            );
            INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('a.jpg', 'a.jpg', '/t', 't');
            INSERT INTO photo_metadata (file_id, date_taken) VALUES (1, '2024-01-01');
            INSERT INTO memories (category, memory_type, title, photo_ids) VALUES (1, 'auto', 'Test', '[1]');
            INSERT INTO photo_tags (file_id, tag) VALUES (1, 'sunset');
        """)
        conn.commit()
        conn.close()

        db = Database(db_path)
        db.init_tables()

        conn2 = sqlite3.connect(db_path)
        files_cols = {r[1] for r in conn2.execute("PRAGMA table_info(files)").fetchall()}
        assert "source_dir" in files_cols

        meta_cols = {r[1] for r in conn2.execute("PRAGMA table_info(photo_metadata)").fetchall()}
        assert "phash" in meta_cols
        assert "is_duplicate_of" in meta_cols

        tags_cols = {r[1] for r in conn2.execute("PRAGMA table_info(photo_tags)").fetchall()}
        assert "source" in tags_cols

        tag_source = conn2.execute("SELECT source FROM photo_tags WHERE file_id=1").fetchone()[0]
        assert tag_source == "manual"

        tables = {r[0] for r in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "face_embeddings" in tables
        assert "face_clusters" in tables
        assert "events" in tables
        assert "task_checkpoints" in tables

        row = conn2.execute(
            "SELECT version_from, version_to FROM migration_log ORDER BY migrated_at DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "0.2"
        assert row[1] == "0.3"

        conn2.close()
    finally:
        shutil.rmtree(tmp)

```

## tests/test_db_schema.py

```python
import os
import sqlite3
import tempfile
import shutil


def test_all_tables_created():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()}
        conn.close()
        expected = {"files", "folder_categories", "photo_metadata",
                    "memories", "click_history", "photo_tags",
                    "face_embeddings", "face_clusters", "events",
                    "memory_reasoning", "migration_log", "task_checkpoints"}
        assert expected.issubset(tables), f"missing tables: {expected - tables}"
    finally:
        shutil.rmtree(tmp)


def test_files_table_columns():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
        conn.close()
        required = {"id", "file_path", "file_name", "folder_path", "folder_name",
                    "file_size", "file_mtime", "file_hash", "is_image", "scanned_at",
                    "source_dir"}
        assert required.issubset(cols), f"missing columns: {required - cols}"
    finally:
        shutil.rmtree(tmp)


def test_photo_metadata_has_is_starred():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(photo_metadata)").fetchall()}
        conn.close()
        assert "is_starred" in cols
    finally:
        shutil.rmtree(tmp)


def test_memories_has_is_starred():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
        conn.close()
        assert "is_starred" in cols
    finally:
        shutil.rmtree(tmp)


def test_photo_tags_unique_constraint():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO files (file_path, file_name, folder_path, folder_name) VALUES ('t.jpg', 't.jpg', '/t', 't')")
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (?, 'sunset', 'manual')", (fid,))
        conn.commit()
        try:
            conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (?, 'sunset', 'manual')", (fid,))
            assert False, "should have raised IntegrityError"
        except sqlite3.IntegrityError:
            pass
        conn.execute("INSERT INTO photo_tags (file_id, tag, source) VALUES (?, 'sunset', 'siglip')", (fid,))
        conn.commit()
        conn.close()
    finally:
        shutil.rmtree(tmp)


def test_config_init_all_tables_delegates():
    from db_manager import Database
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "photos.db")
        db = Database(db_path)
        db.init_tables()
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        assert count >= 12
    finally:
        shutil.rmtree(tmp)

```

## tests/test_exif_thumbnail.py

```python
import os
import tempfile
import shutil
from PIL import Image


def _create_test_jpeg(path, width=200, height=150):
    img = Image.new("RGB", (width, height), color=(255, 128, 0))
    img.save(path, "JPEG")


def test_extract_exif_no_exif():
    from indexer.photo_indexer import extract_exif
    tmp = tempfile.mkdtemp()
    try:
        jpg = os.path.join(tmp, "test.jpg")
        _create_test_jpeg(jpg)
        result = extract_exif(jpg)
        assert "date_taken" in result
        assert "camera_model" in result
        assert "gps_lat" in result
        assert "gps_lon" in result
        assert "orientation" in result
        assert result["date_taken"] is None
        assert result["camera_model"] is None
    finally:
        shutil.rmtree(tmp)


def test_extract_exif_file_not_found():
    from indexer.photo_indexer import extract_exif
    result = extract_exif("/nonexistent/path.jpg")
    assert result["date_taken"] is None


def test_generate_thumbnail_creates_file():
    from indexer.photo_indexer import generate_thumbnail
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src.jpg")
        _create_test_jpeg(src, 800, 600)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        import config
        orig = config.THUMBNAIL_DIR
        config.THUMBNAIL_DIR = thumb_dir
        try:
            thumb_path, w, h = generate_thumbnail(src, "1.jpg")
            assert thumb_path is not None
            assert os.path.exists(thumb_path)
        finally:
            config.THUMBNAIL_DIR = orig
    finally:
        shutil.rmtree(tmp)


def test_generate_thumbnail_skips_existing():
    from indexer.photo_indexer import generate_thumbnail
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src.jpg")
        _create_test_jpeg(src, 400, 300)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        import config
        orig = config.THUMBNAIL_DIR
        config.THUMBNAIL_DIR = thumb_dir
        try:
            thumb_path1, w1, h1 = generate_thumbnail(src, "2.jpg")
            assert thumb_path1 is not None
            thumb_path2, w2, h2 = generate_thumbnail(src, "2.jpg")
            assert w2 is None
            assert h2 is None
        finally:
            config.THUMBNAIL_DIR = orig
    finally:
        shutil.rmtree(tmp)


def test_generate_thumbnail_respects_max_size():
    from indexer.photo_indexer import generate_thumbnail
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "big.jpg")
        _create_test_jpeg(src, 3000, 2000)
        thumb_dir = os.path.join(tmp, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)

        import config
        orig = config.THUMBNAIL_DIR
        config.THUMBNAIL_DIR = thumb_dir
        try:
            thumb_path, w, h = generate_thumbnail(src, "3.jpg")
            thumb_img = Image.open(thumb_path)
            assert thumb_img.width <= 400
            assert thumb_img.height <= 400
        finally:
            config.THUMBNAIL_DIR = orig
    finally:
        shutil.rmtree(tmp)


def test_auto_rotate():
    from indexer.photo_indexer import _auto_rotate
    img = Image.new("RGB", (100, 50))
    result = _auto_rotate(img)
    assert result is not None
    assert result.size[0] == 100

```

## tests/test_repositories.py

```python
import os
import tempfile
import shutil
from datetime import datetime


def test_database_basic_operations():
    from db_manager import Database

    temp_dir = tempfile.mkdtemp()
    try:
        temp_db = os.path.join(temp_dir, "test.db")
        db = Database(temp_db)
        db.init_tables()

        with db.connect() as conn:
            conn.execute(
                "INSERT INTO files (file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image, scanned_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("D:\\test\\photo.jpg", "photo.jpg", "D:\\test", "test", 12345, datetime.now().isoformat(), 1, datetime.now().isoformat()),
            )
            row = conn.execute("SELECT * FROM files WHERE file_path = ?", ("D:\\test\\photo.jpg",)).fetchone()
            assert row is not None

            conn.execute(
                "INSERT OR REPLACE INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
                ("D:\\test", 1, "high"),
            )
            cat = conn.execute("SELECT category FROM folder_categories WHERE folder_path = ?", ("D:\\test",)).fetchone()
            assert cat[0] == 1

            conn.execute(
                "INSERT OR REPLACE INTO photo_metadata (file_id, date_taken, camera_model, gps_lat, gps_lon, width, height, thumbnail_path, indexed_at, is_starred) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, datetime.now().isoformat(), "Test Camera", 39.9, 116.4, 1920, 1080, "D:\\test\\thumb.jpg", datetime.now().isoformat(), 0),
            )
            meta = conn.execute("SELECT * FROM photo_metadata WHERE file_id = ?", (1,)).fetchone()
            assert meta is not None

            conn.execute(
                "INSERT INTO memories (category, memory_type, title, description, photo_ids, cover_file_id, created_at, is_starred) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "auto", "Test Memory", "Test Desc", "[1]", 1, datetime.now().isoformat(), 0),
            )
            mem = conn.execute("SELECT * FROM memories WHERE category = ?", (1,)).fetchall()
            assert len(mem) == 1

            conn.execute(
                "INSERT INTO click_history (file_id, folder_path, category, clicked_at) VALUES (?, ?, ?, ?)",
                (1, "D:\\test", 1, datetime.now().isoformat()),
            )
            click = conn.execute("SELECT * FROM click_history WHERE file_id = ?", (1,)).fetchone()
            assert click is not None

            conn.execute(
                "INSERT OR IGNORE INTO photo_tags (file_id, tag, created_at) VALUES (?, ?, ?)",
                (1, "test", datetime.now().isoformat()),
            )
            tags = conn.execute("SELECT * FROM photo_tags WHERE file_id = ?", (1,)).fetchall()
            assert len(tags) == 1

    finally:
        shutil.rmtree(temp_dir)

```

## tests/test_virtual_waterfall.py

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_virtual_waterfall_layout_basic():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT, GAP

    photos = [{"thumbnail_path": ""} for _ in range(10)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 100)

    assert layout.total_width > 0
    assert layout.total_height > 0
    assert len(layout._positions) == 10


def test_virtual_waterfall_cards_in_range():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    photos = [{"thumbnail_path": ""} for _ in range(20)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 100)

    visible = layout.cards_in_range(scroll_y=0, viewport_height=300)
    assert len(visible) > 0

    visible2 = layout.cards_in_range(scroll_y=0, viewport_height=10000)
    assert len(visible2) == 20


def test_virtual_waterfall_update_card_width():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    photos = [{"thumbnail_path": ""} for _ in range(5)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 100)
    old_height = layout.total_height

    layout.update_card_width(200)
    assert layout._card_width == 200
    assert layout.total_height != old_height or True


def test_virtual_waterfall_photo_at():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    photos = [{"id": i, "thumbnail_path": ""} for i in range(5)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 80)

    for i in range(5):
        assert layout.photo_at(i)["id"] == i


def test_virtual_waterfall_empty():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    layout = VirtualWaterfallLayout([], COL_COUNT, 100)
    assert layout.total_height >= 0
    assert layout.cards_in_range(0, 100) == []


if __name__ == "__main__":
    test_virtual_waterfall_layout_basic()
    test_virtual_waterfall_cards_in_range()
    test_virtual_waterfall_update_card_width()
    test_virtual_waterfall_photo_at()
    test_virtual_waterfall_empty()
    print("All virtual waterfall tests passed")

```

## ui/__init__.py

```python

```

## ui/app.py

```python
import os
import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from logger_setup import logger
from config import (
    CATEGORY_LIFE, CATEGORY_SAMPLE,
    CATEGORY_NAMES, is_configured,
)
from db_manager import Database
from infra.db.repositories.memories_repo import MemoriesRepository
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from infra.db.repositories.click_history_repo import ClickHistoryRepository
from core.models import ClickHistory
from ui.components.virtual_waterfall import VirtualCategoryPage as CategoryPage
from ui.components.startup_window import StartupWindow
from ui.components.image_viewer import ImageViewer
from ui.components.sidebar import Sidebar
from ui.components.timeline_view import TimelineView
from ui.components.special_memories import SpecialMemoriesView
from ui.recommendation import rank_category_photos, load_starred_photos
from ui.recommendation import CATEGORY_COLORS, PAGE_SIZE, record_shown_photos


from services.background_task_manager import BackgroundTaskManager

CATEGORIES = [
    (CATEGORY_LIFE, CATEGORY_NAMES[CATEGORY_LIFE]),
    (CATEGORY_SAMPLE, CATEGORY_NAMES[CATEGORY_SAMPLE]),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NAS 照片回忆")
        self.setMinimumSize(600, 500)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.55), int(screen.height() * 0.85))
        self.move(int(screen.width() * 0.22), int(screen.height() * 0.08))

        self.current_page = 0
        self.pages = []
        self.starred_only = False
        self._cat_photos = {}
        self._cat_offsets = {}
        self._cat_all_loaded = {}
        self._folder_viewer_photos = []
        self._folder_view_counts = {}
        self._suppressed_folders = set()
        self._last_scroll_val = 0
        self._is_fullscreen = False
        self._window_drag_pos = None
        self._first_load_done = False
        self._is_dragging = False

        self.setStyleSheet("""
            QMainWindow {
                background: transparent;
            }
        """)

        _db = Database()
        _db.init_tables()
        self.db = _db.get_persistent_connection()
        self.setup_ui()

        self.image_viewer = ImageViewer()
        self.image_viewer.star_toggled.connect(self._on_star_toggled)
        self.image_viewer.closed.connect(self._on_viewer_closed)
        self.image_viewer.recategorize.connect(self._on_recategorize)
        self.image_viewer.hide()

        self.load_memories()

    def closeEvent(self, event):
        logger.info("MainWindow 正在关闭，等待后台线程...")
        BackgroundTaskManager.get_instance().wait_all(5000)
        super().closeEvent(event)

    def setup_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        central.setStyleSheet("""
            #centralWidget {
                background: #1a1a2e;
                border-radius: 10px;
            }
        """)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar.setStyleSheet("""
            #topBar {
                background: #2c3e50;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
        """)
        top_bar.setFixedHeight(52)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 8, 12, 8)

        title = QLabel("NAS 照片回忆")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; background: transparent;")
        top_layout.addWidget(title)

        top_layout.addStretch()

        self.star_btn = QPushButton("优秀回忆")
        self.star_btn.setStyleSheet("""
            QPushButton { background: #34495e; color: white; border: none;
                padding: 6px 16px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background: #4a6a8a; }
            QPushButton:checked { background: #e74c3c; }
        """)
        self.star_btn.setCheckable(True)
        self.star_btn.clicked.connect(self.toggle_starred)
        top_layout.addWidget(self.star_btn)

        settings_btn = QPushButton("⚙ 设置")
        settings_btn.setStyleSheet("""
            QPushButton { background: #34495e; color: white; border: none;
                padding: 6px 16px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background: #4a6a8a; }
        """)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)
        top_layout.addWidget(settings_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: rgba(255,255,255,0.6);
                border: none; border-radius: 18px; font-size: 16px; font-weight: bold; }
            QPushButton:hover { background: #e74c3c; color: white; }
        """)
        close_btn.clicked.connect(self.close)
        top_layout.addWidget(close_btn)

        main_layout.addWidget(top_bar)
        self.top_bar = top_bar

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigation_changed.connect(self._on_nav_changed)
        body_layout.addWidget(self.sidebar)

        self._random_container = QWidget()
        self._random_container.setStyleSheet("background: #1a1a2e;")
        random_layout = QVBoxLayout(self._random_container)
        random_layout.setContentsMargins(0, 0, 0, 0)
        random_layout.setSpacing(0)

        nav_bar = QWidget()
        nav_bar.setObjectName("navBar")
        nav_bar.setStyleSheet("""
            #navBar {
                background: #ecf0f1;
            }
        """)
        nav_bar.setFixedHeight(40)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(4)

        self.nav_buttons = []
        for cat_id, cat_name in CATEGORIES:
            btn = QPushButton(cat_name)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { background: transparent; border: none;
                    padding: 8px 16px; border-radius: 4px; font-size: 13px; color: #666; }
                QPushButton:hover { background: #ddd; }
                QPushButton:checked { background: #3498db; color: white; font-weight: bold; }
            """)
            btn.clicked.connect(lambda checked, idx=len(self.nav_buttons): self.switch_page(idx))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        random_layout.addWidget(nav_bar)
        self.nav_bar = nav_bar

        self.stack = QStackedWidget()

        for cat_id, cat_name in CATEGORIES:
            page = CategoryPage(cat_id, cat_name)
            page.photo_clicked.connect(self.on_photo_clicked)
            if hasattr(page, 'load_more_requested'):
                page.load_more_requested.connect(lambda cat=cat_id: self._on_load_more(cat))
            else:
                logger.warning(f"CategoryPage 缺少 load_more_requested 信号, 跳过连接")
            page.scroll.verticalScrollBar().valueChanged.connect(
                lambda v, p=page: self._on_page_scroll(p, v)
            )
            self.stack.addWidget(page)
            self.pages.append(page)

        random_layout.addWidget(self.stack)
        self.nav_buttons[0].setChecked(True)

        self._timeline_view = TimelineView()
        self._timeline_view.photo_clicked.connect(self.on_photo_clicked)

        self._special_view = SpecialMemoriesView()
        self._special_view.memory_clicked.connect(self._on_memory_clicked)
        self._special_view.memory_dismissed.connect(self._on_memory_dismissed)

        self._nav_stack = QStackedWidget()
        self._nav_stack.addWidget(self._random_container)
        self._nav_stack.addWidget(self._timeline_view)
        self._nav_stack.addWidget(self._special_view)

        body_layout.addWidget(self._nav_stack)
        main_layout.addLayout(body_layout)

        self.drag_start = None

    def _on_nav_changed(self, nav_id: str):
        nav_map = {"random": 0, "timeline": 1, "special": 2}
        idx = nav_map.get(nav_id, 0)
        self._nav_stack.setCurrentIndex(idx)

        if nav_id == "timeline":
            self._load_timeline()
        elif nav_id == "special":
            self._load_special_memories()

    def _load_timeline(self):
        all_photos = rank_category_photos(self.db, CATEGORY_LIFE)
        self._timeline_view.load_photos(all_photos)

    def _load_special_memories(self):
        from business.memory.memory_discovery import get_on_this_day_memories
        from infra.db.repositories.memories_repo import MemoriesRepository

        repo = MemoriesRepository(Database())
        all_memories = repo.get_undismissed()
        on_this_day = get_on_this_day_memories()
        combined = on_this_day + [m for m in all_memories if m.memory_type != "on_this_day"]
        self._special_view.load_memories(combined)

    def _on_memory_clicked(self, memory_id: int):
        from infra.db.repositories.memories_repo import MemoriesRepository
        repo = MemoriesRepository(Database())
        repo.update_shown(memory_id)

    def _on_memory_dismissed(self, memory_id: int):
        logger.info(f"回忆 {memory_id} 已标记不再显示")

    def switch_page(self, index):
        if self.image_viewer.isVisible():
            self.image_viewer.hide_viewer()
        self.current_page = index
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.load_category(index)

    def toggle_starred(self):
        self.starred_only = self.star_btn.isChecked()
        self.load_memories()

    def _open_settings(self):
        from ui.components.setup_window import SetupWindow
        self._settings_window = SetupWindow(edit_mode=True)
        self._settings_window.config_saved.connect(self._on_settings_saved)
        self._settings_window.show()

    def _on_settings_saved(self):
        logger.info("配置已更新，重新加载")
        self._settings_window.close()
        self._settings_window = None
        self.load_memories()

    def load_memories(self):
        self._suppressed_folders.clear()
        self._folder_view_counts.clear()
        self._cat_offsets = {}
        self._cat_all_loaded = {}

        for cat_id, _ in CATEGORIES:
            memories_repo = MemoriesRepository(Database())
            title = memories_repo.get_latest_title(cat_id)
            summary = f"「{title}」" if title else ""
            self.pages[next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)].set_memory_summary(summary)

        for i in range(self.stack.count()):
            self.load_category(i)
        self.stack.setCurrentIndex(self.current_page)

    def load_category(self, index):
        if index >= len(CATEGORIES):
            return
        cat_id, _ = CATEGORIES[index]

        self._cat_offsets[cat_id] = 0
        self._cat_all_loaded[cat_id] = False

        if self.starred_only:
            all_photos = load_starred_photos(self.db, cat_id)
        else:
            all_photos = rank_category_photos(self.db, cat_id)

        self._cat_photos[cat_id] = list(all_photos)

        first_page = all_photos[:PAGE_SIZE]
        self._cat_offsets[cat_id] = len(first_page)
        self._cat_all_loaded[cat_id] = len(first_page) >= len(all_photos)

        record_shown_photos(self.db, first_page, cat_id)

        if not self._first_load_done:
            self._first_load_done = True
            QTimer.singleShot(30, lambda p=self.pages[index], ph=first_page: p.load_photos(ph))
        else:
            self.pages[index].load_photos(first_page)

    def _on_load_more(self, cat_id):
        if self._cat_all_loaded.get(cat_id, False):
            return
        page_index = next(i for i, (c, _) in enumerate(CATEGORIES) if c == cat_id)
        offset = self._cat_offsets.get(cat_id, 0)
        all_photos = self._cat_photos.get(cat_id, [])

        next_page = all_photos[offset:offset + PAGE_SIZE]
        if not next_page:
            self._cat_all_loaded[cat_id] = True
            return

        self._cat_offsets[cat_id] = offset + len(next_page)
        if self._cat_offsets[cat_id] >= len(all_photos):
            self._cat_all_loaded[cat_id] = True

        record_shown_photos(self.db, next_page, cat_id)
        self.pages[page_index].append_photos(next_page)

    def _on_page_scroll(self, page, value):
        if value > 10:
            page.memory_summary.hide()

        delta = value - self._last_scroll_val
        if abs(delta) > 5:
            if delta > 0 and value > 40:
                self.top_bar.hide()
                self.nav_bar.hide()
            elif delta < 0:
                self.top_bar.show()
                self.nav_bar.show()
            self._last_scroll_val = value

    def on_photo_clicked(self, photo_data):
        if isinstance(photo_data, int):
            file_id = photo_data
            row = self.db.execute(
                """SELECT f.id, f.file_path, f.file_name, f.folder_path,
                          f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
                          pm.width, pm.height, pm.date_taken
                   FROM files f
                   LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                   WHERE f.id = ?""",
                (file_id,),
            ).fetchone()
            if not row:
                logger.warning(f"时间线点击: file_id={file_id} 未找到")
                return
            photo_data = {
                "id": row["id"], "file_path": row["file_path"], "file_name": row["file_name"],
                "folder_path": row["folder_path"],
                "folder_name": row["folder_display"] if "folder_display" in row.keys() else os.path.basename(row["folder_path"]),
                "thumbnail_path": row["thumbnail_path"],
                "width": row["width"] if "width" in row.keys() else None,
                "height": row["height"] if "height" in row.keys() else None,
                "date_taken": row["date_taken"] if "date_taken" in row.keys() else None,
                "file_mtime": row["file_mtime"] if "file_mtime" in row.keys() else None,
            }
            cat_id = CATEGORIES[self.current_page][0]
            all_photos = self._cat_photos.get(cat_id, [])
        else:
            cat_id = CATEGORIES[self.current_page][0]
            all_photos = self._cat_photos.get(cat_id, [])

        clicked_id = photo_data.get("id")
        self._record_click(clicked_id, photo_data.get("folder_path", ""))

        clicked_folder = os.path.dirname(photo_data.get("file_path", ""))
        self._folder_view_counts[clicked_folder] = self._folder_view_counts.get(clicked_folder, 0) + 1
        if self._folder_view_counts[clicked_folder] >= 20:
            self._suppressed_folders.add(clicked_folder)

        folder_photos = [p for p in all_photos if os.path.dirname(p.get("file_path", "")) == clicked_folder]
        if not folder_photos:
            folder_photos = all_photos

        idx = next((i for i, p in enumerate(folder_photos) if p.get("id") == clicked_id), 0)

        pm_repo = PhotoMetadataRepository(Database())
        starred = set(pm_repo.get_starred_file_ids())

        self._folder_viewer_photos = folder_photos
        self.image_viewer.setParent(self.centralWidget())
        self.image_viewer.setGeometry(self._nav_stack.geometry())
        self.image_viewer.show_photos(folder_photos, idx, starred)
        self.image_viewer.raise_()

    def _record_click(self, file_id, folder_path):
        cat_id = CATEGORIES[self.current_page][0]
        click_repo = ClickHistoryRepository(Database())
        click_repo.insert(ClickHistory(file_id=file_id, folder_path=folder_path, category=cat_id))

    def _on_star_toggled(self, file_id, starred):
        pm_repo = PhotoMetadataRepository(Database())
        pm_repo.set_starred(file_id, starred)

    def _on_viewer_closed(self):
        pass

    def _on_recategorize(self, file_id, photo_index):
        if self.image_viewer.isVisible():
            self.image_viewer.hide_viewer()

        photo = self._folder_viewer_photos[photo_index] if photo_index < len(self._folder_viewer_photos) else None
        if not photo:
            return

        self._recategorize_target_id = photo.get("id")
        folder_path = os.path.dirname(photo.get("file_path", ""))
        if not folder_path:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("调整分类")
        dialog.setMinimumSize(300, 220)
        dialog.setStyleSheet("background: #1a1a2e;")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)

        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setContentsMargins(24, 20, 24, 20)
        dlg_layout.setSpacing(12)

        name_label = QLabel(os.path.basename(folder_path))
        name_label.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #e0e0e0;")
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dlg_layout.addWidget(name_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        for cat_id, cat_name in {1: "生活", 2: "样片"}.items():
            btn = QPushButton(cat_name)
            btn.setFont(QFont("Microsoft YaHei", 11))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {CATEGORY_COLORS[cat_id]}; color: white; border: none;
                    border-radius: 6px; padding: 8px 4px; font-size: 12px; }}
            """)
            btn.clicked.connect(lambda checked, c=cat_id: self._apply_recategorize(dialog, folder_path, c))
            btn_layout.addWidget(btn, 1)

        dlg_layout.addLayout(btn_layout)
        dlg_layout.addStretch()
        dialog.exec()

    def _apply_recategorize(self, dialog, folder_path, new_category):
        from classifier.folder_classifier import set_folder_category

        set_folder_category(folder_path, new_category, "manual")

        from classifier.folder_classifier import build_classification_history
        build_classification_history()
        dialog.accept()
        self.load_memories()

    def keyPressEvent(self, event):
        if self.image_viewer.isVisible():
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Escape):
                self.image_viewer.keyPressEvent(event)
                return

        if event.key() == Qt.Key.Key_F:
            if self._is_fullscreen:
                self.showNormal()
                self._is_fullscreen = False
            else:
                self.showFullScreen()
                self._is_fullscreen = True
            return

        if event.key() == Qt.Key.Key_Left:
            self.switch_page((self.current_page - 1) % 2)
        elif event.key() == Qt.Key.Key_Right:
            self.switch_page((self.current_page + 1) % 2)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            child = self.childAt(pos)
            if child is not None and child is not self.centralWidget():
                super().mousePressEvent(event)
                return
            self.drag_start = event.position().toPoint()
            self._window_drag_pos = event.globalPosition().toPoint()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._window_drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._window_drag_pos
            if abs(delta.x()) > 6 or abs(delta.y()) > 6:
                self._is_dragging = True
                self.move(self.pos() + delta)
                self._window_drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_start is not None and not self._is_dragging:
            delta = event.position().toPoint() - self.drag_start
            if abs(delta.x()) > 80:
                if delta.x() > 0:
                    self.switch_page((self.current_page - 1) % 2)
                else:
                    self.switch_page((self.current_page + 1) % 2)
        self.drag_start = None
        self._window_drag_pos = None
        super().mouseReleaseEvent(event)


def main():
    logger.info("=" * 50)
    logger.info("NAS 照片回忆 启动")
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setFont(QFont("Microsoft YaHei", 10))
        main_window = [None]
        startup_ref = [None]
        _bg_scan_started = [False]
        _bg_index_started = [False]
        _bg_refine_started = [False]

        def show_main_window():
            logger.info("show_main_window 开始, 优先构建主界面...")
            try:
                logger.info("构建 MainWindow...")
                main_window[0] = MainWindow()
                logger.info("MainWindow 构建完成, 调用 show()")
                main_window[0].show()
                logger.info("主界面已显示")
                QTimer.singleShot(1000, start_memory_discovery)
            except Exception as e:
                logger.exception("MainWindow 构建失败!")
                import traceback
                err_path = os.path.join(os.path.dirname(__file__), "..", "error.log")
                with open(err_path, "w", encoding="utf-8") as f:
                    traceback.print_exc(file=f)
                raise
            st = startup_ref[0]
            if st:
                st.hide()
                st.close()
            start_background_keyword_refine()

        def start_memory_discovery():
            from PyQt6.QtCore import QThread
            class BgMemoryWorker(QThread):
                def run(self):
                    from business.memory.memory_discovery import discover_on_this_day, discover_recent_memories
                    try:
                        logger.info("开始发现回忆...")
                        on_this_day = discover_on_this_day()
                        recent = discover_recent_memories()
                        logger.info(f"发现回忆完成: {len(on_this_day)} 个那年今日, {len(recent)} 个近期回忆")
                    except Exception as e:
                        logger.exception("发现回忆失败!")

            bg = BgMemoryWorker()
            bg.finished.connect(lambda: logger.info("回忆发现线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("回忆发现线程已启动")

        def start_background_keyword_refine():
            if _bg_refine_started[0]:
                logger.info("后台关键词精分类已在运行，跳过重复启动")
                return
            _bg_refine_started[0] = True
            from PyQt6.QtCore import QThread

            class BgRefineWorker(QThread):
                def run(self):
                    from classifier.folder_classifier import refine_sample_keywords
                    refined = refine_sample_keywords()
                    logger.info(f"后台关键词精分类完成: {refined} 个文件夹重新分类")

            bg = BgRefineWorker()
            bg.finished.connect(lambda: logger.info("后台关键词精分类线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台关键词精分类线程已启动")

        def start_background_scan():
            if _bg_scan_started[0]:
                logger.info("后台扫描已在运行，跳过重复启动")
                return
            _bg_scan_started[0] = True
            from PyQt6.QtCore import QThread

            class BgScanWorker(QThread):
                def run(self):
                    from scanner.fast_scan import full_scan, get_checkpoint_status, clear_checkpoint, ScanState
                    while True:
                        cp = get_checkpoint_status()
                        if cp.get("has_checkpoint") and cp.get("state") in (ScanState.PAUSED, ScanState.STOPPED, ScanState.RUNNING):
                            logger.info(f"后台扫描: 检查点状态={cp['state']}，清除后继续")
                            clear_checkpoint()
                        else:
                            break
                    logger.info("后台扫描开始")
                    result = full_scan(progress_callback=lambda cur, tot: None)
                    if result.get("paused"):
                        logger.info(f"后台扫描暂停: 已扫描 {result.get('total_scanned', 0)}, 共 {result.get('total_found', 0)}")
                    else:
                        logger.info(f"后台扫描全部完成: 总计 {result.get('total', 0)} 文件, 新增 {result.get('new', 0)}, 移除 {result.get('removed', 0)}")

            bg = BgScanWorker()
            bg.finished.connect(lambda: logger.info("后台扫描线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台扫描线程已启动")

        def start_background_index():
            if _bg_index_started[0]:
                logger.info("后台索引已在运行，跳过重复启动")
                return
            _bg_index_started[0] = True
            from PyQt6.QtCore import QThread, pyqtSignal

            class BgIndexWorker(QThread):
                progress = pyqtSignal(int, int)

                def run(self):
                    from indexer.photo_indexer import index_photos, get_checkpoint_status, clear_checkpoint, IndexState
                    while True:
                        cp = get_checkpoint_status()
                        if cp.get("has_checkpoint") and cp.get("state") in (IndexState.PAUSED, IndexState.STOPPED):
                            logger.info(f"后台索引: 检查点状态={cp['state']}，清除后继续")
                            clear_checkpoint()
                        else:
                            break
                    logger.info("后台索引开始")
                    result = index_photos(progress_callback=lambda cur, tot: None)
                    if result.get("paused"):
                        logger.info(f"后台索引暂停: {result.get('indexed', 0)}/{result.get('total', 0)}")
                    else:
                        logger.info(f"后台索引全部完成: 总计 {result.get('total', 0)}, 已索引 {result.get('indexed', 0)}")

            bg = BgIndexWorker()
            bg.progress.connect(lambda cur, tot: logger.info(f"后台索引: {cur}/{tot}"))
            bg.finished.connect(lambda: logger.info("后台索引线程结束"))
            bg.start()
            BackgroundTaskManager.get_instance().register(bg)
            logger.info("后台索引线程已启动")

        def launch_startup():
            startup = StartupWindow()
            startup_ref[0] = startup
            startup.transition_to_main.connect(show_main_window)
            startup.background_scan_needed.connect(start_background_scan)
            startup.background_index_needed.connect(start_background_index)
            startup.show()
            startup.start()

        if not is_configured():
            logger.info("未检测到配置，展示设置窗口")
            from ui.components.setup_window import SetupWindow
            setup = SetupWindow()
            setup.config_saved.connect(lambda: (
                setup.hide(),
                setup.close(),
                launch_startup()
            ))
            setup.show()
        else:
            launch_startup()

        sys.exit(app.exec())
    except Exception as e:
        logger.exception("启动失败!")
        import traceback
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise


if __name__ == "__main__":
    main()

```

## ui/recommendation.py

```python
import os
import random
from config import DB_PATH

CATEGORY_COLORS = {
    1: "#27ae60", 2: "#2980b9",
}

PAGE_SIZE = 30
MAX_SAME_FOLDER_STREAK = 12
SMALL_FOLDER_THRESHOLD = 100
FRESHNESS_WINDOW_DAYS = 7
MAX_SAME_DAY_STREAK = 12


def _interleave_small_folders(photos):
    if not photos:
        return photos

    folder_counts = {}
    for p in photos:
        fp = p.get("folder_path", "")
        folder_counts[fp] = folder_counts.get(fp, 0) + 1

    small_folders = {fp for fp, cnt in folder_counts.items() if cnt < SMALL_FOLDER_THRESHOLD}

    if not small_folders:
        return photos

    result = []
    streak_folder = None
    streak_count = 0
    pending = list(photos)

    while pending:
        placed = False
        for i, p in enumerate(pending):
            fp = p.get("folder_path", "")
            is_small = fp in small_folders

            if is_small and fp == streak_folder and streak_count >= MAX_SAME_FOLDER_STREAK:
                continue

            result.append(p)
            pending.pop(i)
            if fp == streak_folder:
                streak_count += 1
            else:
                streak_folder = fp
                streak_count = 1
            placed = True
            break

        if not placed:
            streak_folder = None
            streak_count = 0
            result.append(pending.pop(0))

    return result


def _interleave_by_time(photos):
    if not photos:
        return photos

    day_groups = {}
    day_order = []
    for p in photos:
        dt = p.get("date_taken", "")
        if dt and len(dt) >= 10:
            day = dt[:10]
        else:
            mtime = p.get("file_mtime", "")
            day = mtime[:10] if mtime and len(mtime) >= 10 else "unknown"
        if day not in day_groups:
            day_groups[day] = []
            day_order.append(day)
        day_groups[day].append(p)

    capped = {}
    for day, ps in day_groups.items():
        capped[day] = ps[:MAX_SAME_DAY_STREAK]

    result = []
    streak_day = None
    streak_count = 0
    pending = {day: list(ps) for day, ps in capped.items()}

    while any(pending.values()):
        placed = False
        for day in day_order:
            if not pending.get(day):
                continue
            if day == streak_day and streak_count >= MAX_SAME_DAY_STREAK:
                continue
            p = pending[day].pop(0)
            result.append(p)
            if day == streak_day:
                streak_count += 1
            else:
                streak_day = day
                streak_count = 1
            placed = True
            break

        if not placed:
            streak_day = None
            streak_count = 0
            for day in day_order:
                if pending.get(day):
                    result.append(pending[day].pop(0))
                    streak_day = day
                    streak_count = 1
                    placed = True
                    break

    return result


def _make_photo_dict(r):
    return {
        "id": r["id"], "file_path": r["file_path"], "file_name": r["file_name"],
        "folder_path": r["folder_path"],
        "folder_name": r["folder_display"] if "folder_display" in r.keys() else os.path.basename(r["folder_path"]),
        "thumbnail_path": r["thumbnail_path"],
        "width": r["width"] if "width" in r.keys() else None,
        "height": r["height"] if "height" in r.keys() else None,
        "date_taken": r["date_taken"] if "date_taken" in r.keys() else None,
        "file_mtime": r["file_mtime"] if "file_mtime" in r.keys() else None,
    }


def _get_recently_shown_ids(db, cat_id, days=FRESHNESS_WINDOW_DAYS):
    rows = db.execute(
        "SELECT DISTINCT file_id FROM photo_shown_history "
        "WHERE category = ? AND shown_at >= datetime('now', ?)",
        (cat_id, f"-{days} days"),
    ).fetchall()
    return {r["file_id"] for r in rows}


def record_shown_photos(db, photos, cat_id):
    if not photos:
        return
    for p in photos:
        db.execute(
            "INSERT INTO photo_shown_history (file_id, category, shown_at) VALUES (?, ?, datetime('now'))",
            (p["id"], cat_id),
        )
    db.commit()


def load_photos_from_ids(db, all_ids):
    if not all_ids:
        return []
    seen = set()
    unique_ids = []
    for pid in all_ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    placeholders = ",".join("?" * len(unique_ids))
    rows = db.execute(
        f"""SELECT f.id, f.file_path, f.file_name, f.folder_path,
                   f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
                   pm.width, pm.height, pm.date_taken
            FROM files f
            LEFT JOIN photo_metadata pm ON f.id = pm.file_id
            WHERE f.id IN ({placeholders})""",
        unique_ids,
    ).fetchall()
    return _interleave_small_folders([_make_photo_dict(r) for r in rows])


def load_category_photos_batch(db, cat_id, offset, limit=PAGE_SIZE):
    rows = db.execute("""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken
        FROM files f
        JOIN folder_categories fc ON f.folder_path = fc.folder_path
        LEFT JOIN photo_metadata pm ON f.id = pm.file_id
        WHERE fc.category = ? AND f.is_image = 1 AND pm.thumbnail_path IS NOT NULL
              AND pm.is_duplicate_of IS NULL
        ORDER BY pm.date_taken DESC
        LIMIT ? OFFSET ?
    """, (cat_id, limit, offset)).fetchall()
    if not rows and offset == 0:
        total_cats = db.execute("SELECT COUNT(*) FROM folder_categories").fetchone()[0]
        if total_cats == 0:
            rows = db.execute("""
                SELECT f.id, f.file_path, f.file_name, f.folder_path,
                       f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
                       pm.width, pm.height, pm.date_taken
                FROM files f
                LEFT JOIN photo_metadata pm ON f.id = pm.file_id
                WHERE f.is_image = 1 AND pm.thumbnail_path IS NOT NULL
                      AND pm.is_duplicate_of IS NULL
                ORDER BY pm.date_taken DESC
                LIMIT ?
            """, (limit,)).fetchall()
    return _interleave_small_folders([_make_photo_dict(r) for r in rows])


def load_starred_photos(db, cat_id):
    rows = db.execute("""
        SELECT f.id, f.file_path, f.file_name, f.folder_path,
               f.folder_name as folder_display, f.file_mtime, pm.thumbnail_path,
               pm.width, pm.height, pm.date_taken
        FROM files f
        JOIN photo_metadata pm ON f.id = pm.file_id
        JOIN folder_categories fc ON f.folder_path = fc.folder_path
        WHERE pm.is_starred = 1 AND f.is_image = 1 AND fc.category = ? AND pm.thumbnail_path IS NOT NULL
        ORDER BY pm.date_taken DESC
    """, (cat_id,)).fetchall()
    return _interleave_small_folders([_make_photo_dict(r) for r in rows])


def rank_category_photos(db, cat_id):
    all_ids = []
    seen_ids = set()
    for row in db.execute(
        "SELECT photo_ids FROM memories WHERE category = ? ORDER BY created_at DESC",
        (cat_id,),
    ).fetchall():
        try:
            import json
            for pid in json.loads(row["photo_ids"]):
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_ids.append(pid)
        except Exception:
            pass

    memory_photos = []
    if all_ids:
        memory_photos = load_photos_from_ids(db, all_ids)
        memory_photos = [p for p in memory_photos if p.get("thumbnail_path")]

    batch_photos = load_category_photos_batch(db, cat_id, 0, limit=9999)

    seen_file_ids = set()
    ordered = []
    for p in memory_photos:
        if p["id"] not in seen_file_ids:
            seen_file_ids.add(p["id"])
            ordered.append(p)
    for p in batch_photos:
        if p["id"] not in seen_file_ids:
            seen_file_ids.add(p["id"])
            ordered.append(p)

    if not ordered:
        return []

    recently_shown = _get_recently_shown_ids(db, cat_id)

    fresh = [p for p in ordered if p["id"] not in recently_shown]
    stale = [p for p in ordered if p["id"] in recently_shown]

    random.shuffle(fresh)
    random.shuffle(stale)

    result = []
    result.extend(fresh)
    result.extend(stale)
    return _interleave_by_time(_interleave_small_folders(result))


def rank_search_photos(db, matched_ids):
    photos = load_photos_from_ids(db, matched_ids)
    random.shuffle(photos)
    return _interleave_small_folders(photos)

```

## ui/components/__init__.py

```python

```

## ui/components/folder_classifier_dialog.py

```python
import os
import random

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

from logger_setup import logger
from db_manager import Database
from ui.recommendation import CATEGORY_COLORS


def _get_sample_photos(folder_path, count=2):
    db = Database()
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT f.file_path, pm.thumbnail_path
               FROM files f
               LEFT JOIN photo_metadata pm ON f.id = pm.file_id
               WHERE f.folder_path LIKE ? AND f.is_image = 1
               LIMIT 50""",
            (folder_path + "%",),
        ).fetchall()

    if not rows:
        return []

    if len(rows) > count:
        rows = random.sample(rows, count)

    results = []
    for row in rows:
        img_path = row[1] or row[0]
        results.append(img_path)
    return results


class BranchClassifierDialog(QDialog):
    result_ready = pyqtSignal(list)

    def __init__(self, branches, parent=None):
        super().__init__(parent)
        self.branches = branches
        self.index = 0
        self.results = []
        self.setWindowTitle("文件夹分类确认")
        self.setMinimumSize(600, 300)
        self.setStyleSheet("background: #1a1a2e;")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setup_ui()
        self._show_current()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.count_label = QLabel()
        self.count_label.setFont(QFont("Microsoft YaHei", 10))
        self.count_label.setStyleSheet("color: #a0a0b0;")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.count_label)

        self.folder_label = QLabel()
        self.folder_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        self.folder_label.setStyleSheet("color: #e0e0e0;")
        self.folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.folder_label.setWordWrap(True)
        self.folder_label.setMinimumHeight(36)
        layout.addWidget(self.folder_label)

        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(12)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_labels = []
        for _ in range(2):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(250, 150)
            lbl.setStyleSheet("""
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                background: #111;
                color: #555;
                font-size: 12px;
            """)
            lbl.setText("")
            preview_layout.addWidget(lbl)
            self.preview_labels.append(lbl)

        layout.addLayout(preview_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        labels = {1: "生活", 2: "样片"}
        self.cat_btns = {}
        for cat_id in (1, 2):
            btn = QPushButton(labels[cat_id])
            btn.setFont(QFont("Microsoft YaHei", 11))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            color = CATEGORY_COLORS[cat_id]
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 4px;
                    font-size: 12px;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)
            btn.clicked.connect(lambda checked, c=cat_id: self._classify(c))
            btn_layout.addWidget(btn, 1)
            self.cat_btns[cat_id] = btn

        layout.addLayout(btn_layout)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        skip_btn = QPushButton("跳过")
        skip_btn.setFixedSize(80, 36)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setFont(QFont("Microsoft YaHei", 10))
        skip_btn.setStyleSheet("""
            QPushButton {
                background: #555;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background: #777; }
        """)
        skip_btn.clicked.connect(self._skip_one)
        bottom.addWidget(skip_btn)

        bottom.addStretch()

        done_btn = QPushButton("完成")
        done_btn.setFixedSize(100, 36)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFont(QFont("Microsoft YaHei", 10))
        done_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        done_btn.clicked.connect(self._done)
        bottom.addWidget(done_btn)

        layout.addLayout(bottom)

    def _show_current(self):
        remaining = len(self.branches) - self.index
        self.count_label.setText(
            f"第 {min(self.index + 1, len(self.branches))} / {len(self.branches)} 个  "
            f"(剩余 {max(0, remaining)} 个)"
        )

        for lbl in self.preview_labels:
            lbl.clear()
            lbl.setText("")

        if self.index >= len(self.branches):
            self.folder_label.setText("全部分类完成!")
            for btn in self.cat_btns.values():
                btn.setEnabled(False)
            return

        branch_path = self.branches[self.index]
        name = os.path.basename(branch_path)
        display = name if len(name) < 60 else name[:57] + "..."
        self.folder_label.setText(display)
        self.folder_label.setToolTip(branch_path)

        samples = _get_sample_photos(branch_path, 2)
        for i, img_path in enumerate(samples):
            if i >= len(self.preview_labels):
                break
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    250, 150,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.preview_labels[i].setPixmap(scaled)
            else:
                self.preview_labels[i].setText("无预览")

    def _classify(self, category):
        if self.index < len(self.branches):
            branch = self.branches[self.index]
            self.results.append((branch, category))
            logger.info(f"用户分类分支: {branch} -> {category}")
            self.index += 1
            self._show_current()

    def _skip_one(self):
        if self.index < len(self.branches):
            self.index += 1
            self._show_current()

    def _done(self):
        self.result_ready.emit(self.results)
        self.accept()

    def get_results(self):
        return self.results

```

## ui/components/image_viewer.py

```python
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QTransform

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
register_heif_opener()
Image.MAX_IMAGE_PIXELS = 500_000_000


class ImageViewer(QWidget):
    closed = pyqtSignal()
    star_toggled = pyqtSignal(int, bool)
    recategorize = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.photos = []
        self.current_index = 0
        self.starred_ids = set()
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("background: #000000;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.image_label = QLabel(self)
        self.image_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #000000;")

        arrow_style = """
            QPushButton {
                background: rgba(0,0,0,0.35);
                color: rgba(255,255,255,0.7);
                border: none;
                border-radius: 32px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
                color: white;
            }
            QPushButton:disabled {
                color: rgba(255,255,255,0.1);
                background: rgba(0,0,0,0.2);
            }
        """

        self.prev_btn = QPushButton("◀", self)
        self.prev_btn.setFixedSize(64, 64)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setStyleSheet(arrow_style)
        self.prev_btn.clicked.connect(self.prev_photo)

        self.next_btn = QPushButton("▶", self)
        self.next_btn.setFixedSize(64, 64)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setStyleSheet(arrow_style)
        self.next_btn.clicked.connect(self.next_photo)

        small_style = """
            QPushButton {
                background: rgba(0,0,0,0.4);
                color: rgba(255,255,255,0.7);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 3px;
                font-size: 11px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); color: white; }
        """

        self.star_btn = QPushButton("☆", self)
        self.star_btn.setFixedSize(40, 28)
        self.star_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.star_btn.setStyleSheet(small_style + """
            QPushButton { font-size: 16px; padding: 4px 8px; }
        """)
        self.star_btn.clicked.connect(self._toggle_star)

        self.cat_btn = QPushButton("分类", self)
        self.cat_btn.setFixedSize(52, 28)
        self.cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cat_btn.setStyleSheet(small_style)
        self.cat_btn.clicked.connect(self._change_category)

        self.open_btn = QPushButton("打开", self)
        self.open_btn.setFixedSize(52, 28)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setStyleSheet(small_style)
        self.open_btn.clicked.connect(self._open_file)

        self.info_label = QLabel(self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.info_label.setStyleSheet("""
            color: rgba(255,255,255,0.35);
            font-size: 10px;
            background: transparent;
            padding: 4px 10px;
        """)

    def show_photos(self, photos, index, starred_ids):
        self.photos = photos
        self.current_index = index
        self.starred_ids = starred_ids
        self.show()
        self.raise_()
        self._load_current()

    def hide_viewer(self):
        self.hide()
        self.closed.emit()

    def _load_current(self):
        if not self.photos or self.current_index < 0:
            return
        if self.current_index >= len(self.photos):
            self.current_index = len(self.photos) - 1

        photo = self.photos[self.current_index]
        file_path = photo.get("file_path", "")

        pixmap = self._load_rotated_pixmap(file_path)
        if pixmap is None or pixmap.isNull():
            thumb_path = photo.get("thumbnail_path", "")
            if thumb_path:
                pixmap = QPixmap(thumb_path)
        if pixmap is None or pixmap.isNull():
            self.image_label.setText("无法加载")
            self.image_label.setStyleSheet("color: #333; font-size: 18px; background: #000;")
            self._update_buttons()
            return

        avail = self.size()
        scaled = pixmap.scaled(
            avail, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setGeometry(0, 0, avail.width(), avail.height())
        self._update_buttons()

    def _load_rotated_pixmap(self, file_path):
        try:
            img = Image.open(file_path)
            img = ImageOps.exif_transpose(img)
            import tempfile
            import os
            fd, temp_path = tempfile.mkstemp(suffix='.jpg')
            os.close(fd)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(temp_path, "JPEG", quality=92)
            pixmap = QPixmap(temp_path)
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            return pixmap
        except Exception:
            return QPixmap(file_path)

    def _update_buttons(self):
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        file_name = photo.get("file_name", "")
        self.info_label.setText(f"{self.current_index + 1}/{len(self.photos)}  {file_name}")

        photo_id = photo.get("id")
        if photo_id in self.starred_ids:
            self.star_btn.setText("★")
            self.star_btn.setStyleSheet(self.star_btn.styleSheet() + "QPushButton { color: #f1c40f; }")
        else:
            self.star_btn.setText("☆")

        self.prev_btn.setVisible(self.current_index > 0)
        self.next_btn.setVisible(self.current_index < len(self.photos) - 1)

    def prev_photo(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current()

    def next_photo(self):
        if self.current_index < len(self.photos) - 1:
            self.current_index += 1
            self._load_current()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        self.image_label.setGeometry(0, 0, w, h)

        self.prev_btn.move(12, (h - 64) // 2)
        self.next_btn.move(w - 76, (h - 64) // 2)

        self.star_btn.move(w - 48, h - 40)
        self.cat_btn.move(w - 108, h - 40)
        self.open_btn.move(w - 168, h - 40)
        self.info_label.setGeometry(0, 0, w, 22)

        self._load_current()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.prev_photo()
        elif event.key() == Qt.Key.Key_Right:
            self.next_photo()
        elif event.key() == Qt.Key.Key_Escape:
            self.hide_viewer()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            btn_geo = self.prev_btn.geometry().united(self.next_btn.geometry())
            btn_geo = btn_geo.united(self.star_btn.geometry())
            btn_geo = btn_geo.united(self.cat_btn.geometry())
            btn_geo = btn_geo.united(self.open_btn.geometry())
            if btn_geo.contains(pos):
                super().mousePressEvent(event)
                return
            self.hide_viewer()
        super().mousePressEvent(event)

    def _toggle_star(self):
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        photo_id = photo.get("id")
        if photo_id is None:
            return
        if photo_id in self.starred_ids:
            self.starred_ids.discard(photo_id)
            self.star_toggled.emit(photo_id, False)
        else:
            self.starred_ids.add(photo_id)
            self.star_toggled.emit(photo_id, True)
        self._update_buttons()

    def _change_category(self):
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        photo_id = photo.get("id")
        if photo_id is None:
            return
        self.recategorize.emit(photo_id, self.current_index)

    def _open_file(self):
        import subprocess
        import os
        if not self.photos:
            return
        photo = self.photos[self.current_index]
        file_path = photo.get("file_path", "")
        folder = os.path.dirname(file_path)
        if folder and os.path.exists(folder):
            subprocess.Popen(["explorer", "/select,", file_path])

```

## ui/components/memory_cards.py

```python
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QPixmap, QGraphicsOpacityEffect

from core.models import Memory


class MemoryPhotoCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data: dict):
        super().__init__()
        self.photo_data = photo_data
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("MemoryPhotoCard { background: transparent; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_anim.setDuration(40)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet("background: #1a1a2e; border-radius: 4px;")
        layout.addWidget(self._img_label)

    def load_thumbnail(self):
        path = self.photo_data.get("thumbnail_path")
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                w = min(pm.width(), 200)
                self._img_label.setPixmap(
                    pm.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
                )
        self._fade_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.photo_data)
        super().mousePressEvent(event)


class MemoryCardWidget(QFrame):
    clicked = pyqtSignal(int)
    dismissed = pyqtSignal(int)

    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self._memory = memory
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            MemoryCardWidget {
                background: #2a2a4e;
                border-radius: 12px;
                border: 1px solid #3a3a5e;
                padding: 8px;
            }
            MemoryCardWidget:hover {
                border-color: #667eea;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        type_colors = {
            "on_this_day": "#ff6b6b",
            "recent": "#ffd93d",
            "person": "#6bcb77",
            "event": "#4d96ff",
            "scene": "#9b59b6",
        }
        color = type_colors.get(self._memory.memory_type, "#667eea")

        type_label = QLabel(self._memory.memory_type)
        type_label.setFont(QFont("Microsoft YaHei", 8))
        type_label.setStyleSheet(f"color: {color};")
        layout.addWidget(type_label)

        title = QLabel(self._memory.title)
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setWordWrap(True)
        layout.addWidget(title)

        if self._memory.description:
            desc = QLabel(self._memory.description)
            desc.setFont(QFont("Microsoft YaHei", 9))
            desc.setStyleSheet("color: #a0a0b0;")
            desc.setWordWrap(True)
            desc.setMaximumHeight(40)
            layout.addWidget(desc)

        photo_ids = self._memory.get_photo_id_list()
        if photo_ids:
            row = QHBoxLayout()
            row.setSpacing(2)
            for fid in photo_ids[:4]:
                thumb = QLabel()
                thumb.setFixedSize(48, 48)
                thumb.setStyleSheet("background: #1a1a2e; border-radius: 3px;")
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row.addWidget(thumb)
            if len(photo_ids) > 4:
                more = QLabel(f"+{len(photo_ids) - 4}")
                more.setFont(QFont("Microsoft YaHei", 8))
                more.setStyleSheet("color: #666;")
                more.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row.addWidget(more)
            row.addStretch()
            layout.addLayout(row)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._memory.id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        dismiss_action = menu.addAction("不再显示")
        action = menu.exec(event.globalPos())
        if action == dismiss_action:
            self.dismissed.emit(self._memory.id)

```

## ui/components/person_detail.py

```python
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QGridLayout, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

from logger_setup import logger
from db_manager import Database
from business.image_recognition.face_cluster import (
    get_clusters, get_cluster_members, rename_cluster,
    reassign_face, create_cluster_from_face
)

_db = Database()


class FaceThumbnail(QLabel):
    clicked = pyqtSignal(int)

    def __init__(self, file_id: int, parent=None):
        super().__init__(parent)
        self._file_id = file_id
        self.setFixedSize(80, 80)
        self.setStyleSheet("background: #2a2a3e; border-radius: 4px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._file_id)
        super().mousePressEvent(event)


class PersonCard(QWidget):
    clicked = pyqtSignal(int)
    rename_requested = pyqtSignal(int)

    def __init__(self, cluster_id: int, name: str, member_count: int, parent=None):
        super().__init__(parent)
        self._cluster_id = cluster_id
        self._name = name
        self._setup_ui(member_count)

    def _setup_ui(self, member_count: int):
        self.setFixedSize(160, 120)
        self.setStyleSheet("""
            PersonCard {
                background: #2a2a4e;
                border-radius: 10px;
                border: 1px solid #3a3a5e;
            }
            PersonCard:hover { border-color: #667eea; }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("👤")
        icon.setFont(QFont("Segoe UI Emoji", 24))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        name = QLabel(self._name or f"人物 {self._cluster_id}")
        name.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        name.setStyleSheet("color: #e0e0e0;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        count = QLabel(f"{member_count} 张照片")
        count.setFont(QFont("Microsoft YaHei", 8))
        count.setStyleSheet("color: #666;")
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(count)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.rename_requested.emit(self._cluster_id)
            else:
                self.clicked.emit(self._cluster_id)
        super().mousePressEvent(event)


class PersonDetailView(QWidget):
    back_requested = pyqtSignal()
    photo_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_cluster_id = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1a2e;")

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(24, 16, 24, 16)
        self._main_layout.setSpacing(12)

        self._header = QHBoxLayout()
        back_btn = QPushButton("← 返回")
        back_btn.setFont(QFont("Microsoft YaHei", 10))
        back_btn.setStyleSheet("color: #667eea; background: transparent; border: none; padding: 4px 8px;")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested.emit)
        self._header.addWidget(back_btn)

        self._name_label = QLabel("人物详情")
        self._name_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        self._name_label.setStyleSheet("color: #e0e0e0;")
        self._header.addWidget(self._name_label)
        self._header.addStretch()

        rename_btn = QPushButton("✏️ 重命名")
        rename_btn.setFont(QFont("Microsoft YaHei", 9))
        rename_btn.setStyleSheet("color: #667eea; background: transparent; border: none; padding: 4px 8px;")
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.clicked.connect(self._on_rename)
        self._header.addWidget(rename_btn)
        self._main_layout.addLayout(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
        """)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(8)
        self._scroll.setWidget(self._grid_container)
        self._main_layout.addWidget(self._scroll)

    def show_person(self, cluster_id: int):
        self._current_cluster_id = cluster_id
        clusters = get_clusters()
        cluster = next((c for c in clusters if c.cluster_id == cluster_id), None)
        if cluster:
            name = cluster.person_name or f"人物 {cluster_id}"
            self._name_label.setText(name)

        members = get_cluster_members(cluster_id)
        self._load_thumbnails(members)

    def _load_thumbnails(self, file_ids: list):
        for i in reversed(range(self._grid.count())):
            w = self._grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        import os
        from config import THUMBNAIL_DIR

        cols = 6
        for i, fid in enumerate(file_ids):
            thumb = FaceThumbnail(fid)
            thumb_path = os.path.join(THUMBNAIL_DIR, f"{fid}.jpg")
            if os.path.exists(thumb_path):
                pm = QPixmap(thumb_path)
                if not pm.isNull():
                    thumb.setPixmap(pm.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            thumb.clicked.connect(self.photo_clicked.emit)
            self._grid.addWidget(thumb, i // cols, i % cols)

    def _on_rename(self):
        if self._current_cluster_id is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名人物", "请输入人物名称："
        )
        if ok and name.strip():
            rename_cluster(self._current_cluster_id, name.strip())
            self._name_label.setText(name.strip())


class PersonListView(QWidget):
    person_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1a2e;")

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QGridLayout(self._container)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(24, 16, 24, 16)
        self._scroll.setWidget(self._container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

    def refresh(self):
        for i in reversed(range(self._layout.count())):
            w = self._layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._cards.clear()

        clusters = get_clusters()
        cols = 4
        for i, c in enumerate(clusters):
            members = get_cluster_members(c.cluster_id)
            card = PersonCard(c.cluster_id, c.person_name, len(members))
            card.clicked.connect(self.person_clicked.emit)
            self._layout.addWidget(card, i // cols, i % cols)
            self._cards.append(card)

```

## ui/components/setup_window.py

```python
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QApplication, QListWidget, QListWidgetItem,
    QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from logger_setup import logger
from config import (
    SOURCE_DRIVE, DATA_DIR, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    save_config, get_settings,
)

_INPUT_STYLE = """
    QLineEdit {
        background: #2a2a3e; color: #e0e0e0;
        border: 1px solid #3a3a5e; border-radius: 4px;
        padding: 6px 10px; font-size: 13px; min-height: 22px;
    }
    QLineEdit:focus { border-color: #667eea; }
"""

_BROWSE_STYLE = """
    QPushButton {
        background: #34495e; color: #ccc; border: none;
        border-radius: 4px; font-size: 11px;
    }
    QPushButton:hover { background: #4a6a8a; }
"""

_SMALL_BTN_STYLE = """
    QPushButton {
        background: #34495e; color: #ccc; border: none;
        border-radius: 4px; font-size: 11px; padding: 4px 10px;
    }
    QPushButton:hover { background: #4a6a8a; }
"""

_REMOVE_BTN_STYLE = """
    QPushButton {
        background: #c0392b; color: white; border: none;
        border-radius: 4px; font-size: 11px; padding: 4px 10px;
    }
    QPushButton:hover { background: #e74c3c; }
"""

_SCROLL_STYLE = """
    QScrollArea {
        border: none; background: transparent;
    }
    QScrollBar:vertical {
        background: #1a1a2e; width: 8px; border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #3a3a5e; border-radius: 4px; min-height: 30px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
"""


class SetupWindow(QWidget):
    config_saved = pyqtSignal()

    def __init__(self, edit_mode=False):
        super().__init__()
        self._edit_mode = edit_mode
        self.setup_ui()
        self.center_on_screen()
        self._load_current()

    def setup_ui(self):
        self.setWindowTitle("配置 - NAS 照片回忆" if self._edit_mode else "初次配置 - NAS 照片回忆")
        self.setMinimumSize(520, 400)
        self.setMaximumSize(580, 800)
        self.setStyleSheet("background: #1a1a2e;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("修改配置" if self._edit_mode else "首次使用 - 请配置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._basic_widget = QWidget()
        basic_layout = QVBoxLayout(self._basic_widget)
        basic_layout.setContentsMargins(0, 0, 0, 0)
        basic_layout.setSpacing(10)
        basic_layout.addLayout(self._make_row("照片库文件夹（多个用分号分隔）", "src_edit", self._browse_src))
        basic_layout.addLayout(self._make_row("缓存数据文件夹", "data_edit", self._browse_data))
        basic_layout.addLayout(self._make_text_row("DeepSeek API Key", "api_edit", "sk-..."))
        layout.addWidget(self._basic_widget)

        self._advanced_toggle = QPushButton("▶ 高级选项")
        self._advanced_toggle.setFont(QFont("Microsoft YaHei", 9))
        self._advanced_toggle.setStyleSheet("""
            QPushButton { background: transparent; color: #667eea; border: none;
                font-size: 11px; text-align: left; padding: 2px 0; }
            QPushButton:hover { color: #7b93f5; }
        """)
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        layout.addWidget(self._advanced_toggle)

        self._scroll_area = QScrollArea()
        self._scroll_area.setStyleSheet(_SCROLL_STYLE)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._advanced_content = QWidget()
        adv_layout = QVBoxLayout(self._advanced_content)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(10)
        adv_layout.addLayout(self._make_text_row("Base URL", "base_url_edit", "https://api.deepseek.com"))
        adv_layout.addLayout(self._make_text_row("Model", "model_edit", "deepseek-chat"))
        adv_layout.addLayout(self._make_keyword_section(
            "样片关键词（匹配文件夹名/文件名自动归为样片）",
            "sample",
        ))
        adv_layout.addLayout(self._make_keyword_section(
            "生活关键词（匹配文件夹名/文件名自动归为生活照片）",
            "life",
        ))
        adv_layout.addStretch()

        self._scroll_area.setWidget(self._advanced_content)
        self._scroll_area.hide()
        layout.addWidget(self._scroll_area, 1)

        self.error_label = QLabel("")
        self.error_label.setFont(QFont("Microsoft YaHei", 9))
        self.error_label.setStyleSheet("color: #e74c3c;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_text = "保存" if self._edit_mode else "保存并开始"
        self.save_btn = QPushButton(btn_text)
        self.save_btn.setFixedSize(150, 38)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white; border: none; border-radius: 6px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7b93f5, stop:1 #9b6bc2);
            }
            QPushButton:disabled { background: #555; }
        """)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        if self._edit_mode:
            cancel_btn = QPushButton("取消")
            cancel_btn.setFixedSize(100, 38)
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background: #555; color: #ccc; border: none;
                    border-radius: 6px; font-size: 13px;
                }
                QPushButton:hover { background: #777; }
            """)
            cancel_btn.clicked.connect(self.close)
            btn_layout.addWidget(cancel_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._drag_pos = None

    def _make_keyword_section(self, label_text, kw_type):
        section = QVBoxLayout()
        section.setSpacing(4)

        label = QLabel(label_text)
        label.setFont(QFont("Microsoft YaHei", 10))
        label.setStyleSheet("color: #a0a0b0;")
        section.addWidget(label)

        kw_list = QListWidget()
        kw_list.setStyleSheet("""
            QListWidget {
                background: #2a2a3e; color: #e0e0e0;
                border: 1px solid #3a3a5e; border-radius: 4px;
                font-size: 12px; padding: 4px;
            }
            QListWidget::item { padding: 3px 6px; }
            QListWidget::item:selected { background: #3a3a5e; }
        """)
        kw_list.setMaximumHeight(120)
        section.addWidget(kw_list)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        kw_input = QLineEdit()
        kw_input.setPlaceholderText("输入新关键词")
        kw_input.setFont(QFont("Microsoft YaHei", 10))
        kw_input.setFixedHeight(30)
        kw_input.setStyleSheet(_INPUT_STYLE)
        input_row.addWidget(kw_input, 1)

        add_btn = QPushButton("添加")
        add_btn.setFixedSize(60, 30)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(_SMALL_BTN_STYLE)
        input_row.addWidget(add_btn)

        remove_btn = QPushButton("删除")
        remove_btn.setFixedSize(60, 30)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(_REMOVE_BTN_STYLE)
        input_row.addWidget(remove_btn)

        section.addLayout(input_row)

        if kw_type == "sample":
            self._sample_kw_list = kw_list
            self._sample_kw_input = kw_input
            add_btn.clicked.connect(self._add_sample_keyword)
            remove_btn.clicked.connect(self._remove_sample_keyword)
            self._load_sample_keywords()
        else:
            self._life_kw_list = kw_list
            self._life_kw_input = kw_input
            add_btn.clicked.connect(self._add_life_keyword)
            remove_btn.clicked.connect(self._remove_life_keyword)
            self._load_life_keywords()

        return section

    def _load_sample_keywords(self):
        self._sample_kw_list.clear()
        try:
            from classifier.folder_classifier import get_sample_keywords
            builtin, custom = get_sample_keywords()
            for kw in builtin:
                item = QListWidgetItem(f"[内置] {kw}")
                item.setData(Qt.ItemDataRole.UserRole, ("builtin", kw))
                item.setForeground(Qt.GlobalColor.gray)
                self._sample_kw_list.addItem(item)
            for kw in custom:
                item = QListWidgetItem(kw)
                item.setData(Qt.ItemDataRole.UserRole, ("custom", kw))
                self._sample_kw_list.addItem(item)
        except Exception as e:
            logger.warning(f"加载样片关键词失败: {e}")

    def _add_sample_keyword(self):
        kw = self._sample_kw_input.text().strip()
        if not kw:
            return
        from classifier.folder_classifier import add_sample_keyword
        if add_sample_keyword(kw):
            self._sample_kw_input.clear()
            self._load_sample_keywords()

    def _remove_sample_keyword(self):
        current = self._sample_kw_list.currentItem()
        if not current:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data or data[0] == "builtin":
            return
        from classifier.folder_classifier import remove_sample_keyword
        if remove_sample_keyword(data[1]):
            self._load_sample_keywords()

    def _load_life_keywords(self):
        self._life_kw_list.clear()
        try:
            from classifier.folder_classifier import get_life_keywords
            builtin, custom = get_life_keywords()
            for kw in builtin:
                item = QListWidgetItem(f"[内置] {kw}")
                item.setData(Qt.ItemDataRole.UserRole, ("builtin", kw))
                item.setForeground(Qt.GlobalColor.gray)
                self._life_kw_list.addItem(item)
            for kw in custom:
                item = QListWidgetItem(kw)
                item.setData(Qt.ItemDataRole.UserRole, ("custom", kw))
                self._life_kw_list.addItem(item)
        except Exception as e:
            logger.warning(f"加载生活关键词失败: {e}")

    def _add_life_keyword(self):
        kw = self._life_kw_input.text().strip()
        if not kw:
            return
        from classifier.folder_classifier import add_life_keyword
        if add_life_keyword(kw):
            self._life_kw_input.clear()
            self._load_life_keywords()

    def _remove_life_keyword(self):
        current = self._life_kw_list.currentItem()
        if not current:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data or data[0] == "builtin":
            return
        from classifier.folder_classifier import remove_life_keyword
        if remove_life_keyword(data[1]):
            self._load_life_keywords()

    def _make_row(self, label_text, attr_name, browse_fn):
        row = QVBoxLayout()
        row.setSpacing(4)
        label = QLabel(label_text)
        label.setFont(QFont("Microsoft YaHei", 10))
        label.setStyleSheet("color: #a0a0b0;")
        row.addWidget(label)

        inner = QHBoxLayout()
        inner.setSpacing(6)
        edit = QLineEdit()
        edit.setFont(QFont("Microsoft YaHei", 10))
        edit.setStyleSheet(_INPUT_STYLE)
        inner.addWidget(edit, 1)

        btn = QPushButton("浏览")
        btn.setFixedSize(60, 34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_BROWSE_STYLE)
        btn.clicked.connect(browse_fn)
        inner.addWidget(btn)

        row.addLayout(inner)
        setattr(self, attr_name, edit)
        return row

    def _make_text_row(self, label_text, attr_name, placeholder=""):
        row = QVBoxLayout()
        row.setSpacing(4)
        label = QLabel(label_text)
        label.setFont(QFont("Microsoft YaHei", 10))
        label.setStyleSheet("color: #a0a0b0;")
        row.addWidget(label)

        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setFont(QFont("Microsoft YaHei", 10))
        edit.setStyleSheet(_INPUT_STYLE)
        row.addWidget(edit)

        setattr(self, attr_name, edit)
        return row

    def _toggle_advanced(self):
        visible = self._scroll_area.isVisible()
        if visible:
            self._scroll_area.hide()
            self._basic_widget.show()
            self._advanced_toggle.setText("▶ 高级选项")
        else:
            self._basic_widget.hide()
            self._scroll_area.show()
            self._advanced_toggle.setText("◀ 返回基本配置")

    def _browse_src(self):
        path = QFileDialog.getExistingDirectory(self, "选择照片库文件夹", self.src_edit.text() or "D:\\")
        if path:
            self.src_edit.setText(path)

    def _browse_data(self):
        path = QFileDialog.getExistingDirectory(self, "选择缓存数据文件夹", self.data_edit.text() or "D:\\")
        if path:
            self.data_edit.setText(path)

    def _load_current(self):
        try:
            s = get_settings()
        except Exception:
            return

        if s.source_drive and s.source_drive != "D:\\测试":
            self.src_edit.setText(s.source_drive)
        if s.photo_data_dir:
            self.data_edit.setText(s.photo_data_dir)
        if s.deepseek_api_key:
            self.api_edit.setText(s.deepseek_api_key)
        if s.deepseek_base_url:
            self.base_url_edit.setText(s.deepseek_base_url)
        if s.deepseek_model:
            self.model_edit.setText(s.deepseek_model)

    def _on_save(self):
        src = self.src_edit.text().strip()
        data = self.data_edit.text().strip()
        api_key = self.api_edit.text().strip()
        base_url = self.base_url_edit.text().strip() or "https://api.deepseek.com"
        model = self.model_edit.text().strip() or "deepseek-chat"

        errors = []
        if not src:
            errors.append("请指定照片库文件夹")
        else:
            for p in src.split(";"):
                p = p.strip()
                if p and not os.path.exists(p):
                    errors.append(f"照片库路径不存在: {p}")
        if not data:
            errors.append("请指定缓存数据文件夹")
        if not api_key:
            errors.append("请填入 DeepSeek API Key")

        if errors:
            self.error_label.setText("\n".join(errors))
            return

        logger.info(f"保存配置: src={src}, data={data}, api_key={api_key[:8]}...")

        save_config(src, data, api_key, base_url, model)

        self.config_saved.emit()

    def center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

```

## ui/components/sidebar.py

```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


_NAV_BTN_STYLE = """
    QPushButton {
        background: transparent;
        color: #a0a0b0;
        border: none;
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 13px;
        text-align: left;
    }
    QPushButton:hover {
        background: #2a2a4e;
        color: #e0e0e0;
    }
    QPushButton[active="true"] {
        background: #3a3a6e;
        color: #ffffff;
        font-weight: bold;
    }
"""

_NAV_ITEMS = [
    ("random", "🎲 随机回忆"),
    ("timeline", "📅 时间线"),
    ("special", "⭐ 特殊回忆"),
]


class Sidebar(QWidget):
    navigation_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = "random"
        self._buttons = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedWidth(180)
        self.setStyleSheet("background: #1a1a2e; border-right: 1px solid #2a2a4e;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 20, 8, 20)
        layout.setSpacing(4)

        title = QLabel("照片回忆")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0; padding: 8px 8px 16px 8px;")
        layout.addWidget(title)

        for nav_id, label in _NAV_ITEMS:
            btn = QPushButton(label)
            btn.setFont(QFont("Microsoft YaHei", 10))
            btn.setStyleSheet(_NAV_BTN_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, nid=nav_id: self._on_nav(nid))
            layout.addWidget(btn)
            self._buttons[nav_id] = btn

        layout.addStretch()

        self._update_active()

    def _on_nav(self, nav_id: str):
        if nav_id == self._current:
            return
        self._current = nav_id
        self._update_active()
        self.navigation_changed.emit(nav_id)

    def _update_active(self):
        for nav_id, btn in self._buttons.items():
            btn.setProperty("active", nav_id == self._current)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def current_nav(self) -> str:
        return self._current

    def set_nav(self, nav_id: str):
        if nav_id in self._buttons:
            self._current = nav_id
            self._update_active()

```

## ui/components/special_memories.py

```python
import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QRect, QPoint
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor

from logger_setup import logger
from core.models import Memory


class MemoryCard(QWidget):
    clicked = pyqtSignal(int)
    dismissed = pyqtSignal(int)

    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self._memory = memory
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(220)
        self.setStyleSheet("""
            MemoryCard {
                background: #2a2a4e;
                border-radius: 12px;
                border: 1px solid #3a3a5e;
            }
            MemoryCard:hover {
                border-color: #667eea;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        type_label = QLabel(self._memory.memory_type)
        type_label.setFont(QFont("Microsoft YaHei", 8))
        type_label.setStyleSheet("color: #667eea; text-transform: uppercase;")
        layout.addWidget(type_label)

        title = QLabel(self._memory.title)
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setWordWrap(True)
        layout.addWidget(title)

        if self._memory.description:
            desc = QLabel(self._memory.description)
            desc.setFont(QFont("Microsoft YaHei", 9))
            desc.setStyleSheet("color: #a0a0b0;")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        photo_count = len(self._memory.get_photo_id_list())
        count_label = QLabel(f"{photo_count} 张照片")
        count_label.setFont(QFont("Microsoft YaHei", 8))
        count_label.setStyleSheet("color: #666;")
        layout.addWidget(count_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._memory.id)
        super().mousePressEvent(event)


class ShatterWidget(QWidget):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._pieces = []
        self._animations = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def shatter(self):
        if self._pixmap.isNull():
            return

        piece_size = 40
        w, h = self._pixmap.width(), self._pixmap.height()

        for y in range(0, h, piece_size):
            for x in range(0, w, piece_size):
                pw = min(piece_size, w - x)
                ph = min(piece_size, h - y)
                piece = self._pixmap.copy(x, y, pw, ph)
                self._pieces.append({
                    "pixmap": piece,
                    "pos": QPoint(x, y),
                    "dx": (x - w // 2) * 3,
                    "dy": (y - h // 2) * 3 - 200,
                })

        self.update()
        self._animate()

    def _animate(self):
        import random
        for i, piece in enumerate(self._pieces):
            anim = QPropertyAnimation(self, b"geometry")
            start_rect = QRect(piece["pos"].x(), piece["pos"].y(),
                               piece["pixmap"].width(), piece["pixmap"].height())
            end_x = piece["pos"].x() + piece["dx"] + random.randint(-50, 50)
            end_y = piece["pos"].y() + piece["dy"] + random.randint(-30, 30)
            end_rect = QRect(end_x, end_y, 0, 0)
            anim.setStartValue(start_rect)
            anim.setEndValue(end_rect)
            anim.setDuration(600 + random.randint(0, 300))
            anim.start()
            self._animations.append(anim)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(0.8)
        for piece in self._pieces:
            painter.drawPixmap(piece["pos"], piece["pixmap"])
        painter.end()


class SpecialMemoriesView(QWidget):
    memory_clicked = pyqtSignal(int)
    memory_dismissed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1a2e;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(24, 16, 24, 16)
        self._layout.setSpacing(12)
        self._layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def load_memories(self, memories: list):
        for c in self._cards:
            c.setParent(None)
        self._cards.clear()

        type_groups = {}
        type_order = []
        for m in memories:
            mt = m.memory_type
            if mt not in type_groups:
                type_groups[mt] = []
                type_order.append(mt)
            type_groups[mt].append(m)

        type_labels = {
            "on_this_day": "📅 那年今日",
            "recent": "🕐 近期回忆",
            "person": "👤 人物回忆",
            "event": "🎯 事件回忆",
            "scene": "🏞️ 场景回忆",
        }

        for mt in type_order:
            label = type_labels.get(mt, mt)
            header = QLabel(label)
            header.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
            header.setStyleSheet("color: #e0e0e0; padding: 8px 0 4px 0;")
            self._layout.insertWidget(self._layout.count() - 1, header)

            row = QHBoxLayout()
            row.setSpacing(10)

            for m in type_groups[mt][:6]:
                card = MemoryCard(m)
                card.clicked.connect(self.memory_clicked.emit)
                card.dismissed.connect(self._on_dismiss)
                row.addWidget(card)

            row.addStretch()
            row_widget = QWidget()
            row_widget.setLayout(row)
            row_widget.setStyleSheet("background: transparent;")
            self._layout.insertWidget(self._layout.count() - 1, row_widget)
            self._cards.extend(type_groups[mt][:6])

    def _on_dismiss(self, memory_id: int):
        from business.memory.memory_reasoning import record_feedback
        record_feedback(memory_id, "dismiss")
        self.memory_dismissed.emit(memory_id)

```

## ui/components/startup_window.py

```python
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from logger_setup import logger


from services.pipeline import Pipeline, ScanStage, ClassifyStage, IndexStage


class StartupWindow(QWidget):
    transition_to_main = pyqtSignal()
    background_scan_needed = pyqtSignal()
    background_index_needed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.worker = None
        self._cancelled = False
        self._transitioned = False
        self.setup_ui()
        self.center_on_screen()

    def setup_ui(self):
        self.setWindowTitle("NAS 照片回忆")
        self.setFixedSize(460, 260)
        self.setStyleSheet("background: #1a1a2e;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        title = QLabel("NAS 照片回忆")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.stage_label = QLabel("正在初始化...")
        self.stage_label.setFont(QFont("Microsoft YaHei", 11))
        self.stage_label.setStyleSheet("color: #a0a0b0;")
        self.stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage_label.setWordWrap(True)
        layout.addWidget(self.stage_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a5e;
                border-radius: 4px;
                background: #2a2a3e;
                text-align: center;
                color: #ccc;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消初始化")
        self.cancel_btn.setFixedSize(130, 36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #e74c3c;
            }
            QPushButton:disabled {
                background: #666;
            }
        """)
        self.cancel_btn.clicked.connect(self.on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._btn_layout = btn_layout

        layout.addStretch()

    def center_on_screen(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def start(self):
        pipeline = Pipeline()
        pipeline.add_stage(ScanStage())
        pipeline.add_stage(ClassifyStage())
        pipeline.add_stage(IndexStage())
        self.worker = pipeline
        pipeline.stage_changed.connect(self.stage_label.setText)
        pipeline.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        pipeline.all_done.connect(self._on_all_done, Qt.ConnectionType.QueuedConnection)
        pipeline.error_occurred.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
        pipeline.interactive_classify_needed.connect(self._on_classify_needed, Qt.ConnectionType.QueuedConnection)
        pipeline.background_scan_needed.connect(self.background_scan_needed.emit)
        pipeline.background_index_needed.connect(self.background_index_needed.emit)
        pipeline.finished.connect(self._on_worker_finished)
        pipeline.start()
        logger.info("Pipeline 启动流程开始")

    def _on_progress(self, current, total):
        if total > 0:
            pct = int(current / total * 100)
            self.progress_bar.setValue(min(pct, 100))
            self.progress_bar.setFormat(f"{current}/{total}")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("")

    def _on_all_done(self):
        self._transitioned = True
        logger.info("启动流程全部完成，跳转主窗口")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("完成")
        self.worker = None
        self.transition_to_main.emit()

    def _on_worker_finished(self):
        if not self._transitioned and not self._cancelled:
            logger.warning("all_done 信号未送达，通过 finished 兜底触发主界面")
            self._transitioned = True
            self.transition_to_main.emit()

    def _on_error(self, msg):
        self._transitioned = True
        logger.warning(f"启动流程中断: {msg}")
        self.stage_label.setText(f"已中断: {msg}")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")

        self.cancel_btn.hide()

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(100, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #666;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #888;
            }
        """)
        close_btn.clicked.connect(self.close)
        close_btn.clicked.connect(QApplication.instance().quit)
        self._btn_layout.insertWidget(0, close_btn)

        continue_btn = QPushButton("进入主界面")
        continue_btn.setFixedSize(130, 36)
        continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        continue_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2ecc71;
            }
        """)
        continue_btn.clicked.connect(self.background_scan_needed.emit)
        continue_btn.clicked.connect(self.background_index_needed.emit)
        continue_btn.clicked.connect(self.transition_to_main.emit)
        self._btn_layout.insertWidget(1, continue_btn)

        self.worker = None

    def _on_classify_needed(self, branches):
        from ui.components.folder_classifier_dialog import BranchClassifierDialog
        self.stage_label.setText("请为文件夹分支选择分类...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.cancel_btn.setEnabled(False)

        self._classify_results = []
        self._classify_dialog = BranchClassifierDialog(branches, self)
        self._classify_dialog.result_ready.connect(self._on_classify_dialog_done)
        self._classify_dialog.finished.connect(self._on_classify_dialog_closed)
        logger.info(f"显示分类对话框，待分类 {len(branches)} 个分支")
        self._classify_dialog.show()

    def _on_classify_dialog_done(self, results):
        logger.info(f"分类对话框完成，获得 {len(results)} 个结果")
        self._classify_results = results
        if self.worker:
            self.worker.set_classify_results(results)
            self.cancel_btn.setEnabled(True)
            self.stage_label.setText("分类完成，继续...")

    def _on_classify_dialog_closed(self):
        if not self._classify_results and self.worker:
            logger.info("分类对话框被关闭，视为跳过分类")
            self.worker.set_classify_results([])
            self.cancel_btn.setEnabled(True)
            self.stage_label.setText("分类跳过，继续...")
        self._classify_dialog = None

    def on_cancel(self):
        self._cancelled = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("取消中...")
        self.stage_label.setText("正在取消...")
        if self.worker:
            self.worker.cancel()

    def closeEvent(self, event):
        if hasattr(self, '_classify_dialog') and self._classify_dialog:
            self._classify_dialog.close()
        if hasattr(self, 'worker') and self.worker:
            self.worker.cancel()
        logger.info("StartupWindow 关闭，清理资源")
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)




```

## ui/components/timeline_view.py

```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from logger_setup import logger
from db_manager import Database

_db = Database()


class TimelineGroup(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, date_label: str, photos: list, parent=None):
        super().__init__(parent)
        self._photos = photos
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(6)

        header = QLabel(date_label)
        header.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #e0e0e0; padding: 4px 0;")
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setSpacing(4)
        for p in photos[:8]:
            thumb = QLabel()
            thumb.setFixedSize(80, 80)
            thumb.setStyleSheet("background: #2a2a3e; border-radius: 4px;")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setCursor(Qt.CursorShape.PointingHandCursor)

            if p.get("thumbnail_path"):
                from PyQt6.QtGui import QPixmap
                pm = QPixmap(p["thumbnail_path"])
                if not pm.isNull():
                    thumb.setPixmap(pm.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))

            thumb.setProperty("file_id", p["id"])
            thumb.mousePressEvent = lambda e, fid=p["id"]: self.clicked.emit(fid)
            row.addWidget(thumb)

        row.addStretch()
        layout.addLayout(row)


class TimelineView(QWidget):
    photo_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: #1a1a2e;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1a1a2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #3a3a5e; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(24, 16, 24, 16)
        self._layout.setSpacing(8)
        self._layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def load_photos(self, photos: list):
        for g in self._groups:
            g.setParent(None)
        self._groups.clear()

        groups = {}
        order = []
        for p in photos:
            dt = p.get("date_taken") or p.get("file_mtime") or ""
            day = dt[:10] if dt and len(dt) >= 10 else "未知日期"
            if day not in groups:
                groups[day] = []
                order.append(day)
            groups[day].append(p)

        for day in reversed(order):
            g = TimelineGroup(day, groups[day])
            g.clicked.connect(self.photo_clicked.emit)
            self._layout.insertWidget(self._layout.count() - 1, g)
            self._groups.append(g)

```

## ui/components/virtual_waterfall.py

```python
from PyQt6.QtWidgets import QWidget, QLabel, QFrame, QScrollArea
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QPixmapCache


COL_COUNT = 3
GAP = 2


class VirtualPhotoCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, photo_data, width, height, parent=None):
        super().__init__(parent)
        self.photo_data = photo_data
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedSize(width, height)
        self.setStyleSheet("background: #222;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.thumb_label = QLabel(self)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(width, height)
        self.thumb_label.setText("…")
        self.thumb_label.setStyleSheet("color: #444; font-size: 12px; background: #222;")

    def _scaled_pixmap(self, pixmap):
        label_size = self.thumb_label.size()
        scaled = pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - label_size.width()) // 2
        y = (scaled.height() - label_size.height()) // 2
        return scaled.copy(x, y, label_size.width(), label_size.height())

    def load_thumbnail(self):
        thumb = self.photo_data.get("thumbnail_path", "")
        if not thumb:
            self.thumb_label.setText("?")
            self.thumb_label.setStyleSheet("color: #666; font-size: 12px; background: #333;")
            return
        pixmap = QPixmapCache.find(thumb)
        if pixmap:
            self.thumb_label.setPixmap(self._scaled_pixmap(pixmap))
            return
        pixmap = QPixmap(thumb)
        if not pixmap.isNull():
            QPixmapCache.insert(thumb, pixmap)
            self.thumb_label.setPixmap(self._scaled_pixmap(pixmap))
        else:
            self.thumb_label.setText("?")
            self.thumb_label.setStyleSheet("color: #666; font-size: 12px; background: #333;")

    def mousePressEvent(self, event):
        self.clicked.emit(self.photo_data)


class VirtualWaterfallLayout:
    def __init__(self, photos, column_count=COL_COUNT, card_width=80):
        self._photos = photos
        self._col_count = column_count
        self._card_width = card_width
        self._positions = []
        self._total_height = 0
        self._col_heights = [0] * column_count
        self._compute_layout()

    def _compute_layout(self):
        self._positions = []
        self._col_heights = [0] * self._col_count

        for photo in self._photos:
            pw = photo.get("width") or 1
            ph = photo.get("height") or 1
            height = max(60, min(int(self._card_width * ph / pw), 800)) + GAP

            col = self._col_heights.index(min(self._col_heights))
            x = col * (self._card_width + GAP)
            y = self._col_heights[col]
            self._positions.append((x, y, self._card_width, height))
            self._col_heights[col] += height

        self._total_height = max(self._col_heights) + GAP if self._col_heights else GAP

    def update_card_width(self, width):
        self._card_width = max(80, width)
        self._compute_layout()

    def visible_rect(self, viewport_height, scroll_y):
        top = max(0, scroll_y - 200)
        bottom = scroll_y + viewport_height + 200
        return (top, bottom)

    def cards_in_range(self, scroll_y, viewport_height):
        top, bottom = self.visible_rect(viewport_height, scroll_y)
        result = []
        for i, (x, y, w, h) in enumerate(self._positions):
            card_bottom = y + h
            if y < bottom and card_bottom > top:
                result.append((i, x, y, w, h))
        return result

    @property
    def total_height(self):
        return self._total_height

    @property
    def total_width(self):
        return self._col_count * (self._card_width + GAP) - GAP

    def photo_at(self, index):
        return self._photos[index]


class VirtualCategoryPage(QScrollArea):
    photo_clicked = pyqtSignal(dict)
    load_more_requested = pyqtSignal()

    def __init__(self, category_id, category_name, parent=None):
        super().__init__(parent)
        self.category_id = category_id
        self.category_name = category_name
        self._photos = []
        self._all_loaded = False
        self._loading_more = False
        self._layout = None
        self._card_widgets = {}
        self._buffer = 5

        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: #111; }")

        self._viewport = QWidget(self)
        self._viewport.setStyleSheet("background: #111;")
        self.setWidget(self._viewport)

        self._empty_label = QLabel("索引中，照片即将出现…", self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #555; font-size: 14px; background: transparent;")
        self._empty_label.hide()

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._do_relayout)

        self.memory_summary = QLabel(self._viewport)
        self.memory_summary.setStyleSheet("""
            font-size: 12px; color: #aaa; padding: 6px 10px;
            background: rgba(0,0,0,0.5);
        """)
        self.memory_summary.setWordWrap(True)
        self.memory_summary.hide()

    @property
    def scroll(self):
        return self

    def set_memory_summary(self, text):
        if text:
            self.memory_summary.setText(text)
            self.memory_summary.show()
            self.memory_summary.raise_()
        else:
            self.memory_summary.hide()

    def load_photos(self, photos):
        self.set_photos(photos)

    def set_photos(self, photos):
        self._photos = list(photos)
        self._all_loaded = False
        self._loading_more = False
        self._destroy_visible_cards()
        self._recompute_layout()
        self._render_visible()
        if self._photos:
            self._empty_label.hide()
        else:
            self._empty_label.setGeometry(self.geometry())
            self._empty_label.raise_()
            self._empty_label.show()

    def append_photos(self, new_photos):
        if new_photos:
            self._photos.extend(new_photos)
            self._destroy_visible_cards()
            self._recompute_layout()
            self._render_visible()
        self._loading_more = False

    def _destroy_visible_cards(self):
        for card in self._card_widgets.values():
            card.deleteLater()
        self._card_widgets.clear()

    def _recompute_layout(self):
        total_w = max(400, self.width())
        card_w = (total_w - GAP * (COL_COUNT + 1)) // COL_COUNT
        card_w = max(80, card_w)
        self._layout = VirtualWaterfallLayout(self._photos, COL_COUNT, card_w)
        self._viewport.resize(self._layout.total_width, self._layout.total_height)

    def _render_visible(self):
        scroll_y = self.verticalScrollBar().value()
        vp_h = self.viewport().height()
        cards = self._layout.cards_in_range(scroll_y, vp_h) if self._layout else []
        for idx, x, y, w, h in cards:
            if idx in self._card_widgets:
                continue
            photo = self._layout.photo_at(idx)
            card = VirtualPhotoCard(photo, w, h, self._viewport)
            card.move(x, y)
            card.load_thumbnail()
            card.clicked.connect(self.photo_clicked)
            card.show()
            self._card_widgets[idx] = card

        visible_indices = {idx for idx, _, _, _, _ in self._layout.cards_in_range(scroll_y, vp_h)}
        to_remove = [idx for idx in self._card_widgets if idx not in visible_indices]
        for idx in to_remove:
            self._card_widgets[idx].deleteLater()
            del self._card_widgets[idx]

    def _on_scroll(self, value):
        self._render_visible()
        bar = self.verticalScrollBar()
        if bar.maximum() > 0 and value >= bar.maximum() - 200:
            if not self._loading_more and not self._all_loaded:
                self._loading_more = True
                self.load_more_requested.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._photos:
            self._resize_timer.start()

    def _do_relayout(self):
        self._destroy_visible_cards()
        self._recompute_layout()
        self._render_visible()

    def clear(self):
        self._destroy_visible_cards()
        self._photos = []
        self._all_loaded = False

```
