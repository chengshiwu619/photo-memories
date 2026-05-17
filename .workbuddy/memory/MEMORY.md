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
- 层间调用走接口表（ARCHITECTURE.md §11）
- Config 统一走 get_settings()

## 待验证问题
- 特殊回忆初期填充逻辑（三层兜底：on_this_day→special_date→folder）需在有实际照片数据后验证效果
- 缩略图/数据库清空后重建状态待确认

## 文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| 架构文档 | `ARCHITECTURE.md`（项目根目录） | 分层架构、模块职责、数据流、接口定义、技术债、决策（权威文档） |
| 版本变更 | `changelog.md`（本目录） | 各版本做了什么 |
| 项目说明 | `README.md`（项目根目录） | 用户/开发者入门 |
