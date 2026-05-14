# NAS 照片回忆 - 架构框架

## 1. 分层架构

```
┌─────────────────────────────────────────┐
│              UI 层 (ui/)                 │
│  app.py / components/ / recommendation  │
├─────────────────────────────────────────┤
│            服务层 (services/)            │
│  pipeline / background_task_manager     │
├─────────────────────────────────────────┤
│            业务层                        │
│  scanner / classifier / indexer / memory│
├─────────────────────────────────────────┤
│            基础设施层 (infra/)           │
│  llm / fs / db / image                  │
├─────────────────────────────────────────┤
│            核心层 (core/)                │
│  models / config / db_manager / logger  │
└─────────────────────────────────────────┘
```

### 层间依赖规则

- 上层可调用下层，下层不可调用上层
- 同层模块间通过公开函数交互，不直接操作对方内部状态
- UI 层禁止直接写 SQL，必须通过 recommendation.py 或 db_manager.py 获取数据
- 业务层禁止直接操作 UI 组件

## 2. 模块职责

### 2.1 核心层

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | `config.py` | 环境变量读取、Settings 单例、全局常量（分类ID/扩展名/模型名） |
| 数据库 | `db_manager.py` | SQLite 连接管理、表结构定义与初始化 |
| 数据模型 | `core/models.py` | 数据类定义（File, PhotoMetadata, Memory 等） |
| 日志 | `logger_setup.py` | 全局 logger 配置 |
| 断点 | `checkpoint_manager.py` | 扫描/索引任务断点持久化 |

### 2.2 基础设施层

| 模块 | 文件 | 职责 |
|------|------|------|
| LLM | `infra/llm/client.py` | OpenAI 兼容客户端封装、重试策略 |
| 文件系统 | `infra/fs/everything.py` | Everything 搜索工具封装 |
| 数据仓库 | `infra/db/repositories/` | 各表 CRUD 操作封装（当前未完全启用） |

### 2.3 业务层

| 模块 | 文件 | 职责 |
|------|------|------|
| 扫描 | `scanner/fast_scan.py` | 磁盘文件发现（Everything/os.walk）、入库 files 表 |
| 分类 | `classifier/folder_classifier.py` | 关键词预分类（样片+生活）、LLM 文件夹分类、后台双向精分类、分类变更后历史一致性修复、用户交互分类、分类历史、关键词管理 |
| 索引 | `indexer/photo_indexer.py` | EXIF 提取、缩略图生成、入库 photo_metadata 表 |
| 回忆 | `memory/memory_generator.py` | 回忆卡片数据查询（LLM 生成已禁用） |

### 2.4 服务层

| 模块 | 文件 | 职责 |
|------|------|------|
| 流水线 | `services/pipeline.py` | 启动阶段编排（Scan→Classify→Index） |
| 后台管理 | `services/background_task_manager.py` | 后台线程注册与等待 |

### 2.5 UI 层

| 模块 | 文件 | 职责 |
|------|------|------|
| 主窗口 | `ui/app.py` | MainWindow、分类切换、照片点击、翻页加载 |
| 推荐 | `ui/recommendation.py` | 照片排序、打散、新鲜度、分页 |
| 瀑布流 | `ui/components/virtual_waterfall.py` | 虚拟滚动瀑布流布局、卡片渲染 |
| 图片查看 | `ui/components/image_viewer.py` | 全屏查看、收藏、分类调整 |
| 启动窗口 | `ui/components/startup_window.py` | 初始化进度、Pipeline 信号连接 |
| 设置窗口 | `ui/components/setup_window.py` | 首次配置/修改配置、关键词管理 |
| 分类对话框 | `ui/components/folder_classifier_dialog.py` | 用户手动分类交互 |
| 回忆卡片 | `ui/components/memory_cards.py` | 回忆卡片展示 |

## 3. 数据流

### 3.1 初始化流程

```
main.py → StartupWindow → Pipeline(QThread)
  ScanStage → ClassifyStage → IndexStage
  ↓ 完成后
transition_to_main → MainWindow
  ↓ 后台继续
BackgroundTaskManager → BgScanWorker / BgIndexWorker / BgRefineWorker
```

### 3.2 分类流程

```
启动阶段 ClassifyStage:
  classify_folders()
    → 样片关键词预分类（仅检查顶层分支名，命中→样片）
    → 生活关键词预分类（仅检查顶层分支名，命中→生活）
    → LLM 分类剩余分支（采样每个分支最多5个子路径+5个文件名作为上下文，单次调用，精简prompt快速返回）
    → LLM确定的分支直接写入分类（confidence=llm-branch）
    → LLM不确定的分支暂归生活（confidence=default-pending-refine），留给后台精分类用优先级体系判断
    → 不确定的默认归生活

主页面启动后后台:
  BgRefineWorker → refine_sample_keywords()
    → 数据源: files 表所有有图片的文件夹（LEFT JOIN folder_categories，含未分类的）
    → 1次SQL查出所有文件夹的 file_name + camera_model + exif_json
    → 用户手点（confidence 含 "manual"）的文件夹跳过，永不覆盖
    → 对每个文件夹分别计算样片/生活命中的最高优先级:
      优先级: 分支分类(5) > 内容信号(4) > EXIF(3) > 文件名(2) > 路径(1)
      分支分类: 分支名命中关键词 或 LLM/关键词已判定的分支分类
      内容信号: file_name 命中样片关键词（如Graphis等品牌/系列名）
      EXIF: camera_model / exif_json 命中关键词
      文件名: file_name 命中生活关键词
      路径: 文件夹名/子路径段/日期结构(YYYY/MM) 命中关键词
    → 冲突解决: 取各自最高优先级比较，高者胜；同级时样片优先于生活
    → 未命中任何关键词且未分类→默认归生活
    → confidence=keyword-refine
    → 若文件夹分类发生变化，清理旧分类下的 memories / photo_shown_history / click_history 残留，避免旧回忆或旧历史继续展示已迁移照片

设置窗口:
  SetupWindow → 高级选项 → 关键词管理
    → 样片关键词: get_sample_keywords() / add_sample_keyword() / remove_sample_keyword()
    → 生活关键词: get_life_keywords() / add_life_keyword() / remove_life_keyword()
    → 内置关键词（代码硬编码，不可删除）
    → 自定义关键词（sample_keywords / life_keywords 表，可增删）
```

### 3.3 照片推荐流程

```
MainWindow.load_category(cat_id)
  → rank_category_photos(db, cat_id)
    → 读取 memories 表获取回忆照片 ID
    → load_photos_from_ids() 获取回忆照片详情
    → load_category_photos_batch() 获取分类下全部照片
    → 合并去重
    → 新鲜度排序（photo_shown_history 表）
    → _interleave_small_folders() 文件夹维度打散
    → _interleave_by_time() 时间维度打散（同日最多12张，超出移除；date_taken 为空回退 file_mtime）
    → 返回完整有序列表
  → UI 切片分页渲染（PAGE_SIZE=30）
  → record_shown_photos() 记录已展示
```

### 3.4 无限滚动流程

```
VirtualCategoryPage._on_scroll()
  → 检测滚动到底部
  → emit load_more_requested
  → MainWindow._on_load_more(cat_id)
    → 从 _cat_photos[cat_id] 切片下一页
    → append_photos() 追加渲染
    → record_shown_photos() 记录已展示
```

## 4. 数据库表结构

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `files` | 文件索引 | file_path(UNIQUE), folder_path, is_image |
| `folder_categories` | 文件夹分类 | folder_path(PK), category |
| `photo_metadata` | EXIF+缩略图 | file_id(PK→files), date_taken, thumbnail_path, is_starred |
| `memories` | 回忆记录 | category, photo_ids(JSON), title, is_starred |
| `click_history` | 点击记录 | file_id, folder_path, category |
| `photo_tags` | 照片标签 | file_id, tag(UNIQUE) |
| `photo_shown_history` | 展示历史 | file_id, category, shown_at |
| `sample_keywords` | 自定义样片关键词 | keyword(UNIQUE) |
| `life_keywords` | 自定义生活关键词 | keyword(UNIQUE) |

## 5. 关键常量与参数

| 常量 | 位置 | 值 | 含义 |
|------|------|----|------|
| PAGE_SIZE | recommendation.py | 30 | 每页照片数 |
| MAX_SAME_FOLDER_STREAK | recommendation.py | 12 | 同文件夹最大连续数 |
| SMALL_FOLDER_THRESHOLD | recommendation.py | 100 | 小文件夹阈值 |
| FRESHNESS_WINDOW_DAYS | recommendation.py | 7 | 新鲜度窗口（天） |
| MAX_SAME_DAY_STREAK | recommendation.py | 12 | 同日最大出现数（超出移除） |
| COL_COUNT | virtual_waterfall.py | 3 | 瀑布流列数 |
| THUMBNAIL_SIZE | config.py | (400,400) | 缩略图尺寸 |

## 6. 架构变更审核规则

以下变更属于架构变更，需提出审核方案、经明确确认后方可执行：

1. **新增/删除模块**：新增 Python 包或删除现有模块
2. **层间依赖变更**：违反分层规则的新调用（如 UI 层直接写 SQL）
3. **数据流变更**：改变模块间数据传递方式（如推荐流程的数据源变化）
4. **数据库表结构变更**：新增/删除/修改表或索引
5. **核心常量变更**：修改上述关键常量影响全局行为
6. **新增外部依赖**：requirements.txt 新增包

以下变更不属于架构变更，可直接执行：

1. 修复 bug（不改变数据流和层间关系）
2. UI 样式调整
3. 函数内部逻辑优化（不改变函数签名和调用关系）
4. 新增测试用例

## 7. 技术栈

- **语言**: Python 3.11+
- **GUI**: PyQt6
- **数据库**: SQLite (WAL 模式)
- **LLM**: DeepSeek (OpenAI 兼容 API)
- **图像处理**: Pillow + pillow-heif + exifread
- **配置管理**: pydantic-settings + python-dotenv
- **重试策略**: tenacity
- **文件搜索**: Everything SDK (es.exe) / os.walk 回退
