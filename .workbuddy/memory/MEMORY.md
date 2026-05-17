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

## UI 改造（2026-07-26）
- ✅ 无限滚动：virtual_waterfall.py 移除 `_all_loaded` 阻断条件，append_photos 重置 `_all_loaded=False`，超3000张裁剪前半防膨胀
- ✅ 循环洗牌：recommendation.py 新增 `reshuffle_photos(photos, shown_ids)` — 已显示照片降权排后
- ✅ app.py 整合：`_cat_shown_ids` 字典跟踪已显示照片ID，`_on_load_more` 在全部加载后触发洗牌续滚
- ✅ 侧边栏竖排：sidebar.py 导航项改为 `\n` 竖排文字+emoji（💡回忆/📅时间线/✨特殊回忆），按钮高度36→72px
- ✅ 特殊回忆扑克堆叠：special_memories.py 全重写，StackedCard(80x100) + PokerStack(折叠30px重叠/展开86px间距) + SpecialMemoriesView(按类型分组)
- 未提交git

## 剩余技术债
- config.py 存在 Core→Infra 层反转（save_config 调用 LLMClient.reset）
- UI 层直接实例化 Database 和 Repository，绕过服务层
- requirements.txt 缺少 open-clip-torch 和 deepface
