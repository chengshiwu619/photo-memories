# NAS 照片回忆

## 环境依赖

- Python 3.13+
- pip 安装依赖：`pip install -r requirements.txt`

## Everything 集成（可选但强烈推荐）

项目内置了 Everything 命令行集成，用于极速文件扫描。需要以下文件放入 `everything/` 目录：

### 必需文件

| 文件 | 用途 | 来源 |
|------|------|------|
| `es.exe` | Everything CLI | 项目自带（ES-1.1.0.30.x64） |
| `Everything64.exe` | Everything 搜索服务 | [voidtools.com](https://www.voidtools.com/downloads/) Everything 1.5+ 便携版 |

### 配置步骤

1. 下载 [Everything 1.5a 便携版 64位](https://www.voidtools.com/forum/viewtopic.php?t=9787)（`Everything-1.5a.x64.zip`）
2. 将 `Everything64.exe` 放入 `everything/` 目录
3. **以管理员身份运行** `Everything64.exe`（仅在首次安装时需管理员权限以创建 NTFS 索引）
4. 前往 **工具 → 选项 → NTFS**，对 `Y:` 盘勾选「包含在数据库中」（如果 Y 盘是 NTFS）
5. 如果 Y 盘是网络盘（NAS/SMB），前往 **工具 → 选项 → 文件夹**，添加 `Y:\` 为强制索引
6. 等待索引完成（状态栏显示文件数量停止增长即可）
7. 后续启动时 `launch.bat` 会自动以后台服务模式启动 Everything

### 工作原理

- 程序启动时自动探测 Everything 实例名（默认、1.5a、1.5）—— 本项目已内建自动探测
- 若 Everything 能直接索引文件（NTFS 卷），使用 `es.exe -csv` 导出全部媒体文件路径，几乎瞬间完成
- 若 Everything 只有文件夹索引（NAS/网络盘 Folder Index），则先通过 Everything 获取全量文件夹列表，再遍历文件夹扫描媒体文件，速度接近 Everything 直接索引
- `es.exe` 已内置在 `everything/` 目录（ES-1.1.0.30.x64），无需额外下载
- 无 Everything 时自动回退到 `os.walk` 遍历 + 文件列表缓存（首次慢，之后秒取）

## 首次使用

### GUI 模式

```bash
python main.py ui
# 或双击 launch.bat
```

首次启动会弹出配置窗口，填写：
- **照片库文件夹**：照片存放路径（如 `Y:\`）
- **缓存数据文件夹**：数据库/缩略图存储路径（如 `D:\测试\pipecache`）
- **DeepSeek API Key**：`sk-...`

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

## 数据库

位置由 `.env` 中的 `PHOTO_DATA_DIR` 指定，默认自动创建。包含的表：

- `files` — 文件清单
- `folder_categories` — 文件夹分类
- `photo_metadata` — 照片元数据和缩略图
- `memories` — LLM 生成的回忆
- `click_history` — 浏览记录
