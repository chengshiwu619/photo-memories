# photo-memories

本项目是一个本地照片回忆库：扫描 NAS 或本地照片，生成缩略图、索引、标签和回忆卡片，帮助重新发现沉睡照片。

## 产品定位

- 所有照片默认都有回忆价值。
- AI 识图只负责打标签，不负责筛选或排除。
- 成人、写真、截图、生活照不默认排除。
- 重复、损坏是状态问题，不是内容排除。
- 特殊回忆是类似苹果相册 Memories 的卡片堆叠，不是简单 tag group。

## 环境

- Python 3.10+
- Windows
- SQLite
- 可选：Everything / `es.exe`
- 可选：SigLIP 依赖（仅增强标签，不阻塞基础流程）
- 可选：deepface（人脸检测/聚类，默认关闭，设置 `ENABLE_FACE_DETECTION=true` 启用）

## 安装

```bash
git clone <repo>
cd photo-memories
pip install -r requirements.txt
```

## 启动

```bash
启动GPU相册.bat
```

首次启动需要配置：

- 照片目录
- 缓存目录
- API Key（仅在需要 LLM 分类/生成时）

## 常用命令

### 正式维护入口

完整性检查：

```bash
python scripts/check_integrity.py
python scripts/check_integrity.py --db-path D:\photo-memories-cache\photos.db --with-repair-plan
```

缩略图维护：

```bash
python scripts/maintain_thumbnails.py --db-path D:\photo-memories-cache\photos.db --retry-failed
python scripts/maintain_thumbnails.py --db-path D:\photo-memories-cache\photos.db --retry-failed --file-id 1072
```

增量扫描新增照片：

```bash
python scripts/rescan_photos.py --limit 200 --verbose
python scripts/rescan_photos.py --limit 200 --apply --index --index-limit 50
python scripts/rescan_photos.py --no-everything --limit 200 --verbose
```

基础 path 标签：

```bash
python scripts/run_ai_labeling.py --db-path D:\photo-memories-cache\photos.db --source path --limit 50 --dry-run
python scripts/run_ai_labeling.py --db-path D:\photo-memories-cache\photos.db --source path --limit 50 --apply
```

path 标签审计：

```bash
python scripts/audit_path_tags.py --db-path D:\photo-memories-cache\photos.db --source path --top 200
python scripts/audit_path_tags.py --db-path D:\photo-memories-cache\photos.db --source path --top 200 --json
```

### 保留但非日常入口

- `scripts/maintain_paths.py`: 旧数据路径状态回填；正常启动流程会后台维护，手动执行前先 dry-run。
- `scripts/maintain_memories.py`: 不可渲染 memories 的维护入口；特殊回忆功能后续再整体整理。
- `scripts/run_ai_recognition.py`: SigLIP 小批量验证入口，属于增强链路，不作为正常用户流程依赖。

## 文档入口

维护入口统一看：

- [项目文档/AGENTS.md](<项目文档/AGENTS.md>)
- [项目文档/项目架构.md](<项目文档/项目架构.md>)
- [项目文档/项目状态.md](<项目文档/项目状态.md>)
- [项目文档/项目记忆.md](<项目文档/项目记忆.md>)

## 当前建议

- 先做缩略图内容识别和视觉标签生产。
- 当前不要做 UI 大改、schema 改动、全量 SigLIP、人脸识别、YOLO 全量化。
- 不要一开始就跑全量识别或全量重建。
