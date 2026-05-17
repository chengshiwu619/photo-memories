# NAS 照片回忆 - v0.3 架构

## 1. 分层架构

```
UI 层 (ui/)          → app.py / components/ / recommendation
服务层 (services/)    → background_task_manager
业务层 (business/)    → scanner / classifier / indexer / image_recognition / memory
基础设施层 (infra/)   → llm / db/repositories / image
核心层 (core/)        → models / config / db_manager / logger / checkpoint_manager
```

### 层间依赖规则

- 严格单向依赖：上层可调用下层，下层禁止调用上层
- 跨层调用必须通过层间接口表（§11），禁止直接 import 层内未导出模块
- UI 层禁止直接写 SQL，必须通过 Repository 或 db_manager
- 业务层禁止直接操作 UI 组件
- AI 识别任务使用缩略图，不读取原图
- 涉及用户照片的删除/移动操作，永远走"标记"而非物理操作

## 2. 模块职责

### 2.1 核心层

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | `config.py` | Settings 单例（get_settings()）、环境变量、多照片库路径（source_dirs 分号分隔）、UNC 反斜杠自动修复 |
| 数据库 | `db_manager.py` | SQLite 连接管理、表结构定义与初始化、版本自动迁移 |
| 数据模型 | `core/models.py` | File, PhotoMetadata, Memory, FaceEmbedding, FaceCluster, Event, MemoryReasoning, TaskCheckpoint |
| 日志 | `logger_setup.py` | 多文件分级（app/error/crash.log）、excepthook 接管、启动崩溃 marker |
| 断点 | `checkpoint_manager.py` | 通用长任务断点持久化（task_checkpoints 表） |

### 2.2 基础设施层

| 模块 | 文件 | 职责 |
|------|------|------|
| LLM | `infra/llm/client.py` | OpenAI 兼容客户端封装、重试策略 |
| 数据仓库 | `infra/db/repositories/` | FilesRepo, PhotoMetadataRepo, MemoriesRepo, PhotoTagsRepo, FaceEmbeddingsRepo, EventsRepo, ClickHistoryRepo |
| CLIP编码器 | `infra/image/clip_encoder.py` | SigLIP/OpenCLIP 图像嵌入提取（使用缩略图） |
| 人脸检测 | `infra/image/face_detector.py` | DeepFace + ArcFace（512维，使用缩略图） |
| 目标检测 | `infra/image/object_detector.py` | LibreYOLO ONNX（onnxruntime，MIT 许可） |
| 缩略图加载 | `infra/image/thumbnail_loader.py` | LRU 缓存（256张），识别模块共享 |

### 2.3 业务层

| 模块 | 文件 | 职责 |
|------|------|------|
| 扫描 | `business/scanner/fast_scan.py` | Everything/os.walk 文件发现、NAS 盘符↔UNC↔IP 双向匹配+规范化、GBK 解码 |
| 分类 | `business/classifier/folder_classifier.py` | 关键词预分类 + LLM 分类 + 后台精分类 |
| 索引 | `business/indexer/photo_indexer.py` | EXIF 提取、缩略图生成、感知哈希去重 |
| 图像标签 | `business/image_recognition/tag_generator.py` | SigLIP 嵌入标签生成 |
| 人脸聚类 | `business/image_recognition/face_cluster.py` | 人脸向量聚类、用户纠偏 |
| 场景聚类 | `business/image_recognition/scene_cluster.py` | CLIP 场景聚类 |
| 回忆发现 | `business/memory/memory_discovery.py` | on_this_day / recent / special_date（7节日，阈值1张）/ folder（按文件夹 top5） |
| 回忆推理 | `business/memory/memory_reasoning.py` | 碎裂反馈记录、负面提示管理 |
| 回忆生成 | `memory/memory_generator.py` | LLM 标题/描述生成（discovery 规则发现 + generator LLM 叙事） |

### 2.4 服务层

| 模块 | 文件 | 职责 |
|------|------|------|
| 流水线 | `services/background_task_manager.py` | Stage 模式流水线（扫描/分类/索引/回忆）、进度回调、取消机制 |

### 2.5 UI 层

| 模块 | 文件 | 职责 |
|------|------|------|
| 主窗口 | `ui/app.py` | MainWindow、侧边栏导航切换 |
| 推荐 | `ui/recommendation.py` | 照片排序、打散、新鲜度、分页、reshuffle |
| 瀑布流 | `ui/components/virtual_waterfall.py` | 虚拟滚动瀑布流、footer 提示、reset_for_shuffle |
| 图片查看器 | `ui/components/image_viewer.py` | 异步原图加载（PIL→临时文件→主线程 QPixmap） |
| 启动窗口 | `ui/components/startup_window.py` | 初始化进度、后台任务启动 |
| 设置窗口 | `ui/components/setup_window.py` | 首次/修改配置、关键词管理、多照片库路径 |
| 分类对话框 | `ui/components/folder_classifier_dialog.py` | 用户手动分类交互 |
| 回忆卡片 | `ui/components/memory_cards.py` | 回忆卡片展示 |
| 侧边栏 | `ui/components/sidebar.py` | 三等分竖排导航 |
| 时间线 | `ui/components/timeline_view.py` | 按日期分组照片 |
| 特殊回忆 | `ui/components/special_memories.py` | 卡片堆叠+碎裂动画（⚠️ 细节待完善） |
| 人物详情 | `ui/components/person_detail.py` | 人物回忆详情、命名、纠偏 |

## 3. 数据流

### 3.1 初始化

```
main.py → StartupWindow → 后台扫描/索引/精分类 → MainWindow → load_memories() → 瀑布流
```

### 3.2 分类

```
ClassifyStage: 关键词预分类 → LLM 分类剩余 → 后台 refine_sample_keywords（5级优先级）
```

### 3.3 随机回忆

```
load_category → rank_category_photos（去重/新鲜度/打散）→ 分页渲染 → 滚动加载 → 全部加载后洗牌续滚
```

### 3.4 识别（后台）

```
background_task_manager → tag_generator → clip_encoder → PhotoTagsRepo
```

规划与实现差异：sqlite-vec ❌（当前纯 Python 聚类）、批量推理 ⚠️ 可配置

### 3.5 回忆生成

```
memory_discovery: on_this_day / recent / special_date / folder → memories 表
memory_generator: LLM 叙事 → memories 表（memory_type=auto）
special_memories: 查询未 dismissed → 卡片堆叠展示
```

LLM 调用场景：文件夹分类（启动1次）、事件/旅行叙事（按需）。回忆标题模板化不调用 LLM。

### 3.6 增量扫描与 NAS 兼容

```
es.exe 查询 → _match_source_dir（盘符↔UNC↔IP 交叉匹配）→ _normalize_filepath → 对比差异 → 仅差异入库
```

关键兼容点：dotenv 吞反斜杠（source_dirs 自动修复）、es.exe GBK 解码、路径规范化为 source_dir 格式。

多照片库：SOURCE_DRIVE 分号分隔 → config.SOURCE_DIRS → files.source_dir 标记来源。

### 3.7 感知哈希去重

索引阶段计算 phash → 距离 < phash_threshold（默认8）判定重复 → is_duplicate_of 标记 → 推荐流程过滤。不物理删除。

### 3.8 缩略图版本复用

复用优先于重建（万张约 10-20 分钟）。三种场景：目录变更→copytree、DB 重建→ID 重映射、尺寸变更→惰性重建。详见 db_manager.py 迁移逻辑。

## 4. 数据库表结构

> db_manager.py 是 schema 的 source of truth，此处仅记设计意图和特殊约束。

### 核心表

| 表 | 主键 | 特殊字段/约束 | 索引 |
|----|------|--------------|------|
| files | id AUTO | file_path UNIQUE, source_dir（多库来源） | folder, hash, source_dir |
| folder_categories | folder_path PK | category NOT NULL | — |
| photo_metadata | file_id PK→files | phash, is_duplicate_of（重复标记） | date, phash, duplicate |
| memories | id AUTO | memory_type: on_this_day/person/event/scene/auto/special_date/folder; dismissed_at（碎裂时间）; payload JSON | category, starred, type, dismissed |
| click_history | id AUTO | file_id→files, category | folder, category |
| photo_tags | id AUTO | UNIQUE(file_id, tag, source); source: siglip/yolo/manual | file, source |
| photo_shown_history | id AUTO | file_id→files, category | file, shown_at |
| sample_keywords / life_keywords | id AUTO | keyword UNIQUE | — |

### v0.3 新增表

| 表 | 主键 | 特殊字段/约束 | 索引 |
|----|------|--------------|------|
| face_embeddings | id AUTO | embedding BLOB（512维 ArcFace）, cluster_id→face_clusters | file, cluster |
| face_clusters | cluster_id AUTO | person_name, user_corrected, representative_face | — |
| events | event_id AUTO | photo_ids JSON, event_type: event/trip, gps_cluster, location_name | — |
| memory_reasoning | id AUTO | memory_id→memories, feedback_type: dismissed/negative_hint | — |
| migration_log | id AUTO | version_from, version_to | — |
| task_checkpoints | (task_type, task_key) PK | status_json | — |

### 迁移（v0.2→v0.3）

自动检测版本 → 迁移前自动备份 → 结构变更+数据回填 → migration_log 防重复。

## 5. 关键常量与参数

| 常量 | 位置 | 值 | 说明 |
|------|------|-----|------|
| PAGE_SIZE | recommendation.py | 30 | 每页照片数 |
| MAX_SAME_FOLDER_STREAK | recommendation.py | 12 | 同文件夹最大连续数 |
| SMALL_FOLDER_THRESHOLD | recommendation.py | 100 | 小文件夹阈值 |
| FRESHNESS_WINDOW_DAYS | recommendation.py | 7 | 新鲜度窗口（天） |
| MAX_SAME_DAY_STREAK | recommendation.py | 12 | 同日最大出现数 |
| COL_COUNT | virtual_waterfall.py | 3 | 瀑布流列数 |
| thumbnail_size | config.py (Settings) | (400,400) | 缩略图尺寸（UI/AI 共用） |
| memory_high_freq_days | config.py (Settings) | 3 | 回忆高频生成天数 |
| phash_threshold | config.py (Settings) | 8 | 感知哈希去重阈值 |

## 6. 功能清单

| # | 功能 | 涉及模块 | 优先级 | 状态 |
|---|------|----------|--------|------|
| 1 | 侧边栏导航（随机回忆/时间线/特殊回忆） | UI层 | 高 | ✅ |
| 2 | imagehash 感知哈希去重 | indexer | 高 | ✅ |
| 3 | 那年今日回忆 | memory | 高 | ✅ |
| 4 | 时间线布局 | UI层 | 高 | ✅ |
| 5 | 特殊回忆卡片堆叠布局 | UI层 | 高 | ✅ |
| 6 | 人物回忆（DeepFace+聚类） | infra/business | 中 | ✅ |
| 7 | 事件/旅行回忆 | business | 中 | ✅ |
| 8 | CLIP场景聚类 | infra/business | 中 | ✅ |
| 9 | SigLIP语义标签 | infra | 高 | ✅ |
| 10 | 目标检测（LibreYOLO ONNX） | infra | 中 | ✅ |
| 11 | 碎裂回忆反馈机制 | memory | 中 | ✅ |
| 12 | 人物回忆纠偏 | UI/business | 中 | ✅ |
| 13 | 多照片库支持 | config/scanner | 中 | ✅ |
| 14 | 侧边栏三等分竖排导航 | UI层 | 高 | ✅ |
| 15 | 瀑布流去重+footer提示 | UI层 | 高 | ✅ |
| 16 | 特殊回忆三层兜底填充 | UI/business | 高 | ✅ |
| 17 | 大图异步加载 | UI层 | 高 | ✅ |
| 18 | 特殊回忆卡片碎裂动画 | UI层 | 中 | ⚠️ 框架已实现 |
| 19 | 缩略图版本复用 | db/indexer | 高 | 📋 v0.4 |
| 20 | custom-ui-pyqt6增强卡片 | UI层 | 延后 | ⏸️ |

## 7. 依赖与风险

| 依赖 | 用途 | 许可证 |
|------|------|--------|
| imagehash | 感知哈希去重 | BSD-2 |
| open-clip-torch | SigLIP/OpenCLIP 语义标签 | Apache-2.0 |
| deepface | 人脸检测与聚类（ArcFace 后端） | MIT |
| onnxruntime | LibreYOLO ONNX 目标检测 | MIT |
| sqlite-vec | 向量近似检索 | ❌ 暂未集成 |

模型文件：`models/yolov8n.onnx`（需手动下载）。`.gitignore` 已添加 `*.pt`。

## 8. 操作规则与架构审核

### 操作规则

1. 架构先行：先确认架构再写代码
2. 架构修改审核制：架构变更需提出审核方案，经明确确认后执行
3. 批量操作用脚本：涉及批量修改/合并文件时写 Python 脚本执行
4. 先清单后动手：修改前形成清单等待确认
5. 不确定就问，别猜
6. 没要求的不写，只改被要求的部分
7. 给验收标准，别给步骤
8. AI 识别全部使用缩略图
9. LLM 调用最小化
10. 数据库迁移必须可逆（迁移前自动备份）
11. 涉及用户照片的删除/移动操作，永远走标记而非物理操作
12. 禁止死代码入库
13. 层间调用走接口表（§11）
14. Config 统一走 get_settings()

### 架构变更审核范围

新增/删除模块、层间依赖变更、数据流变更、数据库表结构变更、外部依赖变更。

## 9. 错误日志与崩溃恢复

| 文件 | 级别 | 用途 |
|------|------|------|
| app.log | DEBUG+ | 全量，按天滚动 30 天 |
| error.log | WARNING+ | 仅警告和错误 |
| crash.log | 未捕获异常 | 完整 traceback |
| last_run.txt | N/A | 启动/退出标记，检测闪退 |

异常接管：sys.excepthook + threading.excepthook。启动闪退兜底：main.py 最早 try/except → crash.log + tkinter.messagebox。

## 10. 层间接口定义

各层对外只暴露以下接口，跨层调用必须且只能使用这些接口。

### 10.1 核心层（所有层可调用）

| 接口 | 模块 | 函数/类 |
|------|------|---------|
| 配置读取 | `config.py` | `get_settings() → Settings` |
| 配置写入 | `config.py` | `save_config(...)` |
| 配置检测 | `config.py` | `is_configured() → bool` |
| 数据库 | `db_manager.py` | `Database` 类 |
| 数据模型 | `core/models.py` | 所有 dataclass |
| 断点 | `checkpoint_manager.py` | `CheckpointManager` 类 |
| 日志 | `logger_setup.py` | `logger` |

禁止 import deprecated 全局变量（SOURCE_DRIVE/THUMBNAIL_DIR 等），统一 get_settings()。已知层反转：save_config() → LLMClient.reset()（Core→Infra），待改为事件/回调模式。

### 10.2 基础设施层（业务层/服务层可调用，UI 层禁止直接调用）

| 接口 | 模块 | 函数/类 |
|------|------|---------|
| LLM 客户端 | `infra/llm/client.py` | `get_llm_client() → LLMClient` |
| 缩略图加载 | `infra/image/thumbnail_loader.py` | `get_thumbnail_loader() → ThumbnailLoader` |
| CLIP 编码 | `infra/image/clip_encoder.py` | `encode_images(file_ids) → list[ndarray]` |
| 人脸检测 | `infra/image/face_detector.py` | `extract_embeddings_batch(file_ids) → list` |
| 目标检测 | `infra/image/object_detector.py` | `detect_objects(file_id) → list[dict]` |
| Files 仓库 | `infra/db/repositories/files_repo.py` | `FilesRepository` |
| Metadata 仓库 | `infra/db/repositories/photo_metadata_repo.py` | `PhotoMetadataRepository` |
| Memories 仓库 | `infra/db/repositories/memories_repo.py` | `MemoriesRepository` |
| Tags 仓库 | `infra/db/repositories/photo_tags_repo.py` | `PhotoTagsRepository` |
| FaceEmbeddings 仓库 | `infra/db/repositories/face_embeddings_repo.py` | `FaceEmbeddingsRepository` |
| Events 仓库 | `infra/db/repositories/events_repo.py` | `EventsRepository` |
| ClickHistory 仓库 | `infra/db/repositories/click_history_repo.py` | `ClickHistoryRepository` |

### 10.3 业务层（服务层/UI 层可调用）

| 接口 | 模块 | 函数 |
|------|------|------|
| 全量扫描 | `fast_scan.py` | `full_scan(progress_callback, batch_limit) → dict` |
| 扫描控制 | `fast_scan.py` | `clear_checkpoint() / set_paused() / set_stopped()` |
| 文件夹分类 | `folder_classifier.py` | `classify_folders() → dict` |
| 精分类 | `folder_classifier.py` | `refine_sample_keywords() → dict` |
| 照片索引 | `photo_indexer.py` | `index_photos(progress_callback, batch_limit) → dict` |
| 索引控制 | `photo_indexer.py` | `clear_checkpoint() / set_paused() / set_stopped()` |
| 去重 | `photo_indexer.py` | `dedup_by_phash(progress_callback) → dict` |
| 标签生成 | `tag_generator.py` | `generate_tags_for_image(file_id) → list[str]` |
| 人脸聚类 | `face_cluster.py` | `cluster_faces(embeddings) → dict` |
| 场景聚类 | `scene_cluster.py` | `cluster_by_scene(file_ids) → list` |
| 那年今日 | `memory_discovery.py` | `discover_on_this_day(category) → list` |
| 近期回忆 | `memory_discovery.py` | `discover_recent_memories(category) → list` |
| 特殊日期回忆 | `memory_discovery.py` | `discover_special_date_memories() → list` |
| 文件夹回忆 | `memory_discovery.py` | `discover_folder_memories(top_n) → list` |
| 回忆查询 | `memory_discovery.py` | `get_on_this_day_memories(category) → list` |
| 回忆推理 | `memory_reasoning.py` | `record_dismissal(memory_id, reasoning) / get_negative_hints()` |
| LLM 回忆 | `memory_generator.py` | `generate_all_memories() → list` |

### 10.4 服务层（UI 层可调用）

| 接口 | 模块 | 函数/类 |
|------|------|---------|
| 后台流水线 | `background_task_manager.py` | `BackgroundTaskManager` 类 |
| 流水线阶段 | `background_task_manager.py` | `Pipeline`, `ScanStage`, `ClassifyStage`, `IndexStage` |

### 10.5 接口变更规则

新增：登记后即可使用。删除：确认无调用方后移除+架构审核。修改签名：架构审核。

## 11. 技术债（P2 延后至 v0.4）

| # | 问题 | 修复方向 |
|---|------|---------|
| 1 | config.py Core→Infra 层反转（save_config→LLMClient.reset） | 事件/回调模式 |
| 2 | UI 层直接实例化 Database/Repository（7处） | 通过业务层间接访问 |
| 3 | 业务层 raw SQL 105 处 | 逐步迁移至 Repository，新代码必须用 Repository |
| 4 | app.py 职责过多（739行，4个内联 QThread） | 拆分 QThread 到独立模块 |
| 5 | db_manager._ensure_missing_tables 只检查3个旧表 | 扩展检查范围 |
| 6 | 缩略图版本复用未实现（§3.8 已设计） | DB 迁移阶段自动执行 |
| 7 | config.py 模块级副作用（import 时创建目录） | 延迟到首次使用时 |
| 8 | deprecated 变量残留：SOURCE_DRIVE/SOURCE_DIRS/DATA_DIR/THUMBNAIL_DIR/CLASSIFICATION_HISTORY_FILE | 迁移至 Settings 字段 |
