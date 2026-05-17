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

### 其他
- 缓存清空（storage/thumbnails/ 和 photos.db）
- Git 提交推送，创建 V0.3 release
- README 更新

## v0.2 (历史版本)
- 基础瀑布流+侧边栏+回忆发现
- 详见 GitHub tag v0.2
