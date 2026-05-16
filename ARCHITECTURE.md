# NAS 照片回忆 - v0.3 架构

## 1. 分层架构

```
┌──────────────────────────────────────────────────┐
│                    UI 层 (ui/)                     │
│  app.py / components/ / recommendation            │
│  sidebar / timeline / special_memories            │
├──────────────────────────────────────────────────┤
│                  服务层 (services/)                │
│  pipeline / background_task_manager               │
│  recognition_scheduler                            │
├──────────────────────────────────────────────────┤
│                     业务层                         │
│  business/image_recognition / business/memory     │
│  business/scanner / business/classifier           │
│  business/indexer / memory (generator)            │
├──────────────────────────────────────────────────┤
│                基础设施层 (infra/)                  │
│  llm / fs / db / image                           │
├──────────────────────────────────────────────────┤
│                  核心层 (core/)                    │
│  models / config / db_manager / logger            │
└──────────────────────────────────────────────────┘
```

### 层间依赖规则

- 上层可调用下层，下层不可调用上层
- 同层模块间通过公开函数交互，不直接操作对方内部状态
- UI 层禁止直接写 SQL，必须通过 recommendation.py 或 db_manager 获取数据
- 业务层禁止直接操作 UI 组件
- AI 识别任务使用缩略图，不读取原图
- 涉及用户照片的删除/移动操作，永远走"标记"而非物理操作

## 2. 模块职责

### 2.1 核心层

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | `config.py` | 环境变量读取、Settings 单例、全局常量（分类ID/扩展名/模型名）、多照片库路径支持（分号分隔，通过 `source_dirs` 解析） |
| 数据库 | `db_manager.py` | SQLite 连接管理、表结构定义与初始化、v0.2→v0.3 自动迁移 |
| 数据模型 | `core/models.py` | 数据类定义（File、PhotoMetadata、Memory、FaceEmbedding、FaceCluster、Event、MemoryReasoning、TaskCheckpoint 等） |
| 日志 | `logger_setup.py` | 全局 logger 配置、多文件分级（app.log 全量 / error.log WARNING+ / crash.log 未捕获异常）、sys.excepthook + threading.excepthook 接管、启动崩溃 marker（last_run.txt）、按天滚动 |
| 断点 | `checkpoint_manager.py` | 通用长任务断点持久化（扫描/索引/识别统一使用 `task_checkpoints` 表） |

### 2.2 基础设施层

| 模块 | 文件 | 职责 |
|------|------|------|
| LLM | `infra/llm/client.py` | OpenAI 兼容客户端封装、重试策略 |
| 文件系统 | `infra/fs/everything.py` | Everything 搜索工具封装、多路径查询支持 |
| 数据仓库 | `infra/db/repositories/` | 各表 CRUD 操作封装（FilesRepo、PhotoMetadataRepo、MemoriesRepo、PhotoTagsRepo、ClickHistoryRepo） |
| CLIP编码器 | `infra/image/clip_encoder.py` | SigLIP/OpenCLIP 图像嵌入提取（后台，使用缩略图） |
| 人脸检测 | `infra/image/face_detector.py` | DeepFace 人脸检测与特征提取（使用缩略图，固定 ArcFace 后端） |
| 目标检测 | `infra/image/object_detector.py` | 目标检测抽象接口 + YOLOv8 实现（ultralytics，预留切换后端） |
| 缩略图加载 | `infra/image/thumbnail_loader.py` | 识别模块共享的缩略图加载器，统一 LRU 内存管理（256张） |

### 2.3 业务层

| 模块 | 文件 | 职责 |
|------|------|------|
| 扫描 | `business/scanner/fast_scan.py` | 磁盘文件发现（Everything/os.walk）、入库 files 表、多照片库路径遍历、`source_dir` 字段标记 |
| 分类 | `business/classifier/folder_classifier.py` | 关键词预分类 + LLM 分类 + 后台精分类、自动清理旧分类残留 |
| 索引 | `business/indexer/photo_indexer.py` | EXIF 提取、缩略图生成、感知哈希去重（`dedup_by_phash`）、入库 photo_metadata 表 |
| 图像标签 | `business/image_recognition/tag_generator.py` | 基于 SigLIP 嵌入的图像标签生成策略 |
| 人脸聚类 | `business/image_recognition/face_cluster.py` | 人脸向量聚类、人物分组管理、用户纠偏（标记为他人）、rename_cluster、reassign_face |
| 场景聚类 | `business/image_recognition/scene_cluster.py` | CLIP 场景聚类（距离判定） |
| 回忆发现 | `business/memory/memory_discovery.py` | 那年今日回忆、近期回忆、人物回忆、事件回忆、场景回忆、数据查询与过滤 |
| 事件检测 | `business/memory/event_detector.py` | 时间断裂聚类 + GPS 聚类、事件/旅行发现 |
| 回忆叙事 | `business/memory/memory_narrator.py` | LLM 叙事生成 |
| 回忆推理 | `business/memory/memory_reasoning.py` | 碎裂回忆反馈记录、负面提示管理 |
| 回忆生成 | `memory/memory_generator.py` | LLM 回忆标题/描述生成（v0.2 保留模块，与 memory_discovery 并存：discovery 负责规则发现入口，generator 负责 LLM 叙事能力） |

### 2.4 服务层

| 模块 | 文件 | 职责 |
|------|------|------|
| 流水线 | `services/background_task_manager.py` | Stage 模式流水线（扫描/分类/索引/回忆）、进度回调、取消机制、交互式分类、批量限制；后台线程统一注册与安全等待退出 |
| 识别调度 | `services/recognition_scheduler.py` | 识别任务调度初始实现（支持 SigLIP 单批推理，断点续传，进度上报；完整 AI 流水线待后续完善） |

### 2.5 UI 层

| 模块 | 文件 | 职责 |
|------|------|------|
| 主窗口 | `ui/app.py` | MainWindow、侧边栏导航切换（随机回忆/时间线/特殊回忆） |
| 推荐 | `ui/recommendation.py` | 照片排序、打散、新鲜度、分页、去重过滤（`is_duplicate_of`） |
| 瀑布流 | `ui/components/virtual_waterfall.py` | 虚拟滚动瀑布流布局、卡片渲染 |
| 图片查看器 | `ui/components/image_viewer.py` | 全屏查看、收藏、分类调整 |
| 启动窗口 | `ui/components/startup_window.py` | 初始化进度、后台任务启动 |
| 设置窗口 | `ui/components/setup_window.py` | 首次配置/修改配置、关键词管理、多照片库路径管理 |
| 分类对话框 | `ui/components/folder_classifier_dialog.py` | 用户手动分类交互 |
| 回忆卡片 | `ui/components/memory_cards.py` | 回忆卡片展示（v0.3 重写） |
| 侧边栏导航 | `ui/components/sidebar.py` | 3个导航项切换 |
| 时间线视图 | `ui/components/timeline_view.py` | 按日期分组的照片时间线布局 |
| 特殊回忆视图 | `ui/components/special_memories.py` | 回忆卡片堆叠布局、碎裂动画框架（QPropertyAnimation） |
| 人物详情页 | `ui/components/person_detail.py` | 人物回忆详情页、命名、纠偏入口 |

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
recognition_scheduler.py（初始框架）
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
| 10 | 目标检测（YOLOv8） | infra/image | 中 | ✅ 已实现 |
| 11 | custom-ui-pyqt6增强卡片效果 | UI层 | 延后 | ⏸️ 延后（原生PyQt6） |
| 12 | 特殊回忆卡片碎裂动画 | UI层 | 中 | ⚠️ 框架已实现（细节待完善） |
| 13 | 碎裂回忆反馈机制 | memory、LLM | 中 | ✅ 已实现 |
| 14 | 人物回忆纠偏 | UI层、business | 中 | ✅ 已实现 |
| 15 | 多照片库支持 | config、scanner、everything、setup_window | 中 | ✅ 已实现 |

## 7. 依赖与风险

### 外部依赖

| 依赖 | 用途 | 许可证 | 状态 |
|------|------|--------|------|
| imagehash | 感知哈希去重 | BSD-2 | ✅ requirements.txt |
| open-clip-torch | SigLIP/OpenCLIP 语义标签 | Apache-2.0 | ⚠️ 代码已实现，待添加到 requirements.txt |
| deepface | 人脸检测与聚类 | MIT | ⚠️ 代码已实现，待添加到 requirements.txt |
| onnxruntime | YOLOv8 ONNX 目标检测 | MIT | ✅ requirements.txt（替代 ultralytics，消除 AGPL 风险） |
| sqlite-vec | 向量近似检索 | MIT | ❌ 暂未集成（当前纯Python） |
| custom-ui-pyqt6 | 增强卡片视觉效果 | 未确认 | ⏸️ 延后 |

### object_detector 抽象接口
```python
class ObjectDetector(Protocol):
    def detect(self, image_path: str) -> list[dict]: ...

class YOLOv8ONNXDetector:  # 当前实现，基于 onnxruntime
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

## 9. 架构变更审核规则

以下变更属于架构变更，需提出审核方案、经明确确认后方可执行：
1. **新增/删除模块**：新增 Python 包或删除现有模块
2. **层间依赖变更**：违反分层规则的新调用
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
