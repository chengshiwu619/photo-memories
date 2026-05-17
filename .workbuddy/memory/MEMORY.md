# photo-memories 项目长期记忆

## 项目概况
- NAS 照片回忆系统，技术栈 PyQt6 + SQLite + Python
- 依赖 es.exe（Everything SDK）文件扫描，.env 管理 API 密钥
- 通过 anyaigc.com 第三方 API 访问 Claude 模型
- 当前版本 v0.3，核心 UI 为侧边栏导航（随机回忆/时间线/特殊回忆）

## 协作规范（写入 ARCHITECTURE.md 第8节）
- 架构先行，修改前先出清单确认后才执行
- 架构变更需审核确认
- 给验收标准不给步骤
- 不确定就问
- 没要求的不写
- 只改被要求的部分
- 禁止死代码入库
- 层间调用走接口表
- Config 统一走 get_settings()

## 架构关键决策
- 2026-05-16: ARCHITECTURE.md 大改，新增层间接口定义（第11节）、技术债清单（第12节）、缩略图版本复用策略（第3.11节）
- YOLOv8n(AGPL-3.0) 替换为 LibreYOLO(MIT)，基于 onnxruntime
- AI 识别任务统一使用缩略图执行
- LLM 调用边界：仅事件/旅行描述调用 LLM，其余标题模板化
- 人脸聚类命名：用户点击卡片进入详情视图后输入名称
- 特殊回忆卡片：无数量上限，前3天高频后低频，长期未点击碎裂动画
- 导航项显示：数据驱动，有数据就显示
- 回忆导出功能（PDF/视频/HTML）明确不做
- 缩略图版本复用：DB迁移阶段加入映射/拷贝/重命名策略

## 已完成技术债清理（2026-07-25）
- ✅ 删除死代码文件: data_service.py, recognition_scheduler.py, everything.py, folder_categories_repo.py, task_checkpoints_repo.py
- ✅ 保留已实现但未接线文件: event_detector.py, memory_narrator.py, memory_discovery.py（v0.3 UI接入特殊回忆Tab时需复用）
- ✅ 删除死函数: memory_generator.py 4个、memory_discovery.py 3个
- ✅ Deprecated 全局变量迁移: 所有11个deprecated变量迁移至 get_settings()，config.py 清理完毕
- ✅ db_manager.py 重复方法合并: 删除 _create_v03_new_tables_stmt，统一用 executescript 版本
- ✅ 测试文件同步更新: test_config.py, test_exif_thumbnail.py

## P0+P1 修复（2026-05-17）
- ✅ P0-1: 删除 yolov8n.pt（6.3MB PyTorch 权重残留），.gitignore 改为 `*.pt` 通配符
- ✅ P0-2: 修复 ui/app.py closeEvent 持久连接泄漏，退出时关闭 self.db
- ✅ P1-3: 删除死代码文件 event_detector.py（129行）、memory_narrator.py（68行）
- ✅ P1-4: 删除 memory_discovery.py 3个死函数（discover_person/event/scene_memories），清理未使用 import（FaceClustersRepository/FaceEmbeddingsRepository/EventsRepository）
- ✅ P1-5: ARCHITECTURE.md 同步更新（§2.3/2.4 删除已删文件行、§12.1 已删条目打✅、§12.2 重写迁移状态、§12.4 删除不存在条目、§7 依赖标✅、§5 常量改为 Settings 字段引用）
- ✅ P1-6: config.py 常量迁移（THUMBNAIL_SIZE/PHASH_THRESHOLD/MEMORY_HIGH_FREQ_DAYS → Settings 字段），调用方 photo_indexer.py/thumbnail_loader.py 改用 get_settings()，memory_discovery.py 默认参数改为 Optional，test_config.py 同步更新

## UI 改造（2026-05-17 第二轮）
- ✅ 侧边栏：三等分均分布局（addWidget stretch=1），删除 emoji 图标仅保留竖排纯文字
- ✅ 瀑布流去重+底部提示：_on_scroll 恢复 not _all_loaded 检查（v0.2 行为），append_photos 回退简单 extend（去重由 reshuffle_photos 保证），新增 footer_label 显示"已加载所有图片"，新增 reset_for_shuffle() 和 set_all_loaded() 方法
- ✅ 特殊回忆初期填充：三层兜底——① discover_special_date_memories（7个节日，降阈值到1张，不要求 thumbnail_path）② discover_folder_memories（按文件夹分组 top5）③ _load_special_memories 在条目<3时逐级补充
- ✅ 大图查看器异步加载：_LoadOriginalWorker 后台 PIL 解码+保存临时文件，信号传 temp_path 字符串（非 QPixmap），主线程回调创建 QPixmap。先显示缩略图占位再异步替换为原图
- ✅ v0.2 对比修复：_on_scroll 缺少 _all_loaded 检查导致无限触发加载、append_photos _shown_ids 去重与洗牌冲突、QPixmap 跨线程创建失败

## 待验证问题（清空缓存后需重新测试）
- SOURCE_DRIVE 配置指向项目根目录而非照片目录，首次启动扫描到0文件——需用户通过设置窗口配置正确的照片源目录
- 缩略图/数据库已清空（storage/thumbnails/ 和 photos.db 已删除），下次启动自动重建
- 特殊回忆初期填充逻辑需在有实际照片数据后验证效果

## 剩余技术债（P2 延后至 v0.4）
- config.py 存在 Core→Infra 层反转（save_config 调用 LLMClient.reset）
- UI 层直接实例化 Database 和 Repository，绕过服务层（7处）
- 业务层 raw SQL 105 处，需逐步迁移至 Repository 模式
- app.py 职责过多（739行），4个内联 QThread 类需拆分
- db_manager._ensure_missing_tables 只检查3个旧表
- 缩略图版本复用（ARCHITECTURE.md §3.11 已设计但未实现）
- config.py 模块级副作用（L114-116 import时创建目录）
