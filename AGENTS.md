# AGENTS

本文件是 photo-memories 唯一必读的 AI / Codex 维护入口。不要默认继续读取 README 或整个 `项目文档/`；只在任务命中下表时打开对应文件。

## 当前目标

- 本地网页端是唯一用户界面，可继续修改页面结构、交互和视觉表现；不要恢复 PyQt 桌面入口。
- 已有异步缩略图、可视区预加载、虚拟瀑布流、随机结果去重和页面缓存是前端性能基线，调整 UI 时不得退回同步读图或一次性渲染全量照片。
- AI 成人内容识别只生成标签和“疑似样片”候选，不自动改分类；最终由用户确认。
- SigLIP 只读本地模型缓存，软件不得包含联网下载模型的逻辑。

## 任务索引

| 任务 | 首要入口 | 需要时再看 |
| --- | --- | --- |
| 网页导航、页面和组件 | `webapp/frontend/src/App.jsx` | `webapp/frontend/src/components/` |
| 网页 API、本地媒体服务、启动 | `webapp/server.py`、`main.py` | `business/recommendation.py` |
| 网页瀑布流、图片查看器 | `PhotoMasonry.jsx`、`PhotoLightbox.jsx` | Virtuoso Masonry / Yet Another React Lightbox 官方文档 |
| 时间线、随机漫游、疑似样片 | `webapp/frontend/src/App.jsx`、`webapp/server.py` | `business/recommendation.py` |
| 随机抽取、分类查询、去重 | `business/recommendation.py` | `business/classifier/category_rules.py` |
| 生活/样片分类 | `business/classifier/category_rules.py` | `项目文档/照片分类规则.md` |
| 成人识别与疑似样片 | `business/image_recognition/tag_generator.py`、`business/classifier/nsfw_review.py` | `infra/image/clip_encoder.py` |
| 扫描、索引、缩略图 | `business/indexer/`、`infra/image/` | `scripts/maintain_thumbnails.py` |
| 数据库与仓储 | `db_manager.py`、`infra/db/repositories/` | `项目文档/开发索引.md` |
| 项目全貌或跨模块改造 | `项目文档/开发索引.md` | 仅继续读取其中明确指向的文件 |

## 不变量

- 不删除、移动或重命名用户照片、视频和缓存。
- 不把 NAS 原图解码、重查询或模型推理放到 UI 线程。
- SQLite 写入保持短事务和集中串行；未经明确需要不改 schema / migration。
- 分类展示统一复用 `category_match_sql()`；不要在组件中复制分类优先级。
- `Photos/Moments` 默认强制生活，只有用户对单张照片确认“转样片”可以跨越。
- 保留用户已有改动；不处理 `.codex-diagnostics/`。
- 未经要求不提交、不安装依赖、不联网、不跑全量识别或全量重建。

## 工作方式

- 先定位最小入口，再读取相关实现和测试；不要为了建立上下文遍历全部文档或代码。
- 网页通用能力优先使用现有组件库：MUI、TanStack Query、Virtuoso Masonry、Yet Another React Lightbox；不要重复手写请求缓存、虚拟列表、弹窗焦点和键盘导航。
- 前端改造允许分阶段进行，但每一步都要保持可启动、可回滚，并验证滚动、切页、热启动和冷启动主链路。
- 能补小测试就补。涉及真实性能时，用小批量真实库只读验证，不把 mock 通过当成真实性能结论。
- 使用 `rg` / `rg --files` 定位；不要生成与任务无关的说明文件。

## 交付格式

- 修改文件
- 变更摘要
- 风险
- 未修改内容
- 验证命令
