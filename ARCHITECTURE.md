# NAS 照片回忆 - v0.3 架构

## 1. 分层架构

```
┌──────────────────────────────────────────────────┐
│                    UI 层 (ui/)                     │
│  app.py / components/ / recommendation            │
│  sidebar / timeline / special_memories            │
├──────────────────────────────────────────────────┤
│                  服务层 (services/)                │
│  background_task_manager                          │
├──────────────────────────────────────────────────┤
│                     业务层                         │
│  business/image_recognition / business/memory     │
│  business/scanner / business/classifier            │
│  business/indexer / memory (generator)            │
├──────────────────────────────────────────────────┤
│                基础设施层 (infra/)                  │
│  llm / db/repositories / image                    │
├──────────────────────────────────────────────────┤
│                  核心层 (core/)                    │
│  models / config / db_manager / logger            │
└──────────────────────────────────────────────────┘
```

### 层间依赖规则

- **严格单向依赖**：上层可调用下层，下层禁止调用上层
- 同层模块间通过公开函数交互，不直接操作对方内部状态
- 跨层调用必须通过层间接口表（见第 11 节），禁止直接 import 层内未导出模块
- UI 层禁止直接写 SQL，必须通过 Repository 或 db_manager 获取数据
- 业务层禁止直接操作 UI 组件
- AI 识别任务使用缩略图，不读取原图
- 涉及用户照片的删除/移动操作，永远走"标记"而非物理操作

## 2. 模块职责

### 2.1 核心层

| 模块 | 文件 | 职责 | 状态 |
|------|------|------|------|
| 配置 | `config.py` | 环境变量读取、Settings 单例、全局常量（分类ID/扩展名/模型名）、多照片库路径支持（分号分隔，通过 `source_dirs` 解析） | ✅ 活跃 |
| 数据库 | `db_manager.py` | SQLite 连接管理、表结构定义与初始化、版本自动迁移 | ✅ 活跃 |
| 数据模型 | `core/models.py` | 数据类定义（File、PhotoMetadata、Memory、FaceEmbedding、FaceCluster、Event、MemoryReasoning、TaskCheckpoint 等） | ✅ 活跃 |
| 日志 | `logger_setup.py` | 全局 logger 配置、多文件分级（app.log 全量 / error.log WARNING+ / crash.log 未捕获异常）、sys.excepthook + threading.excepthook 接管、启动崩溃 marker（last_run.txt）、按天滚动 | ✅ 活跃 |
| 断点 | `checkpoint_manager.py` | 通用长任务断点持久化（扫描/索引/识别统一使用 `task_checkpoints` 表） | ✅ 活跃 |

### 2.2 基础设施层

| 模块 | 文件 | 职责 | 状态 |
|------|------|------|------|
| LLM | `infra/llm/client.py` | OpenAI 兼容客户端封装、重试策略 | ✅ 活跃 |
| 数据仓库 | `infra/db/repositories/` | 各表 CRUD 操作封装（FilesRepo、PhotoMetadataRepo、MemoriesRepo、PhotoTagsRepo、FaceEmbeddingsRepo、EventsRepo、ClickHistoryRepo） | ✅ 活跃 |
| CLIP编码器 | `infra/image/clip_encoder.py` | SigLIP/OpenCLIP 图像嵌入提取（后台，使用缩略图） | ✅ 活跃 |
| 人脸检测 | `infra/image/face_detector.py` | DeepFace 人脸检测与特征提取（使用缩略图，固定 ArcFace 后端） | ✅ 活跃 |
| 目标检测 | `infra/image/object_detector.py` | 目标检测抽象接口 + LibreYOLO ONNX 实现（基于 onnxruntime，MIT 许可） | ✅ 活跃 |
| 缩略图加载 | `infra/image/thumbnail_loader.py` | 识别模块共享的缩略图加载器，统一 LRU 内存管理（256张） | ✅ 活跃 |

### 2.3 业务层

| 模块 | 文件 | 职责 | 状态 |
|------|------|------|------|
| 扫描 | `business/scanner/fast_scan.py` | 磁盘文件发现（Everything/os.walk）、入库 files 表、多照片库路径遍历、`source_dir` 字段标记 | ✅ 活跃 |
| 分类 | `business/classifier/folder_classifier.py` | 关键词预分类 + LLM 分类 + 后台精分类、自动清理旧分类残留 | ✅ 活跃 |
| 索引 | `business/indexer/photo_indexer.py` | EXIF 提取、缩略图生成、感知哈希去重（`dedup_by_phash`）、入库 photo_metadata 表 | ✅ 活跃 |
| 图像标签 | `business/image_recognition/tag_generator.py` | 基于 SigLIP 嵌入的图像标签生成策略 | ✅ 活跃 |
| 人脸聚类 | `business/image_recognition/face_cluster.py` | 人脸向量聚类、人物分组管理、用户纠偏（标记为他人）、rename_cluster、reassign_face | ✅ 活跃 |
| 场景聚类 | `business/image_recognition/scene_cluster.py` | CLIP 场景聚类（距离判定） | ✅ 活跃 |
| 回忆发现 | `business/memory/memory_discovery.py` | 那年今日回忆、近期回忆、数据查询与过滤 | ✅ 活跃 |
| 事件检测 | `business/memory/event_detector.py` | 时间断裂聚类 + GPS 聚类、事件/旅行发现 | ⚠️ 代码存在，未被 UI 调用 |
| 回忆叙事 | `business/memory/memory_narrator.py` | LLM 叙事生成 | ⚠️ 代码存在，未被 UI 调用 |
| 回忆推理 | `business/memory/memory_reasoning.py` | 碎裂回忆反馈记录、负面提示管理 | ✅ 活跃 |
| 回忆生成 | `memory/memory_generator.py` | LLM 回忆标题/描述生成（v0.2 保留模块，与 memory_discovery 并存：discovery 负责规则发现入口，generator 负责 LLM 叙事能力） | ✅ 活跃 |

### 2.4 服务层

| 模块 | 文件 | 职责 | 状态 |
|------|------|------|------|
| 流水线 | `services/background_task_manager.py` | Stage 模式流水线（扫描/分类/索引/回忆）、进度回调、取消机制、交互式分类、批量限制；后台线程统一注册与安全等待退出 | ✅ 活跃 |
| 识别调度 | `services/recognition_scheduler.py` | 识别任务调度（SigLIP/人脸/YOLO/场景四阶段，断点续传） | ⚠️ 代码存在，功能已部分并入 background_task_manager，待整合或移除 |
| 数据服务 | `services/data_service.py` | 数据访问门面（封装 Repository 调用） | ❌ 死代码，0引用，待清理 |

### 2.5 UI 层

| 模块 | 文件 | 职责 | 状态 |
|------|------|------|------|
| 主窗口 | `ui/app.py` | MainWindow、侧边栏导航切换（随机回忆/时间线/特殊回忆） | ✅ 活跃 |
| 推荐 | `ui/recommendation.py` | 照片排序、打散、新鲜度、分页、去重过滤（`is_duplicate_of`） | ✅ 活跃 |
| 瀑布流 | `ui/components/virtual_waterfall.py` | 虚拟滚动瀑布流布局、卡片渲染 | ✅ 活跃 |
| 图片查看器 | `ui/components/image_viewer.py` | 全屏查看、收藏、分类调整 | ✅ 活跃 |
| 启动窗口 | `ui/components/startup_window.py` | 初始化进度、后台任务启动 | ✅ 活跃 |
| 设置窗口 | `ui/components/setup_window.py` | 首次配置/修改配置、关键词管理、多照片库路径管理 | ✅ 活跃 |
| 分类对话框 | `ui/components/folder_classifier_dialog.py` | 用户手动分类交互 | ✅ 活跃 |
| 回忆卡片 | `ui/components/memory_cards.py` | 回忆卡片展示（v0.3 重写） | ✅ 活跃 |
| 侧边栏导航 | `ui/components/sidebar.py` | 3个导航项切换 | ✅ 活跃 |
| 时间线视图 | `ui/components/timeline_view.py` | 按日期分组的照片时间线布局 | ✅ 活跃 |
| 特殊回忆视图 | `ui/components/special_memories.py` | 回忆卡片堆叠布局、碎裂动画框架（QPropertyAnimation） | ⚠️ 框架已实现，细节待完善 |
| 人物详情页 | `ui/components/person_detail.py` | 人物回忆详情页、命名、纠偏入口 | ✅ 活跃 |

## 3. 数据流

### 3.1 初始化流程

```
main.py → StartupWindow
  → 启动后台任务：
    - BgScanWorker：后台扫描（可断点）
    - BgIndexWorker：后台索引（可断点）
    - BgRefineWorker：后台关键词精分类
  → 过渡到 MainWindow
  → MainWindow.load_memories()
  → 按分类加载照片，展示瀑布流
```

### 3.2 分类流程

```
启动阶段 ClassifyStage：
  classify_folders()
    → 样片关键词预分类
    → 生活关键词预分类
    → LLM 分类剩余分支（采样子路径+文件名作为上下文）
    → 不确定分支暂归生活（confidence=default-pending-refine）

主页面启动后后台：
  refine_sample_keywords()
    → 批量查询，按5级优先级重新判定
    → 分支分类(5) > 内容信号(4) > EXIF(3) > 文件名(2) > 路径(1)
    → 冲突时样片优先
    → 分类变化后自动清理旧分类下的 memories/photo_shown_history/click_history 残留
```

### 3.3 照片推荐流程（随机回忆）

```
MainWindow.load_category(cat_id)
  → rank_category_photos(db, cat_id)
    → 查询分类下照片
    → 合并去重（排除 is_duplicate_of 非空的记录）
    → 新鲜度排序
    → 文件夹维度/时间维度打散
    → 分页渲染
  → record_shown_photos()
```

### 3.4 无限滚动流程

```
VirtualCategoryPage → load_more_requested
  → MainWindow._on_load_more(cat_id)
    → 从已排序列表取后续批次
    → append_photos() 追加
```

### 3.5 识别数据流（后台）

#### 当前实现状态

```
background_task_manager.py（Stage 模式流水线）
  → tag_generator.py
    → clip_encoder.py（SigLIP 推理）
    → PhotoTagsRepo 写入（source=siglip）
```

#### 规划与实现差异

| 规划项 | 实现状态 | 说明 |
|--------|----------|------|
| 完整串行流水线 | ✅ 已实现 | Stage 模式，整合到 background_task_manager.py |
| sqlite-vec | ❌ 未实现 | 当前使用纯 Python 向量化欧几里得/余弦距离聚类（`_clustering.py`） |
| 批量推理每批 50 张 | ⚠️ 可配置 | 基础框架支持，细节待完善 |
| 缩略图统一加载 | ✅ 已实现 | thumbnail_loader.py LRU 缓存 |
| 人脸聚类 | ✅ 已实现 | face_cluster.py → _clustering.py 向量化贪心聚类 |
| 场景聚类 | ✅ 已实现 | scene_cluster.py → _clustering.py 向量化贪心聚类 |
| 回忆发现（5类） | ✅ 已实现 | on_this_day / recent / person / event / scene |

### 3.6 识别调度模型

#### 实现细节

- 使用 `task_checkpoints` 表，`task_type` 为 `'recognition'`
- 断点存储方式：单条记录存储当前进度（与规划的每条文件一条记录不同）

### 3.7 回忆生成数据流

```
memory_discovery.py
  → 那年今日：按月日匹配历史照片 (discover_on_this_day) ✅
  → 近期回忆：近 N 天照片 (discover_recent_memories) ✅
  → 人物回忆：基于 face_clusters 聚类 (discover_person_memories) ✅
  → 事件回忆：基于 events 表 (discover_event_memories) ✅
  → 场景回忆：基于场景聚类输出 (discover_scene_memories) ✅
  → 写入 memories 表（memory_type、payload、dismissed_at 管理）

memory_generator.py
  → LLM 叙事生成：聚焦采样 + DeepSeek 生成标题/描述 ✅
  → 写入 memories 表（memory_type=auto）

special_memories.py
  → 查询未 dismissed_at 的回忆
  → 卡片堆叠展示
```

### 3.8 LLM 调用场景

| 场景 | 调用频率 | 状态 |
|------|----------|------|
| 文件夹分类 | 启动时 1 次 | ✅ 已实现 |
| 事件/旅行叙事 | 按需 | ✅ 已实现 |
| 回忆标题 | 无 | 模板化，不调用 |

### 3.9 照片库缓存与迁移

#### 增量扫描（Everything 对比，复用 files 表）

```
启动时每个 source_dir 分别执行：
  → es.exe 查询该目录下媒体文件
  → 查询 files WHERE source_dir = ? 已有记录
  → 对比差异：新增/变更/移除
  → 仅差异入库，标记移除的记录
  → 清理不在配置中的旧 source_dir 记录
```

#### 多照片库支持

- 配置方式：`SOURCE_DRIVE` 分号分隔多路径
- 内部表示：`config.SOURCE_DIRS` 列表
- 数据库：`files.source_dir` 标记来源
- 全局合并：人脸/事件聚类跨库合并，不分组

#### 数据库版本迁移（v0.2→v0.3）

- 自动检测版本，启动时执行
- 迁移前自动备份
- 结构变更 + 数据回填
- 记录到 `migration_log` 表，防止重复执行

### 3.10 感知哈希去重流程

#### 去重策略

- 索引阶段计算 phash
- `photo_metadata.phash` 存储
- 距离 < `PHASH_THRESHOLD`（默认 8）判定重复
- `photo_metadata.is_duplicate_of` 标记原图 file_id
- 推荐流程过滤 is_duplicate_of 非空的照片
- 不物理删除，不拒绝入库

### 3.11 缩略图版本复用策略

版本更迭或配置变更时，已有缩略图数据应尽量复用，避免全量重新生成。

#### 复用原则

- 缩略图文件命名：`{file_id}.jpg`，存储于 `{PHOTO_DATA_DIR}/thumbnails/`
- 缩略图生成开销大（万张照片约 10-20 分钟），复用优先于重建
- AI 侧接受重采样（400→224/112），不因尺寸微调强制全量重建

#### 迁移场景与策略

| 场景 | 触发条件 | 策略 |
|------|----------|------|
| A. 缓存目录变更 | 用户修改 `PHOTO_DATA_DIR` | `shutil.copytree` 整体搬迁旧 thumbnails 目录到新路径 |
| B. DB 重建导致 file_id 变化 | 删库重建、版本迁移 | 读取旧 DB 建立 `file_path → old_file_id` 映射，查新 DB 得 `file_path → new_file_id`，批量 `os.rename({old_id}.jpg, {new_id}.jpg)` |
| C. 缩略图尺寸变更 | `THUMBNAIL_SIZE` 调整 | 惰性重建：不强制全量重新生成，索引阶段 `generate_thumbnail()` 按需补缺 |

#### 实施步骤（DB 迁移阶段自动执行）

1. **检测旧目录**：迁移前记录旧 `thumbnail_dir` 路径
2. **路径搬迁**：若 `PHOTO_DATA_DIR` 变更，`copytree` 旧目录 → 新目录
3. **ID 重映射**：若 DB 重建，基于 `file_path` 双库映射，批量 rename 缩略图文件
4. **路径更新**：`photo_metadata.thumbnail_path` 字段更新为新路径
5. **惰性清理**：无映射的旧缩略图保留不删（避免误删），索引阶段按需补缺
6. **日志记录**：`"缩略图复用: 迁移 N 个, 跳过 M 个 (无映射)"`

#### 缩略图完整性校验

- `generate_thumbnail()` 跳过条件扩展：不仅检查文件存在，还需 `os.path.getsize() > 0`
- 损坏/零字节缩略图视为缺失，索引阶段自动重新生成

## 4. 数据库表结构

### 4.1 现有表（v0.3）

#### files
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| file_path | TEXT | UNIQUE NOT NULL | |
| file_name | TEXT | NOT NULL | |
| folder_path | TEXT | NOT NULL | |
| folder_name | TEXT | NOT NULL | |
| file_size | INTEGER | | |
| file_mtime | TEXT | | |
| file_hash | TEXT | | |
| is_image | INTEGER | DEFAULT 1 | |
| scanned_at | TEXT | | |
| source_dir | TEXT | | 多库来源路径 |
索引：`idx_files_folder`、`idx_files_hash`、`idx_files_source_dir`

#### folder_categories
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| folder_path | TEXT | PK | |
| category | INTEGER | NOT NULL | |
| confidence | TEXT | | |
| classified_at | TEXT | | |

#### photo_metadata
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| file_id | INTEGER | PK → files | |
| date_taken | TEXT | | |
| camera_model | TEXT | | |
| gps_lat | REAL | | |
| gps_lon | REAL | | |
| width | INTEGER | | |
| height | INTEGER | | |
| thumbnail_path | TEXT | | |
| exif_json | TEXT | | |
| indexed_at | TEXT | | |
| is_starred | INTEGER | DEFAULT 0 | |
| phash | TEXT | | 感知哈希 |
| is_duplicate_of | INTEGER | | 重复标记，指向原图 file_id |
索引：`idx_meta_date`、`idx_meta_phash`、`idx_meta_duplicate`

#### memories
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| category | INTEGER | NOT NULL | |
| memory_type | TEXT | NOT NULL | on_this_day / person / event / scene / auto |
| title | TEXT | NOT NULL | |
| description | TEXT | | |
| photo_ids | TEXT | NOT NULL | JSON 数组 |
| cover_file_id | INTEGER | | |
| created_at | TEXT | | |
| is_starred | INTEGER | DEFAULT 0 | |
| last_shown_at | TEXT | | 最后展示时间 |
| click_count | INTEGER | DEFAULT 0 | 点击次数 |
| dismissed_at | TEXT | | 碎裂时间，NULL=未碎裂 |
| payload | TEXT | | JSON 扩展数据 |
索引：`idx_memories_category`、`idx_memories_starred`、`idx_memories_type`、`idx_memories_dismissed`

#### click_history
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| file_id | INTEGER | NOT NULL → files | |
| folder_path | TEXT | NOT NULL | |
| category | INTEGER | | |
| clicked_at | TEXT | DEFAULT now | |
索引：`idx_click_folder`、`idx_click_category`

#### photo_tags
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| file_id | INTEGER | NOT NULL → files | |
| tag | TEXT | NOT NULL | |
| source | TEXT | NOT NULL | siglip / yolo / manual |
| created_at | TEXT | DEFAULT now | |
| UNIQUE(file_id, tag, source) | | |
索引：`idx_tags_file`、`idx_tags_source`

#### photo_shown_history
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| file_id | INTEGER | NOT NULL → files | |
| category | INTEGER | | |
| shown_at | TEXT | DEFAULT now | |
索引：`idx_shown_file`、`idx_shown_at`

#### sample_keywords / life_keywords
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| keyword | TEXT | UNIQUE NOT NULL | |
| created_at | TEXT | DEFAULT now | |

### 4.2 新增表（v0.3）

#### face_embeddings
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| file_id | INTEGER | NOT NULL → files | |
| embedding | BLOB | NOT NULL | 512维 ArcFace 向量 |
| cluster_id | INTEGER | | → face_clusters |
索引：`idx_fe_file`、`idx_fe_cluster`

#### face_clusters
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| cluster_id | INTEGER | PK AUTO | |
| person_name | TEXT | DEFAULT '' | |
| user_corrected | INTEGER | DEFAULT 0 | |
| representative_face | INTEGER | | → face_embeddings |
| created_at | TEXT | | |

#### events
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| event_id | INTEGER | PK AUTO | |
| start_date | TEXT | NOT NULL | |
| end_date | TEXT | NOT NULL | |
| gps_cluster | TEXT | | GPS 分组标识 |
| location_name | TEXT | | 反向地理编码位置 |
| photo_ids | TEXT | NOT NULL | JSON 数组 |
| event_type | TEXT | DEFAULT 'event' | event / trip |

#### memory_reasoning
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| memory_id | INTEGER | NOT NULL → memories | |
| reasoning | TEXT | | 碎裂原因/用户反馈 |
| feedback_type | TEXT | | dismissed / negative_hint |
| created_at | TEXT | DEFAULT now | |

#### migration_log
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTO | |
| version_from | TEXT | NOT NULL | 'init' 或 '0.2' |
| version_to | TEXT | NOT NULL | '0.3' |
| migrated_at | TEXT | DEFAULT now | |

#### task_checkpoints
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| task_type | TEXT | NOT NULL | scan / index / recognition |
| task_key | TEXT | NOT NULL | default 或 file_id 范围 |
| status_json | TEXT | | 进度状态 JSON |
| updated_at | TEXT | | |
| PRIMARY KEY(task_type, task_key) | | |

### 4.3 索引规划汇总
| 表 | 索引名 | 字段 | 状态 |
|----|--------|------|------|
| files | idx_files_source_dir | source_dir | ✅ |
| photo_metadata | idx_meta_phash | phash | ✅ |
| photo_metadata | idx_meta_duplicate | is_duplicate_of | ✅ |
| photo_tags | idx_tags_source | source | ✅ |
| face_embeddings | idx_fe_cluster | cluster_id | ✅ |
| memories | idx_memories_type | memory_type | ✅ |
| memories | idx_memories_dismissed | dismissed_at | ✅ |

### 4.4 v0.2→v0.3 迁移
- 自动检测 schema 版本
- 迁移前自动备份
- 结构变更 + 数据回填
- 记录到 migration_log，防止重复

## 5. 关键常量与参数

| 常量 | 位置 | 值 | 说明 |
|------|------|-----|------|
| PAGE_SIZE | recommendation.py | 30 | 每页照片数 |
| MAX_SAME_FOLDER_STREAK | recommendation.py | 12 | 同文件夹最大连续数 |
| SMALL_FOLDER_THRESHOLD | recommendation.py | 100 | 小文件夹阈值 |
| FRESHNESS_WINDOW_DAYS | recommendation.py | 7 | 新鲜度窗口（天） |
| MAX_SAME_DAY_STREAK | recommendation.py | 12 | 同日最大出现数 |
| COL_COUNT | virtual_waterfall.py | 3 | 瀑布流列数 |
| THUMBNAIL_SIZE | config.py | (400,400) | 缩略图尺寸（UI/AI 共用） |
| MEMORY_HIGH_FREQ_DAYS | config.py | 3 | 回忆高频生成天数 |
| PHASH_THRESHOLD | config.py | 8 | 感知哈希去重阈值 |

## 6. 功能清单与实现状态

| # | 功能 | 涉及模块 | 优先级 | 状态 |
|---|------|----------|--------|------|
| 1 | 侧边栏导航（随机回忆/时间线/特殊回忆） | UI层 | 高 | ✅ 已实现 |
| 2 | imagehash 感知哈希去重 | indexer、config、db_manager | 高 | ✅ 已实现 |
| 3 | 那年今日回忆 | memory、db_manager | 高 | ✅ 已实现 |
| 4 | 时间线布局 | UI层 | 高 | ✅ 已实现 |
| 5 | 特殊回忆卡片堆叠布局 | UI层 | 高 | ✅ 已实现 |
| 6 | 人物回忆（DeepFace人脸聚类+聚合卡片） | infra/image、business | 中 | ✅ 已实现 |
| 7 | 事件/旅行回忆（时间断裂+GPS聚类） | business | 中 | ✅ 已实现 |
| 8 | CLIP场景聚类卡片堆叠 | infra/image、business | 中 | ✅ 已实现 |
| 9 | SigLIP语义标签（后台） | infra/image、pipeline | 高 | ✅ 已实现 |
| 10 | 目标检测（LibreYOLO ONNX） | infra/image | 中 | ✅ 已实现 |
| 11 | custom-ui-pyqt6增强卡片效果 | UI层 | 延后 | ⏸️ 延后（原生PyQt6） |
| 12 | 特殊回忆卡片碎裂动画 | UI层 | 中 | ⚠️ 框架已实现（细节待完善） |
| 13 | 碎裂回忆反馈机制 | memory、LLM | 中 | ✅ 已实现 |
| 14 | 人物回忆纠偏 | UI层、business | 中 | ✅ 已实现 |
| 15 | 多照片库支持 | config、scanner、everything、setup_window | 中 | ✅ 已实现 |
| 16 | 缩略图版本复用 | db_manager、photo_indexer | 高 | 📋 待实现 |

## 7. 依赖与风险

### 外部依赖

| 依赖 | 用途 | 许可证 | 状态 |
|------|------|--------|------|
| imagehash | 感知哈希去重 | BSD-2 | ✅ requirements.txt |
| open-clip-torch | SigLIP/OpenCLIP 语义标签 | Apache-2.0 | ⚠️ 代码已实现，待添加到 requirements.txt |
| deepface | 人脸检测与聚类 | MIT | ⚠️ 代码已实现，待添加到 requirements.txt |
| onnxruntime | LibreYOLO ONNX 目标检测 | MIT | ✅ requirements.txt（替代 ultralytics，消除 AGPL 风险） |
| sqlite-vec | 向量近似检索 | MIT | ❌ 暂未集成（当前纯Python） |
| custom-ui-pyqt6 | 增强卡片视觉效果 | 未确认 | ⏸️ 延后 |

### object_detector 抽象接口
```python
class ObjectDetector(Protocol):
    def detect(self, image_path: str) -> list[dict]: ...

class LibreYOLOONNXDetector:  # 当前实现，基于 onnxruntime
    ...
```

模型文件路径：`models/yolov8n.onnx`（需手动下载 YOLOv8n ONNX 权重）

### deepface 后端锁定
固定使用 ArcFace 后端，512维向量输出。

## 8. 操作规则

1. **架构先行**：先确认架构再写代码
2. **架构修改审核制**：架构变更需提出审核方案，经明确确认后执行
3. **批量操作用脚本**：涉及批量修改/合并文件时写 Python 脚本执行
4. **先清单后动手**：修改前形成清单等待确认
5. **不确定就问，别猜**
6. **没要求的不写**
7. **只改被要求的部分**
8. **给验收标准，别给步骤**
9. **AI识别全部使用缩略图**
10. **LLM调用最小化**
11. **数据库迁移必须可逆**：迁移前自动备份
12. **涉及用户照片的删除/移动操作，永远走标记而非物理操作**
13. **禁止死代码入库**：新增函数/变量必须有调用方，否则不入
14. **层间调用走接口表**：跨层 import 必须符合第 11 节的层间接口定义
15. **Config 统一走 get_settings()**：禁止新增 deprecated 全局变量引用

## 9. 架构变更审核规则

以下变更属于架构变更，需提出审核方案、经明确确认后方可执行：
1. **新增/删除模块**：新增 Python 包或删除现有模块
2. **层间依赖变更**：违反分层规则的新调用，或修改层间接口表
3. **数据流变更**：改变模块间数据传递方式
4. **数据库表结构变更**：新增/删除/修改表或索引
5. **外部依赖变更**：新增/移除/替换外部依赖库

## 10. 错误日志与崩溃恢复策略

### 日志文件划分

| 文件 | 路径 | 级别 | 用途 |
|------|------|------|------|
| app.log | storage/logs/app.log | DEBUG+ | 全量日志，按天滚动，保留 30 天 |
| error.log | storage/logs/error.log | WARNING+ | 仅警告和错误，按天滚动，保留 30 天 |
| crash.log | storage/logs/crash.log | 未捕获异常 | 完整 traceback + sys.argv + 关键环境变量 |
| last_run.txt | storage/logs/last_run.txt | N/A | 启动/退出标记，检测闪退 |

### 异常接管机制

1. `sys.excepthook`：接管主线程未捕获异常 → 写入 crash.log
2. `threading.excepthook`：接管后台线程未捕获异常 → 写入 crash.log
3. Qt 异常：PyQt 槽函数中的 Python 异常通过 sys.excepthook 捕获

### 启动崩溃检测

- 进程启动时写 `last_run.txt: started @ <time>`
- 正常退出时改为 `ok @ <time>`
- 下次启动检测到 `started` 未改为 `ok` → logger.warning 提示可能闪退

### 启动闪退兜底

- main.py 入口最早期 try/except 包住所有逻辑
- 崩溃时写入 crash.log 后用 tkinter.messagebox 告知用户
- launch.bat 末尾保留 `pause`，让用户能看到控制台输出

### 阶段化日志

每个主要阶段加 `logger.info("=== Stage: XXX start ===")` 分隔标记，闪退时一眼定位死在哪。

### 缩略图尺寸说明

AI 侧接受重采样开销（400→224/112），不生成第二套缩略图。实测 10000 张额外耗时约 10-20 秒，可接受。

## 11. 层间接口定义

各层对外只暴露以下接口，跨层调用必须且只能使用这些接口。未列入的模块/函数属于层内实现细节，禁止跨层直接引用。

### 11.1 核心层对外接口

所有层均可调用。

| 接口 | 模块 | 函数/类 | 说明 |
|------|------|----------|------|
| 配置读取 | `config.py` | `get_settings() → Settings` | 获取配置单例，所有配置项通过此接口读取 |
| 配置写入 | `config.py` | `save_config(...)` | 保存用户配置到 .env |
| 配置检测 | `config.py` | `is_configured() → bool` | 检查是否已完成初始配置 |
| 数据库 | `db_manager.py` | `Database` 类 | 连接管理、表初始化、版本迁移 |
| 数据模型 | `core/models.py` | 所有 dataclass | File, PhotoMetadata, Memory, FaceEmbedding, FaceCluster, Event, MemoryReasoning, PhotoTag, TaskCheckpoint |
| 断点 | `checkpoint_manager.py` | `CheckpointManager` 类 | 长任务断点持久化 |
| 日志 | `logger_setup.py` | `logger` | 全局 logger 实例 |

**禁止**：其他层禁止 import `config.py` 中的 deprecated 全局变量（`SOURCE_DRIVE`、`THUMBNAIL_DIR` 等），统一使用 `get_settings().xxx`。现有 deprecated 变量按第 12 节计划逐步清理。

**已知层反转**：`config.py` 的 `save_config()` 和 `reload_config()` 内部引用了 `infra.llm.client.LLMClient.reset()`。这是 Core → Infra 的违规，待后续重构时将 reset 逻辑改为事件/回调模式消除。

### 11.2 基础设施层对外接口

业务层和服务层可调用。UI 层禁止直接调用（必须通过业务层或服务层间接使用）。

| 接口 | 模块 | 函数/类 | 说明 |
|------|------|----------|------|
| LLM 客户端 | `infra/llm/client.py` | `get_llm_client() → LLMClient` | OpenAI 兼容客户端，自动重试 |
| 缩略图加载 | `infra/image/thumbnail_loader.py` | `get_thumbnail_loader() → ThumbnailLoader` | 缩略图 LRU 缓存加载 |
| CLIP 编码 | `infra/image/clip_encoder.py` | `encode_images(file_ids) → list[ndarray]` | SigLIP 图像嵌入提取 |
| 人脸检测 | `infra/image/face_detector.py` | `extract_embeddings_batch(file_ids) → list` | DeepFace 人脸特征提取 |
| 目标检测 | `infra/image/object_detector.py` | `detect_objects(file_id) → list[dict]` | LibreYOLO ONNX 目标检测 |
| Files 仓库 | `infra/db/repositories/files_repo.py` | `FilesRepository` | files 表 CRUD |
| Metadata 仓库 | `infra/db/repositories/photo_metadata_repo.py` | `PhotoMetadataRepository` | photo_metadata 表 CRUD |
| Memories 仓库 | `infra/db/repositories/memories_repo.py` | `MemoriesRepository` | memories 表 CRUD |
| Tags 仓库 | `infra/db/repositories/photo_tags_repo.py` | `PhotoTagsRepository` | photo_tags 表 CRUD |
| FaceEmbeddings 仓库 | `infra/db/repositories/face_embeddings_repo.py` | `FaceEmbeddingsRepository` | face_embeddings 表 CRUD |
| Events 仓库 | `infra/db/repositories/events_repo.py` | `EventsRepository` | events 表 CRUD |
| ClickHistory 仓库 | `infra/db/repositories/click_history_repo.py` | `ClickHistoryRepository` | click_history 表 CRUD |

### 11.3 业务层对外接口

服务层和 UI 层可调用。

| 接口 | 模块 | 函数 | 说明 |
|------|------|------|------|
| 全量扫描 | `business/scanner/fast_scan.py` | `full_scan(progress_callback, batch_limit) → dict` | 磁盘文件发现与入库 |
| 扫描控制 | `business/scanner/fast_scan.py` | `clear_checkpoint() / set_paused() / set_stopped()` | 断点管理 |
| 文件夹分类 | `business/classifier/folder_classifier.py` | `classify_folders() → dict` | 关键词+LLM 分类 |
| 精分类 | `business/classifier/folder_classifier.py` | `refine_sample_keywords() → dict` | 后台 5 级优先级精分类 |
| 照片索引 | `business/indexer/photo_indexer.py` | `index_photos(progress_callback, batch_limit) → dict` | EXIF/缩略图/phash 入库 |
| 索引控制 | `business/indexer/photo_indexer.py` | `clear_checkpoint() / set_paused() / set_stopped()` | 断点管理 |
| 去重 | `business/indexer/photo_indexer.py` | `dedup_by_phash(progress_callback) → dict` | 感知哈希去重 |
| 标签生成 | `business/image_recognition/tag_generator.py` | `generate_tags_for_image(file_id) → list[str]` | SigLIP 图像标签 |
| 人脸聚类 | `business/image_recognition/face_cluster.py` | `cluster_faces(embeddings) → dict` | 人脸向量聚类 |
| 场景聚类 | `business/image_recognition/scene_cluster.py` | `cluster_by_scene(file_ids) → list` | CLIP 场景聚类 |
| 那年今日 | `business/memory/memory_discovery.py` | `discover_on_this_day(category) → list` | 按月日匹配历史照片 |
| 近期回忆 | `business/memory/memory_discovery.py` | `discover_recent_memories(category) → list` | 近 N 天照片 |
| 回忆查询 | `business/memory/memory_discovery.py` | `get_on_this_day_memories(category) → list` | 查询已生成的回忆 |
| 回忆推理 | `business/memory/memory_reasoning.py` | `record_dismissal(memory_id, reasoning) / get_negative_hints() → list` | 碎裂反馈与负面提示 |
| LLM 回忆 | `memory/memory_generator.py` | `generate_all_memories() → list` | DeepSeek 标题/描述生成 |

### 11.4 服务层对外接口

UI 层可调用。

| 接口 | 模块 | 函数/类 | 说明 |
|------|------|----------|------|
| 后台流水线 | `services/background_task_manager.py` | `BackgroundTaskManager` 类 | Stage 模式后台任务管理 |
| 流水线阶段 | `services/background_task_manager.py` | `Pipeline`, `ScanStage`, `ClassifyStage`, `IndexStage` | 各阶段定义 |

### 11.5 UI 层对外接口

UI 层不对外暴露接口，仅作为应用入口。

### 11.6 接口变更规则

- 新增接口：在对应层的接口表中登记后即可使用
- 删除接口：需确认无调用方后方可移除，并在架构变更审核中说明
- 修改接口签名：属于架构变更，需走审核流程

## 12. 技术债与清理计划

### 12.1 死代码清单

以下模块/函数经审计确认为 0 引用，标记为待清理。在清理前功能不受影响，但禁止新增对这些死代码的调用。

| 文件 | 死代码 | 类型 | 估计行数 |
|------|--------|------|----------|
| `services/data_service.py` | 整文件（`DataService`, `get_data_service`） | 整文件 | 41 |
| `services/recognition_scheduler.py` | 整文件（4 阶段调度逻辑已并入 background_task_manager） | 整文件 | 279 |
| `business/memory/event_detector.py` | 整文件（`detect_events`, `get_events`） | 整文件 | 130 |
| `business/memory/memory_narrator.py` | 整文件（`narrate_memory`） | 整文件 | ~50 |
| `infra/fs/everything.py` | 整文件（`is_available`, `search_images`） | 整文件 | 24 |
| `infra/db/repositories/folder_categories_repo.py` | 整文件（`FolderCategoriesRepository`） | 整文件 | ~30 |
| `infra/db/repositories/task_checkpoints_repo.py` | 整文件（`TaskCheckpointsRepository`） | 整文件 | ~30 |
| `memory/memory_generator.py` | `star_memory()`, `unstar_memory()`, `get_memories()`, `get_photo_thumbnails()` | 4 函数 | ~60 |
| `business/memory/memory_discovery.py` | `discover_person_memories()`, `discover_event_memories()`, `discover_scene_memories()` | 3 函数 | ~90 |

**总计约 700+ 行**，清理时直接删除文件/函数，不影响现有功能。

### 12.2 Deprecated 全局变量迁移计划

`config.py` 中的 deprecated 全局变量应逐步迁移到 `get_settings()` 调用。迁移完成后可移除 `_sync_module_vars_from_settings()` 和所有 deprecated 变量。

| 全局变量 | 实际调用方 | 迁移动作 | 优先级 |
|----------|-----------|----------|--------|
| `DEEPSEEK_API_KEY` | 无（3处死导入） | 直接删除导入 | 高 |
| `DEEPSEEK_BASE_URL` | 无（3处死导入） | 直接删除导入 | 高 |
| `DEEPSEEK_MODEL` | `memory_generator.py:156` (1处) | 改为 `get_settings().deepseek_model` | 中 |
| `DEEPSEEK_CLASSIFY_MODEL` | `folder_classifier.py:350`, `memory_narrator.py:31,60` | 改为 `get_settings().deepseek_classify_model` | 中 |
| `SOURCE_DRIVE` | `folder_classifier.py:246,686`, `fast_scan.py` (9处) | 改为 `get_settings().source_drive` | 低（改动多） |
| `SOURCE_DIRS` | `fast_scan.py` (10处) | 改为 `get_settings().source_dirs` | 低（改动多） |
| `DATA_DIR` | `fast_scan.py:125,153,181,193` | 改为 `get_settings().photo_data_dir` | 低 |
| `DB_PATH` | 无（1处死导入 `recommendation.py`） | 直接删除导入 | 高 |
| `THUMBNAIL_DIR` | `photo_indexer.py`, `object_detector.py`, `thumbnail_loader.py`, `person_detail.py` | 改为 `get_settings().thumbnail_dir` | 低（4文件） |
| `CLASSIFICATION_HISTORY_FILE` | `folder_classifier.py:307,310,315,316` | 改为 `get_settings().classification_history_file` | 低 |

### 12.3 已知层反转

| 来源 | 目标 | 说明 | 修复方向 |
|------|------|------|----------|
| `config.py` (Core) | `infra.llm.client.LLMClient` (Infra) | `save_config()` / `reload_config()` 调用 `LLMClient.reset()` | 改为事件/回调模式，由 Infra 层自行监听配置变更 |

### 12.4 数据访问不一致

| 问题 | 涉及模块 | 改进方向 |
|------|----------|----------|
| 业务层一半用 Repository 模式，一半用 raw SQL | `fast_scan.py`, `folder_classifier.py`, `photo_indexer.py`, `memory_generator.py` 用 raw SQL；`face_cluster.py`, `event_detector.py`, `memory_discovery.py`, `memory_reasoning.py` 用 Repository | 逐步迁移至 Repository 模式，新代码必须用 Repository |
| UI 层直接实例化 Database 和 Repository | `ui/app.py` | 逐步改为通过业务层接口间接访问 |
| `db_manager.py` 存在重复方法 | `_create_v03_new_tables` vs `_create_v03_new_tables_stmt` | 合并为一个方法 |

### 12.5 待补充依赖

| 依赖 | 说明 | 优先级 |
|------|------|--------|
| `open-clip-torch` | 代码已实现，缺 requirements.txt | 中 |
| `deepface` | 代码已实现，缺 requirements.txt | 中 |
