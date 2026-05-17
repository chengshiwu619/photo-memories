# 版本变更记录

## v0.3 (2026-05-17)

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
