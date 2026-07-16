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

默认启动本地网页版并自动打开系统浏览器。网页端是唯一用户界面；初始配置仍可通过 `python main.py setup` 在命令行完成。

网页版运行时使用仓库中已经构建好的静态资源，不需要联网。修改网页源码后，在 `webapp/frontend` 中执行 `pnpm run build` 更新 `webapp/static`。

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

维护和开发入口：

- [AGENTS.md](<AGENTS.md>)：唯一 AI / Codex 必读入口，含按任务定位表。
- [项目文档/开发索引.md](<项目文档/开发索引.md>)：仅在跨模块改造或需要项目全貌时阅读。
- [项目文档/照片分类规则.md](<项目文档/照片分类规则.md>)：修改生活/样片规则时阅读。

## 当前阶段

- 本地网页端已经取代旧 PyQt 桌面端。
- 前端修改应保留异步缩略图、预加载、虚拟瀑布流、页面缓存和随机结果去重能力。
- 不要把原图读取、模型推理或重查询放回 UI 线程。
- 未经明确需要不改 schema，不跑全量识别或全量重建。
