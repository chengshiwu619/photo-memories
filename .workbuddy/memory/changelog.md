# 版本变更记录

## v0.4.1 (2026-05-17)

### Bug 修复
- **堆叠态限定 6 张**：`special_memories.py/_layout_collapsed()` 固定 `max_visible = min(len(photos), 6)`
- **特殊回忆仅用生活照片**：所有 discover 函数在创建 memories 前通过 `_filter_life_photos()` 过滤为 `category=1` 的照片，写法为 `Memory(category=1)`
- **随机回忆跨分类漏洞修复**：`recommendation.py/rank_category_photos()` 从 memories 表加载照片后，通过 JOIN folder_categories 交叉验证每张照片是否确实属于目标分类，防止脏数据泄漏
- **DB 清理**：删除 3 条 `category=1` 但含样片照片的脏 event memory（希威社文件夹），session id=17,19,21

### 架构改进
- **人脸嵌入聚类后台接入**：`face_cluster.py` 新增 `recluster_all()` 函数；`app.py` 新增 `BgTagsWorker`（SigLIP 标签生成）+ `BgFaceWorker`（人脸嵌入+聚类）；后台索引完成后自动编排启动
- **特殊回忆三阶段触发机制**：`app.py` 新增 `_get_index_progress()`，<30% 仅文件夹回忆，30-70% 增加日期+近期回忆，>70% 全量
- **跨分类聚合防御**：移除 `_get_majority_category()`，改为统一 `_filter_life_photos()` 硬过滤 + 运行时交叉验证双重保护

### 代码清理
- 删除 `overview.md`（内容已并入 changelog）
- 删除所有 `__pycache__` 目录及 `.pyc` 文件

---

## v0.3 (2026-05-17)

### 时间线拉球跳动修复 (2026-05-17)
- Bug：拉球拖动时每个 mouseMoveEvent 都触发 `_render_visible()`，高频创建/销毁 widget 导致画面跳动
- Bug：释放时 `year_selected → _scroll_to_year` 跳到年初位置，与拖动最终停留位置不一致
- 修复：
  - 拖动时 `_render_visible` 改为 30ms 防抖渲染（`_render_debounce`），降低 widget 操作频率
  - 释放时不跳年份：删除 `year_selected` 发射，改为 `drag_ended` 信号立即触发一次最终渲染
  - 新增 `_YearIndex.drag_ended` 信号，`TimelineView._on_year_drag_ended()` 停止防抖并执行最终渲染
- 修改文件：`ui/components/timeline_view.py`

### 时间线拉球年月指示器定位修复 (2026-05-17)
- Bug：`_YearIndex._show_indicator()` 中 `self.mapToGlobal(self.pos())` 坐标计算错误（pos 重复加倍偏移），且 indicator 的 parent 为 MainWindow 但 move 用了全局屏幕坐标，导致年月标签跑出可视区域
- 修复：改用 `self.mapTo(self.window(), QPoint(0, ball_y))` 正确映射到窗口坐标系，指示器紧贴拉球左侧垂直居中
- 补 import QPoint
- 修改文件：`ui/components/timeline_view.py`

### 批量修改：随机回忆去重 + 时间线增强 + 特殊回忆修复 (2026-05-17)
- **随机回忆不重复**：`reshuffle_photos()` 改为返回 fresh + stale 合并列表；`_on_load_more()` 洗牌后不再清空 `_cat_shown_ids`，同次会话照片不重复出现
- **缩略图过滤**：`load_photos_from_ids()`/`load_category_photos_batch()`/`load_starred_photos()` 增加 `os.path.exists(thumbnail_path)` 检查；瀑布流渲染时跳过缩略图文件不存在的卡片
- **时间线拉球增强**：改为月粒度 `(year, month, count)` 数据；悬停显示「2026年5月」浮层指示器；拖动时连续滚动（新增 `scroll_continuous` 信号）；回到最新按钮（右下角「△」浮动按钮）
- **优秀回忆按钮统一**：`toggle_starred()` 根据当前视图切换；时间线支持 `AND pm.is_starred = 1` 过滤
- **时间线性能**：`_timeline_refresh_timer` 只在时间线可见时运行，切出时 stop()
- **Bug 修复**：`_PhotoCard` 构造使用 `"id"` key 而非 `"file_id"`（之前所有时间线点击报 file_id=0）；PokerStack 顶部 margin 8→2，卡片 y 偏移 6→0
- **特殊回忆三阶段触发**：新增 `_get_index_progress()`；<30% 仅文件夹，30-70% 文件夹+那年今日+近期，>70% 全量
- **缓存目录迁移**：`storage/` → `D:\photo-memories-cache`；`thumbnail_path` 数据库路径批量更新（13410 条）
- **修改文件**：`ui/app.py`、`ui/recommendation.py`、`ui/components/timeline_view.py`、`ui/components/special_memories.py`、`ui/components/virtual_waterfall.py`、`config.py`、`.env`

### P0+P1 修复
- P0-1: 删除 yolov8n.pt（6.3MB PyTorch 权重残留），.gitignore 改为 `*.pt` 通配符
- P0-2: 修复 ui/app.py closeEvent 持久连接泄漏，退出时关闭 self.db
- P1-3: 删除死代码文件 event_detector.py（129行）、memory_narrator.py（68行）
- P1-4: 删除 memory_discovery.py 3个死函数（discover_person/event/scene_memories），清理未使用 import
- P1-5: ARCHITECTURE.md 同步更新（§2.3/2.4 删除已删文件行、§12.1 已删条目打✅、§12.2 重写迁移状态、§5 常量改为 Settings 字段引用）
- P1-6: config.py 常量迁移（THUMBNAIL_SIZE/PHASH_THRESHOLD/MEMORY_HIGH_FREQ_DAYS → Settings 字段），调用方改用 get_settings()，test_config.py 同步更新

### 技术债清理（三阶段）
- Phase 1: 删除 7 个死代码文件（data_service.py, recognition_scheduler.py, everything.py, folder_categories_repo.py, task_checkpoints_repo.py, event_detector.py, memory_narrator.py）
- Phase 2: 11 个 deprecated 全局变量迁移至 get_settings()，涉及 10 个文件
- Phase 3: db_manager.py 重复方法合并，删除 _create_v03_new_tables_stmt
- 总变更: 21 文件, +324/-721 行（净减 397 行）

### UI 改造
- 侧边栏：三等分均分布局（addWidget stretch=1），删除 emoji 仅保留竖排纯文字
- 瀑布流：_on_scroll 恢复 not _all_loaded 检查，append_photos 回退简单 extend，新增 footer_label + set_all_loaded() + reset_for_shuffle()
- 特殊回忆初期填充：三层兜底——on_this_day → special_date → folder
- 大图查看器异步加载：_LoadOriginalWorker 后台 PIL 解码→临时文件→主线程 QPixmap
- special_memories.py 新增 special_date 和 folder 类型标签和颜色
- reshuffle_photos 改为 fresh 优先、fresh 为空才取 stale

### v0.2 对比修复3个根因 bug
1. _on_scroll 缺少 not _all_loaded 检查 → 恢复 v0.2 行为
2. append_photos 的 _shown_ids 去重与洗牌冲突 → 回退简单 extend
3. QPixmap 跨线程创建失败 → 改为传 temp_path 字符串，主线程创建

### NAS 网盘映射扫描修复
- 修复 Everything 返回路径与 source_dirs 配置不匹配（盘符↔UNC↔IP 双向映射+规范化）
- 新增 _get_drive_mappings()、_resolve_unc_host()、_expand_source_dir_prefixes()、_normalize_filepath()
- 修改 _match_source_dir()、_parse_es_csv()、fast_scan() 过滤逻辑
- 修复 es.exe 输出编码 UTF-8→GBK
- 修复 config.py source_dirs 属性自动修复 dotenv 吞反斜杠
- 修复 .env SOURCE_DRIVE 配置
- 验证结果：296,475 条 → 68,175 个媒体文件（之前为 0）

### 数据库写锁冲突修复
- 根因：后台线程（扫描/索引）持久连接长时间持有写锁，与主线程写操作冲突
- photo_indexer.py：index_photos() 拆分为 _index_single_photo()（纯 I/O）+ pending_writes 缓冲 + _db.connect() 短事务 executemany 批量写入；dedup_by_phash() 同样改为批量短事务
- fast_scan.py：full_scan() 移除持久连接，改为 pending_writes 缓冲 + _db.connect() 短事务批量写入；_cleanup_removed_source_dirs() 移除 conn 参数改用短连接
- recommendation.py：record_shown_photos() 移除 db 参数，改用 Database().connect() 短连接 + executemany 批量写入
- app.py：record_shown_photos 调用去掉 self.db 参数；self.db 持久连接仅用于 SELECT 只读查询

### 编码损坏路径过滤
- fast_scan.py：_parse_es_csv() 跳过含 \ufffd 替换字符的文件路径，避免 os.stat() 重复报错和 filelist.txt 缓存污染

### 三栏目隔离保护
- app.py：新增 _current_nav 追踪当前主栏目（random/timeline/special），on_photo_clicked() 根据来源栏目取正确的分类和照片列表，时间线/特殊回忆点击不再误用随机回忆的分类
- app.py：load_memories() 拆分，收藏切换/重分类只调 _reload_random() 重载随机回忆栏，不影响时间线/特殊回忆；设置保存等全量重载场景调 _invalidate_all_caches() + load_memories()
- app.py：_last_scroll_val 改为 _last_scroll_vals（按页面 id 独立存储），各栏目滚动互不影响顶栏显隐
- app.py：时间线/特殊回忆增加 _timeline_loaded/_special_loaded 缓存标记，切换栏目时不重复查询
- special_memories.py：_load_stack_photos() 改用 Database().connect() 短连接，修复每个 PokerStack 泄漏一个持久连接的问题

### 时间线分栏优化
- 时间线查询已有 thumbnail_path IS NOT NULL 过滤（确认无需修改）
- app.py：新增 _timeline_refresh_timer（30秒间隔），增量刷新新索引完成的照片，无需手动切换

### 特殊回忆分栏优化
- special_memories.py：新增 GridCard 组件（方形缩略图），展开态改为5列网格布局
- special_memories.py：PokerStack 新增 photo_clicked/collapse_others 信号，实现手风琴模式（同时只展开一个回忆堆叠）
- special_memories.py：展开态点击缩略图通过 photo_clicked 信号 → app.py _on_special_photo_clicked → on_photo_clicked 打开图片查看器
- app.py：discover_folder_memories top_n 从 5 降为 2，减少文件夹回忆

### 时间线黑屏修复 + 缩略图增强
- timeline_view.py：_PhotoCard 缺少 QLabel 子控件导致 load_thumbnail 无法显示 → 添加 self._thumb QLabel，直接 setPixmap
- config.py：thumbnail_size 从 (400,400) 提升到 (600,600)
- photo_indexer.py：JPEG quality 从 80 提升到 90
- 手动清理：删除 1021 个旧缩略图、filelist.txt、5 个文件夹回忆记录，重置 photo_metadata.thumbnail_path 为 NULL（下次索引自动按新参数重新生成）

### 编码损坏路径 + 不可识别图片修复
- fast_scan.py：filelist.txt 缓存读取增加 \ufffd 过滤，防止损坏路径从缓存进入扫描
- photo_indexer.py：_index_single_photo 新增 Image.open 预检，无法识别的图片标记 thumbnail_path='__FAILED__'，避免重复尝试
- 全局：所有 thumbnail_path IS NOT NULL 查询增加 AND thumbnail_path != '__FAILED__' 过滤（10 处）
- 手动清理：删除 211 个缩略图、filelist.txt、5 个回忆、4 条点击历史、390 条展示历史、2 个断点、1 条迁移日志，重置 1220 张照片的 thumbnail_path

### row_factory + LLM 分类修复
- db_manager.py：connect() 添加 conn.row_factory = sqlite3.Row，修复短连接查询返回 tuple 导致 _make_photo_dict(r) 用 r["id"] 访问报错（特殊回忆卡片堆叠不出现）
- folder_classifier.py：LLM 分类增加 parsed 类型保护，非 dict 类型（如 int）时跳过当次尝试，避免 'int' object has no attribute 'get'

### 特殊回忆交互修复 + 侧边栏标签
- special_memories.py：StackedCard 添加 mousePressEvent，点击折叠态卡片发射 clicked 信号触发展开
- special_memories.py：_layout_collapsed() 创建 StackedCard 后调用 load_thumbnail()，修复折叠态缩略图不显示
- sidebar.py：第一栏标签从"回忆"改回"随机回忆"
- background_task_manager.py：IndexStage 跳过检查 SQL 修复 pm.thumbnail_path → thumbnail_path（去掉不存在的表别名），>=100 缩略图跳过逻辑生效

### 时间线 header 位置 + 特殊回忆缩略图黑色修复
- timeline_view.py：日期 header 从独立 _draw_headers() 合并到 _render_visible() 统一管理（_visible_headers dict），header 设不透明背景 #111 + setFixedHeight，解决时间标签与缩略图重叠
- timeline_view.py：删除 _draw_headers() 方法，_clear_all() 同步清理 _visible_headers
- special_memories.py：替换 PyQt6 内置 QPixmapCache 为自定义 _PixmapCache（dict 实现），PyQt6 已移除字符串 key 的 find/insert API 导致缩略图无法缓存和加载

### 其他
- 缓存清空（storage/thumbnails/ 和 photos.db）
- Git 提交推送，创建 V0.3 release
- README 更新

## v0.2 (历史版本)
- 基础瀑布流+侧边栏+回忆发现
- 详见 GitHub tag v0.2
