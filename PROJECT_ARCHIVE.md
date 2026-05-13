# NAS 照片回忆 — 项目档案

> 生成日期：2026-05-13
> 版本：当前运行版本
> 用途：重构参考文档

---

## 一、项目概述

基于 **Python 3.10+ / PyQt6** 的桌面照片管理工具。对指定文件夹（NAS/Y盘）中的照片/视频进行全量扫描，调用 **DeepSeek LLM** 自动分类文件夹并生成带温度的「回忆」文字，以瀑布流形式交互展示。

**核心能力**：扫描 → 分类 → 索引（EXIF+缩略图） → 回忆生成 → 瀑布流展示

---

## 二、目录结构

```
photo-memories/
├── main.py                     # CLI入口：scan/classify/index/memories/all/ui/setup 七命令
├── config.py                   # .env加载、SQLite建表、OpenAI客户端、分类常量
├── logger_setup.py             # RotatingFileHandler(5MB×3) + StreamHandler
├── clean_data.py               # 运维：清空分类/回忆/点击/收藏，保留files+缩略图
├── launch.bat                  # 双击启动：Everything服务 → python -B main.py ui
├── requirements.txt            # openai Pillow pillow-heif python-dotenv PyQt6 exifread
├── .env.example                # 配置模板（不含密钥）
│
├── scanner/
│   ├── fast_scan.py            # 主扫描器：Everything es.exe + os.walk回退 + 断点续扫
│   └── file_scanner.py         # 独立回退扫描器：os.walk + MD5去重（已不常用）
│
├── classifier/
│   └── folder_classifier.py    # LLM文件夹4分类 + 分支传播 + 相似照片检测
│
├── indexer/
│   └── photo_indexer.py        # EXIF提取 + 400×400缩略图生成 + 断点续传
│
├── memory/
│   └── memory_generator.py     # LLM回忆生成：聚焦同天/同文件夹5-12张照片
│
├── ui/
│   ├── app.py                  # MainWindow：分类导航、瀑布流翻页、全屏查看、收藏/重分类
│   ├── recommendation.py       # 推荐排序：回忆照片ID优先 + 点击加权 + 文件夹压制
│   └── components/
│       ├── memory_cards.py     # PhotoCard淡入动画 + WaterfallLayout + CategoryPage无限滚动
│       ├── image_viewer.py     # 全屏查看器：左右翻页、EXIF自动旋转、收藏/重分类
│       ├── startup_window.py   # 4阶段启动窗口：扫描→分类→索引→回忆 + 后台线程触发
│       ├── setup_window.py     # 首次配置窗口：照片库/缓存路径/API Key
│       └── folder_classifier_dialog.py  # LLM分类确认弹窗：4分类按钮 + 分支预览
│
├── everything/
│   ├── es.exe / es.exe.old     # Everything命令行工具（NTFS全盘搜索）
│   └── ensure.py               # Everything进程管理：启动/检测/实例探测
│
└── storage/logs/               # 项目内日志（运行时自动创建）
```

**文件清单**：14 个 `.py` 文件 + 2 个 `.exe` + 1 个 `.bat` + 配置/依赖文件

---

## 三、数据流程

```
                  ┌──────────────────┐
                  │  Everything es.exe│ ← NTFS MFT索引
                  │  或 os.walk 回退  │
                  └────────┬─────────┘
                           │ filelist.txt (缓存)
                           ▼
┌─────────┐    INSERT    ┌──────────────┐    LLM     ┌──────────────────┐
│ files   │◄────────────│ 扫描阶段 (1/4) │──────────►│ folder_categories│
│ (路径/  │             │ full_scan()   │ classify   │ (1生活2样片3摄影  │
│  大小/  │             └──────────────┘ _folders()  │  4色情)          │
│  时间)  │                                           └──────────────────┘
└────┬────┘                                                  │
     │                                               分支传播到子文件夹
     │                                                       │
     ▼                                                       ▼
┌──────────────┐    EXIF+PIL   ┌──────────────┐    LLM     ┌──────────┐
│ 索引阶段(3/4)│◄─────────────│ photo_metadata│──────────►│ memories │
│ index_photos │ 缩略图400×400│ (日期/相机/   │ generate  │ (标题/   │
│ (断点续传)   │              │  GPS/缩略图)  │ _all_     │  描述/   │
└──────────────┘              └──────────────┘ memories() │ 照片ID)  │
                                                           └────┬─────┘
                                                                │
     ┌──────────────────────────────────────────────────────────┘
     ▼
┌─────────────────────────────────────────────────────┐
│              UI 主界面 (MainWindow)                   │
│  ┌──────────────────────────────────────────────┐   │
│  │  分类导航栏: [生活照片] [拍摄样片] [摄影照片] [色情照片] │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │  CategoryPage × 4                             │   │
│  │  WaterfallLayout (3列瀑布流)                   │   │
│  │  PhotoCard (淡入动画, 40ms)                    │   │
│  │  无限滚动 → load_category_photos_batch()       │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │  ImageViewer (全屏覆盖)                        │   │
│  │  左右翻页 / EXIF旋转 / 收藏⭐ / 重分类 / 打开文件夹│
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 四、SQLite 数据库结构

数据库文件：`{PHOTO_DATA_DIR}/photos.db`

### 表结构

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `files` | 文件清单 | `file_path`(UNIQUE), `folder_path`, `file_size`, `file_mtime`, `is_image` |
| `folder_categories` | 文件夹分类 | `folder_path`(PK), `category`(1-4), `confidence` |
| `photo_metadata` | 元数据+缩略图 | `file_id`(PK→files.id), `date_taken`, `camera_model`, `gps_lat/lon`, `thumbnail_path`, `is_starred` |
| `memories` | LLM回忆 | `category`, `title`, `description`, `photo_ids`(JSON), `cover_file_id`, `is_starred` |
| `click_history` | 用户点击 | `file_id`, `folder_path`, `category`, `clicked_at` |
| `photo_tags` | 用户标签 | `file_id`, `tag`(UNIQUE组合) |

### 关键查询关系

```
files ◄──(file_id)── photo_metadata
files ◄──(folder_path)── folder_categories
memories ◄──(photo_ids JSON数组)── files.id
files ◄──(file_id)── click_history
```

---

## 五、模块职责详述

### 5.1 config.py — 全局配置中心

- `dotenv` 加载 `.env` 文件
- 所有路径变量：`SOURCE_DRIVE`, `DATA_DIR`, `DB_PATH`, `THUMBNAIL_DIR`
- `init_all_tables()` 幂等建表（`CREATE TABLE IF NOT EXISTS`）
- `get_openai_client()` 懒加载单例（兼容 DeepSeek API）
- `save_config()` / `reload_config()` 持久化和刷新配置
- `is_configured()` 检查三要素（API Key、源路径、数据路径）
- WAL 模式启用：`PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=30000`
- 分类常量：`CATEGORY_LIFE=1, CATEGORY_SAMPLE=2, CATEGORY_PHOTOGRAPHY=3, CATEGORY_ADULT=4`

### 5.2 scanner/fast_scan.py — 文件扫描引擎

**核心流程**：
1. `_list_all_image_files()` → Everything es.exe 全局扫描或 filelist.txt 缓存
2. Everything 不可用 → `_walk_files()` (os.walk) 回退
3. `full_scan()` 遍历 file_list，对比 DB 已有记录，新增入库
4. 路径规范化：`os.path.normpath()` 防止双斜杠不一致

**断点续扫**：
- 检查点文件：`scan_checkpoint.json`（state/running/paused/stopped + current_index）
- 每 100 条保存检查点，每 50 条 commit
- `batch_limit` 参数控制前台热身数量（默认 500）
- 暂停/停止标志检测（每 100 条轮询文件）

**已知问题**：Everything es.exe 输出为系统 ANSI 编码（GBK），含有日文假名或特殊 Unicode 字符的路径会被替换为 `?`，导致约 3600 个文件无法入库。

### 5.3 classifier/folder_classifier.py — LLM 文件夹分类

**流程**：
1. 从 `files` 表提取顶层文件夹分支
2. 构建 `classification_history.txt` 作为上下文
3. 调用 DeepSeek API 分类（返回 JSON：`{分类ID: [文件夹列表]}`）
4. `propagate_branch_category()` 传播到子文件夹
5. 交互确认弹窗（`needs_user` 分支）

**Prompt 设计**：提供 4 分类定义 + 历史已分类文件夹上下文 + 当前待分类分支列表，要求 LLM 返回严格 JSON。

**相似检测**：`find_similar_photos_in_folder()` 通过 LLM 判断同文件夹中与目标照片相似的其他照片，用于重分类时批量移动。

### 5.4 indexer/photo_indexer.py — 元数据提取与缩略图

**EXIF 提取**（exifread）：
- 拍摄日期（EXIF DateTimeOriginal > Image DateTime）
- 相机型号（Image Model）
- GPS 经纬度（GPSLatitude/Longitude + 方向参考）
- 方向信息（Image Orientation）

**缩略图生成**（Pillow + pillow-heif）：
- 等比例缩放到 400×400 以内（`Image.LANCZOS`）
- 自动 EXIF 旋转（`ImageOps.exif_transpose`）
- RGBA/P 模式转 RGB
- 保存为 JPEG quality=80，路径 `{file_id}.jpg`
- 已存在缩略图跳过（`os.path.exists` 检查）

**断点续传**：
- 检查点：`index_checkpoint.json`
- `get_unindexed_photos()`：LEFT JOIN photo_metadata WHERE pm.file_id IS NULL
- 每 20 条 commit，每 20 条存检查点

**并发保护**：
- `timeout=30` + `PRAGMA busy_timeout=30000` + WAL 模式
- 与 MainWindow 的读取连接并发安全

### 5.5 memory/memory_generator.py — 回忆生成

**流程**：
1. `get_photos_by_category()` 查询分类下所有有缩略图照片
2. `pick_focused_photos()` 聚焦策略：
   - 优先：同一拍摄日期 ≥5 张且 ≤max_count
   - 次选：同一文件夹名 ≥5 张且 ≤max_count
   - 兜底：随机采样 max_count 张（默认 12）
3. `build_photo_context()` 构建 Prompt 上下文（文件名/文件夹/日期/设备）
4. 调用 DeepSeek API（`response_format: json_object`, temperature 0.8-1.1）
5. 结果写入 `memories` 表

**Prompt 要点**：6-8 字标题 + 30-80 字感性描述，不编造信息。

### 5.6 ui/app.py — 主界面

**MainWindow 职责**：
- 4 分类 CategoryPage 切换（QStackedWidget）
- `load_memories()` → 加载回忆摘要 + `rank_category_photos()` 排序
- 滚动隐藏/显示顶栏导航栏（delta > 5px）
- 左右滑动手势切换分类（delta > 80px）+ 键盘 ←→
- 全屏切换（F 键）
- 收藏/重分类/点击记录

**closeEvent**：等待 `_bg_threads` 中的后台线程（最多 5 秒）

**main() 启动流程**：
1. 清理 `__pycache__`
2. 检查配置 → 未配则显示 SetupWindow
3. 显示 StartupWindow（4 阶段 + 进度条）
4. 完成后 emit → show_main_window → 构建 MainWindow
5. 同时启动后台扫描/索引线程

**后台线程**：
- `BgScanWorker`：QThread 中调用 `full_scan()`，处理暂停/停止检查点
- `BgIndexWorker`：QThread 中调用 `index_photos()`，实时信号汇报进度

### 5.7 ui/recommendation.py — 推荐排序

**排序策略**：
1. 优先：memories.photo_ids 中的照片（回忆相关）
2. 再按：收藏（前 3 张） + 点击加权（×0.05，上限 0.35）
3. 过滤：仅显示 `pm.thumbnail_path IS NOT NULL` 的照片
4. 排序：`pm.date_taken DESC`
5. 分页：PAGE_SIZE=30，无限滚动加载

### 5.8 ui/components/ 组件

| 组件 | 功能 |
|------|------|
| `memory_cards.py` | PhotoCard(40ms淡入) + WaterfallLayout(3列) + CategoryPage(逐张展示+无限滚动) |
| `image_viewer.py` | 全屏QPixmap、左右键翻页、EXIF自动旋转、收藏⭐、重分类弹窗、打开资源管理器 |
| `startup_window.py` | StartupWorker(QThread) 4阶段流程 + StartupWindow 进度UI + 分类交互托管 |
| `setup_window.py` | 表单式配置：照片库路径/缓存路径/API Key |
| `folder_classifier_dialog.py` | 分支文件夹预览 + 4分类按钮 + 跳过/完成 |

---

## 六、启动流程（完整时序）

```
launch.bat 或 python main.py ui
  │
  ├─ 1. 检查 .env 配置 → 未配置则 SetupWindow
  │
  ├─ 2. StartupWindow.show()
  │     └─ StartupWorker(QThread).start()
  │         ├─ clear_scan() + clear_index() 清旧检查点
  │         ├─ 阶段1: full_scan(batch_limit=500)
  │         │    ├─ _list_all_image_files() → Everything 或 filelist.txt
  │         │    ├─ 对比 DB existing set
  │         │    ├─ 前500新增入库 → 剩余挂 bg_scan_needed
  │         │    └─ 移除不存在文件
  │         ├─ 阶段2: classify_folders()
  │         │    ├─ 提取顶层分支
  │         │    ├─ LLM 分类
  │         │    ├─ needs_user? → 弹出分类确认对话框
  │         │    └─ propagate_branch_category()
  │         ├─ 阶段3: index_photos(batch_limit=100)
  │         │    ├─ _skip_index()? (>=100缩略图)
  │         │    │   → 跳过前台，设 bg_needed=True
  │         │    └─ 否则 100张热身 → 剩余挂 bg_needed
  │         ├─ 阶段4: generate_all_memories()
  │         │    └─ 4分类逐个：聚焦照片 → LLM → INSERT memories
  │         ├─ emit background_scan_needed → BgScanWorker
  │         ├─ emit background_index_needed → BgIndexWorker
  │         └─ emit all_done → transition_to_main
  │
  └─ 3. MainWindow.show()
        ├─ init_all_tables() + DB连接
        ├─ setup_ui() (导航栏+QStackedWidget×4)
        ├─ load_memories() → rank_category_photos()
        └─ 后台线程持续运行
```

---

## 七、配置项 (.env)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API 密钥（必需） |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名称 |
| `SOURCE_DRIVE` | `D:\测试` | 照片库根路径 |
| `PHOTO_DATA_DIR` | `{项目根}/storage` | 缓存数据目录（DB、缩略图、检查点等） |

---

## 八、依赖清单

| 包 | 版本 | 用途 |
|----|------|------|
| `openai` | ≥1.0.0 | DeepSeek API 调用 |
| `Pillow` | ≥10.0.0 | 图片缩略图、旋转、格式转换 |
| `pillow-heif` | ≥1.0.0 | HEIC 格式支持 |
| `python-dotenv` | ≥1.0.0 | .env 配置加载 |
| `PyQt6` | ≥6.5.0 | 桌面 GUI 界面 |
| `exifread` | ≥3.0.0 | EXIF 元数据提取 |

---

## 九、已知问题 & 重构建议

### 代码层面

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 1 | Everything es.exe GBK编码导致含日文/特殊字符路径变`?` | fast_scan.py | 改用 `subprocess.run(encoding='utf-8')` 或文件系统直接枚举替代 |
| 2 | 组件文件过大 | memory_cards.py 300+行, startup_window.py 400+行 | 拆分为更小单元 |
| 3 | 扫描/索引模块代码重复 | fast_scan.py ↔ file_scanner.py ↔ photo_indexer.py | 提取公共 CheckpointManager 基类 |
| 4 | `_bg_threads` 模块级变量，隐式依赖 | app.py | 改为 MainWindow 属性或在 main() 中传入 |
| 5 | 启动流程4阶段耦合在 StartupWorker.run() | startup_window.py | 拆分为 Pipeline 模式，每个阶段独立 worker |
| 6 | SQL 查询分散在多处 | recommendation.py, memory_generator.py, photo_indexer.py | 集中到 data_access 层 |
| 7 | 前台扫描/索引用 `batch_limit` 硬编码 | startup_window.py L59/L103 | 改为可配置或自适应 |
| 8 | 缩略图文件无清理机制 | photo_indexer.py | 照片删除时同步清理对应缩略图 |
| 9 | PIL 大图内存风险 | photo_indexer.py L11 | `MAX_IMAGE_PIXELS=500M` 对超大图可能 OOM |

### 架构层面

| # | 问题 | 建议 |
|---|------|------|
| 1 | 单文件 SQLite 无并发写入优化 | 评估是否需要迁移到专用连接池或服务端 DB |
| 2 | LLM 调用无重试/速率限制 | 加 tenacity 重试 + API 调用队列 |
| 3 | 无单元测试 | 至少对 scanner/indexer/memory 核心逻辑加 tests |
| 4 | 瀑布流全量渲染 | 6 万张照片时内存压力大，考虑虚拟滚动 |
| 5 | 回忆只生成一次 | 索引完成后自动增量生成新分类的回忆 |

---

## 十、数据存储位置

| 内容 | 路径 | 大小参考 |
|------|------|---------|
| 数据库 | `{PHOTO_DATA_DIR}/photos.db` | ~80 MB（6万条） |
| 缩略图 | `{PHOTO_DATA_DIR}/thumbnails/*.jpg` | 全部完成后 ~3 GB |
| 文件列表缓存 | `{PHOTO_DATA_DIR}/filelist.txt` | ~8 MB |
| 分类历史 | `{PHOTO_DATA_DIR}/classification_history.txt` | ~50 KB |
| 扫描检查点 | `{PHOTO_DATA_DIR}/scan_checkpoint.json` | ~100 B |
| 索引检查点 | `{PHOTO_DATA_DIR}/index_checkpoint.json` | ~100 B |
| 应用日志 | `{项目}/storage/logs/app.log` | 滚动 5MB×3 |
