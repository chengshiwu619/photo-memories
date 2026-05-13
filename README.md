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
