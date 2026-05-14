# 更新记录

## V0.2 (2026-05-15)

### 分类系统

- **5级优先级体系**：分支分类(5) > 内容信号(4) > EXIF(3) > 文件名(2) > 路径(1)，同级冲突时样片优先于生活
- **分支分类保护**：LLM/关键词判定的分支分类作为最高优先级信号，保护子文件夹不被低优先级信号翻转
- **LLM分类优化**：采样每个分支最多5个子路径+5个文件名作为上下文，精简prompt，返回值改用数组格式 `{"c":[1,2,0,...]}` 减少token
- **LLM返回值兼容**：处理 `deepseek-v4-flash` 返回 `[{...}]` 数组包裹的情况
- **分支自身记录**：每个分支自身写入 `folder_categories` 记录，供后台精分类的 `branch_cat_map` 使用
- **不确定分支处理**：LLM不确定的分支暂归生活（confidence=default-pending-refine），留给后台精分类用优先级体系重新判断

### 分类变更一致性修复

- **自动清理旧分类残留**：文件夹分类发生变化后，自动清理旧分类下的 `memories`、`photo_shown_history`、`click_history` 残留记录，避免旧回忆或旧历史继续展示已迁移照片
- **memories清理**：从旧分类回忆中移除变更文件夹的 photo_id，若回忆为空则删除
- **展示/点击历史清理**：批量删除旧分类下属于变更文件夹的记录

### 路径兼容性修复

- **路径正反斜杠统一**：新增 `_path_like_patterns()` 生成正反斜杠兼容的 SQL LIKE 参数，同时覆盖 `Y:\...` 和 `Y:/...`
- **路径父子判断**：新增 `_is_same_or_child_path()` 替代 `startswith(branch_path + os.sep)` 判断，统一用 `/` 归一化后比较
- 全部7处路径判断替换为兼容函数

### 关键词管理

- 新增内置样片关键词："希威社"、"色图"
- 删除误匹配的 "pixel"（EXIF中 Pixels/Inch 被误匹配），只保留 "google pixel"

### Bug修复

- **branch_cat_map 解包错误**：`for fp, cat, conf in classified_map.items()` → `for fp, (cat, conf) in classified_map.items()`
- **采样SQL漏掉分支自身文件**：增加 `WHERE (folder_path = ? OR folder_path LIKE ?)`
- **LLM分类的样片分支不被保护**：`branch_cat_map` 检查增加 `"llm" in b_conf`
- **采样SQL性能优化**：7次单独查询改为1次批量查询

### 架构文档

- ARCHITECTURE.md 更新优先级体系为5级
- 补充分类变更后历史一致性修复描述
- 补充LLM采样上下文和不确定分支处理描述
- 冲突解决规则更新为"同级时样片优先于生活"

### 清理

- 删除调试脚本 `debug_full.py`、`debug_kw.py`
- `.gitignore` 增加 `debug_*.py`、`photos_before_*.db` 规则
