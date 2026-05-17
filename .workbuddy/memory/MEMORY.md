# photo-memories 项目长期记忆

## 项目概况
- NAS 照片回忆系统，技术栈 PyQt6 + SQLite + Python
- 依赖 es.exe（Everything SDK）文件扫描，.env 管理 API 密钥
- 通过 anyaigc.com 第三方 API 访问 Claude 模型
- 当前版本 v0.3，核心 UI 为侧边栏导航（随机回忆/时间线/特殊回忆）

## 协作规范
- 架构先行，修改前先出清单确认后才执行
- 架构变更需审核确认
- 给验收标准不给步骤
- 不确定就问，别猜
- 没要求的不写，只改被要求的部分
- 禁止死代码入库
- 层间调用走接口表（ARCHITECTURE.md §10）
- Config 统一走 get_settings()

## 待验证问题
- 特殊回忆初期填充逻辑（三层兜底：on_this_day→special_date→folder）需在有实际照片数据后验证效果

## 已验证问题
- 缩略图/数据库清空后重建状态：DB 重建后 memories 表引用过期 file_id（thumbnail_path 全 NULL），导致特殊回忆栏空白。处理策略：memories 可安全删后重建（ARCHITECTURE.md §11.1）。

## v0.4 待修改项
- 版本更迭缓存清理机制：当缩略图参数（尺寸/质量）变更时，自动检测并清理旧缩略图，触发重新生成；需考虑增量重建（避免一次性全部重生成导致长时间阻塞）
- 时间线侧边索引拉球：快速定位到某个时间点
- 特殊回忆创建机制验证：地点聚合、人脸聚合等是否正确运行
- 启动时 memories/events 等表的 file_id 完整性检查（悬空引用自动清理+重建），参见 ARCHITECTURE.md §11

## 缩略图参数
- 当前：600×600，JPEG quality=90（v0.3 之前为 400×400/quality=80，已手动清理旧缓存并重置 thumbnail_path）
- 不可识别图片标记：`thumbnail_path='__FAILED__'`，所有查询均过滤 `!= '__FAILED__'`
- 编码损坏路径：`_parse_es_csv()` 和 filelist.txt 缓存读取均过滤 `\ufffd` 和 `?`（es.exe 自身将无法编码的字符替换为 ASCII `?`，Python GBK 解码后为 U+003F 而非 U+FFFD，需同时过滤两者）

## 数据库连接策略
- 后台线程（扫描/索引/去重）：禁止使用持久连接，统一用 pending_writes 缓冲 + `_db.connect()` 短事务 `executemany` 批量写入
- UI 层持久连接 `self.db`：仅用于 SELECT 只读查询，所有写操作走 `Database().connect()` 短连接
- `record_shown_photos()` 等写函数：不接收 db 参数，内部自行创建短连接
- `connect()` 和 `get_persistent_connection()` 均设置 `row_factory = sqlite3.Row`，确保查询结果可用字典语法访问

## 三栏目隔离策略
- `_current_nav` 追踪当前主栏目（random/timeline/special），`on_photo_clicked()` 根据来源取正确的分类和照片列表
- 收藏切换/重分类只调 `_reload_random()`，不影响时间线/特殊回忆；设置保存等全量重载调 `_invalidate_all_caches()` + `load_memories()`
- 时间线/特殊回忆有 `_timeline_loaded`/`_special_loaded` 缓存标记，切换不重复查询
- `_last_scroll_vals` 按页面 id 独立存储，各栏目滚动互不影响
- `_load_stack_photos()` 使用短连接，禁止持久连接泄漏

## 时间线分栏
- 仅显示已有缩略图的照片（`thumbnail_path IS NOT NULL`）
- `_timeline_refresh_timer` 每 30 秒增量刷新，后台索引完成后自动出现新照片
- `_timeline_known_ids` 追踪已加载的 file_id 集合
- 日期 header 与卡片统一在 `_render_visible()` 中管理（`_visible_headers` dict），header 有不透明背景 #111，不再与缩略图重叠

## 特殊回忆分栏
- 展开态：5 列网格布局（`GridCard`，80×80 方形缩略图），最多显示 20 张
- 手风琴模式：`collapse_others` 信号，同时只展开一个 `PokerStack`
- 展开态点击缩略图：`photo_clicked` 信号 → `_on_special_photo_clicked` → `on_photo_clicked` 打开图片查看器，**支持前后翻页**（传入该 PokerStack 完整照片列表）
- 折叠态堆叠：最多 3 张（`max_visible=3`），按 `created_at` 降序排列，**无分组 headers**
- 触发条件：生活照片 ≥200 张（`_get_life_photo_count()`）→ Phase 3 全量发现；<200 张 → Phase 1 仅文件夹回忆 `top_n=3`
- 文件夹回忆上限 `top_n=3`
- 缩略图缓存：使用自定义 `_PixmapCache`（dict 实现），不使用 PyQt6 内置 `QPixmapCache`（PyQt6 已移除字符串 key 的 find/insert API）

## 文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| 架构文档 | `ARCHITECTURE.md`（项目根目录） | 分层架构、模块职责、数据流、接口定义、技术债、决策（权威文档） |
| 版本变更 | `changelog.md`（本目录） | 各版本做了什么 |
| 项目说明 | `README.md`（项目根目录） | 用户/开发者入门 |
