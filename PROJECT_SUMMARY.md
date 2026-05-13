# NAS 照片回忆 — 项目摘要

## 项目目标
本地 NAS 照片"回忆/精选"应用，类似 Apple/Google Photos 回忆功能，让 NAS 存储的照片以瀑布流形式展示在桌面窗口。

## 4 条基本协作规则
1. 涉及功能问题不确定时必须主动询问，不自行猜测
2. 没有明确要求的功能不要擅自添加
3. 修改代码时只修改被要求的部分，不顺手改其他
4. 每次完成功能后给出明确的验收标准

## 技术栈
- Python + PyQt6 桌面 GUI
- SQLite 本地索引数据库 (data/photos.db)
- DeepSeek V4 Pro API (json_mode) 用于 LLM 分类和回忆生成
- Pillow 生成缩略图 (400x400 JPEG)
- exifread 提取 EXIF 元数据
- MD5 哈希去重

## 4 大照片分类
| 编号 | 名称 | 说明 |
|------|------|------|
| 1 | 生活照片 | 日常手机拍摄、自拍、随手拍 |
| 2 | 拍摄样片 | 艺人写真、模特样片、cosplay |
| 3 | 摄影照片 | 摄影作品、相机拍摄、风景街拍 |
| 4 | 色情照片 | 成人内容、色情写真 |

## 目录结构
```
D:\photo-memories\
├── config.py          # 全局配置(API密钥、路径、分类常量、数据库建表)
├── .env               # DeepSeek API密钥(gitignored)
├── main.py            # CLI入口 / 一键启动GUI
├── launch.bat         # 双击启动脚本
├── logger_setup.py    # 统一日志(logs/app.log, 5MB滚动, 3备份)
├── clean_data.py      # 数据清理脚本(运维工具)
├── scanner/
│   └── file_scanner.py     # Y盘扫描(MD5哈希, 视频跳过, 断点续扫)
├── classifier/
│   └── folder_classifier.py # LLM分类 + 分类历史TXT + 交互分类
├── indexer/
│   └── photo_indexer.py    # EXIF提取 + 缩略图生成(断点续传)
├── memory/
│   └── memory_generator.py # 回忆生成(聚焦单天/单文件夹~8-12张)
├── ui/
│   ├── app.py           # MainWindow(主界面) + 启动逻辑
│   ├── recommendation.py # 推荐策略(独立文件, 点击权重+收藏+文件夹抑制)
│   └── components/
│       ├── memory_cards.py       # PhotoCard + WaterfallLayout + CategoryPage
│       ├── image_viewer.py        # 全屏查看器(左右大按钮+底部按钮栏)
│       ├── startup_window.py      # 一键启动窗口(4阶段进度)
│       └── folder_classifier_dialog.py # 交互分类弹窗(样品图+不清楚按钮)
└── data/
    ├── photos.db        # SQLite数据库
    ├── thumbnails/      # 缩略图目录
    ├── classification_history.txt # LLM分类历史参考
    ├── scan_checkpoint.json       # 扫描断点
    └── index_checkpoint.json      # 索引断点
```

## 数据库表
| 表名 | 用途 |
|------|------|
| files | 文件索引(路径、名称、大小、哈希) |
| folder_categories | 文件夹分类 |
| photo_metadata | 照片元数据(EXIF、缩略图、is_starred) |
| memories | 回忆记录(标题、描述、照片ID列表) |
| click_history | 点击记录(用于推荐权重) |
| photo_tags | 用户标签 |

## 启动流程(一键)
1. 扫描D:\测试 → 2. LLM分类文件夹 → 3. 生成缩略图 → 4. 生成回忆 → 跳转主界面

## 主界面
- 顶部栏：标题 | [搜索标签...] | [标签] | [优秀回忆]
- 导航栏：生活照片 | 拍摄样片 | 摄影照片 | 色情照片
- 瀑布流卡片区域(4-6列, 1px间距, 横屏照片占2列)
- 滚轮向下：顶栏+导航栏自动隐藏；回滚恢复
- F键全屏切换
- 每轮只显示1条回忆标题(滚动即隐藏)

## 全屏查看器
- 纯黑背景, 图片撑满窗口
- 左右 64px 大圆按钮翻页(同文件夹内)
- 右下按钮：☆收藏 | 分类 | 打开 | 标签
- 点击图片区域关闭
- ←→方向键导航, ESC退出

## 标签系统
- 全屏查看器中点"标签"→输入文字
- 存储到 photo_tags 表
- 搜索栏输入文字→回车→LLM语义匹配标签→弹出搜索窗(瀑布流显示)

## 推荐策略(ui/recommendation.py)
- 同文件夹点击次数 × 0.05 (上限0.35) 加权重
- 已收藏照片额外 +0.15
- 收藏照片最多展示3张，其余正常随机穿插
- 同一文件夹浏览≥20张后自动抑制

## 回忆生成策略
- 优先找同一天或同一文件夹的照片
- 每组5-12张，聚焦到一个注意点上
- 标题6-8字，描述30-80字

## LLM 调用
- 模型: deepseek-v4-pro (环境变量 DEEPSEEK_MODEL)
- 分类和回忆均使用 response_format={"type": "json_object"}
- 分类时附带 classification_history.txt 历史参考

## 已知问题
- HEIC 格式需 pillow-heif 库支持（已添加）
- 超大分辨率图片已通过 `Image.MAX_IMAGE_PIXELS = None` 绕过 decompression bomb 保护

## 源目录
- 测试用: D:\测试 (config.py SOURCE_DRIVE)
- 正式用: Y: (需改回)

## 下次启动
```bash
cd D:\photo-memories
python clean_data.py   # 可选：清除分类/回忆/点击记录
python main.py         # 一键启动
```
