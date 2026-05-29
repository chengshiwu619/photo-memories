# NAS 照片回忆

> 本地化搭建的照片回忆系统，用它来唤醒 NAS 沉睡的照片。

你的 NAS 里躺着几万张照片，却很少翻看。这个项目用 LLM 自动分类文件夹、AI 识别生成回忆，以瀑布流的方式把照片重新呈现给你——一切都在本地运行，数据不离开你的硬盘。

## 功能特点

- 🔍 **极速扫描** — Everything 搜索引擎集成，6 万+文件秒级发现；无 Everything 时自动回退 os.walk
- 🤖 **LLM 智能分类** — DeepSeek API 自动将文件夹归为生活照片 / 拍摄样片
- 🧠 **AI 识别** — SigLIP 语义标签、DeepFace 人脸聚类、YOLOv8 目标检测（均基于缩略图，onnxruntime 推理）
- 💭 **回忆生成** — 那年今日、近期回忆、特殊日期回忆、文件夹回忆，多类型卡片堆叠展示
- 🖼️ **瀑布流浏览** — 虚拟滚动 + 懒加载缩略图，万级照片流畅展示，循环洗牌不重复
- 📅 **时间线视图** — 按拍摄时间浏览全部照片
- ✨ **特殊回忆** — 节日回忆、文件夹回忆等多类型卡片堆叠，初期自动填充
- 🔒 **完全本地** — 照片、缩略图、数据库全部存储在本地，仅 LLM 调用需要联网

## 快速开始

### 环境依赖

- Python 3.10+
- [DeepSeek API Key](https://platform.deepseek.com/)（用于分类和回忆生成）
- Windows（Everything 集成为可选）

### 安装

```bash
git clone https://github.com/chengshiwu619/photo-memories.git
cd photo-memories
pip install -r requirements.txt
```

### 启动

```bash
python main.py ui
```

首次启动会弹出配置窗口，填写：
- **照片库路径** — NAS 照片存放路径（如 `Y:\`），支持分号分隔多路径
- **缓存数据路径** — 数据库和缩略图存储路径
- **DeepSeek API Key** — `sk-...`

启动后自动执行：文件扫描 → LLM 分类 → 缩略图生成 → 回忆发现，无需手动操作。

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
├── business/                # 业务层
│   ├── classifier/          # LLM 文件夹分类 + 关键词精分类
│   ├── indexer/             # 照片索引 & 缩略图生成 & 感知哈希去重
│   ├── memory/              # 回忆发现（那年今日/近期/特殊日期/文件夹）
│   ├── scanner/             # 文件扫描（Everything / os.walk）
│   └── image_recognition/   # AI 识别（场景聚类/人脸/目标检测）
├── infra/                   # 基础设施层
│   ├── db/repositories/     # 数据仓库（FilesRepo/MemoriesRepo/...）
│   ├── image/               # 缩略图加载/CLIP编码/人脸检测/目标检测
│   └── llm/                 # LLM 客户端（DeepSeek/OpenAI 兼容）
├── core/                    # 核心层
│   ├── models.py            # 数据模型定义
│   └── checkpoint_manager.py # 长任务断点持久化
├── services/                # 服务层
│   └── background_task_manager.py # 后台任务管理
├── ui/                      # UI 层
│   ├── app.py               # 主窗口
│   ├── components/          # 瀑布流/侧边栏/图片查看器/特殊回忆/时间线
│   └── recommendation.py    # 照片排序 & 间隔算法
├── config.py                # 配置管理（Pydantic Settings + .env）
├── db_manager.py            # 数据库管理（SQLite + WAL + 自动迁移）
├── logger_setup.py          # 日志系统
└── main.py                  # 入口
```

## 技术栈

- **UI**: PyQt6 + 虚拟瀑布流（QScrollArea + 动态卡片）+ 异步原图加载
- **LLM**: DeepSeek API（文件夹分类 + 回忆生成）
- **AI 识别**: SigLIP/OpenCLIP（语义标签）+ DeepFace（人脸聚类）+ LibreYOLO ONNX（目标检测）
- **扫描**: Everything CLI / os.walk
- **数据库**: SQLite + WAL 模式 + 版本自动迁移
- **缩略图**: Pillow + EXIF 自动旋转 + 感知哈希去重
- **配置**: Pydantic Settings + .env

## 测试

```bash
python -m pytest tests/test_config.py
```

## License

[MIT](LICENSE)
