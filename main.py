import sys
import argparse

from logger_setup import logger
from db_manager import Database
from scanner.fast_scan import full_scan as scan_drive
from classifier.folder_classifier import classify_folders
from indexer.photo_indexer import index_photos
from memory.memory_generator import generate_all_memories
from ui.app import main as ui_main


def run_setup():
    from config import save_config, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, SOURCE_DRIVE, DATA_DIR, DEEPSEEK_API_KEY

    print("=== NAS 照片回忆 - 初始配置 ===\n")
    print("按回车使用当前值\n")

    src = input(f"照片库文件夹 [{SOURCE_DRIVE}]: ").strip()
    if not src:
        src = SOURCE_DRIVE

    data = input(f"缓存数据文件夹 [{DATA_DIR}]: ").strip()
    if not data:
        data = DATA_DIR

    api_key = input(f"DeepSeek API Key [{DEEPSEEK_API_KEY[:8]}...]: ").strip()
    if not api_key:
        api_key = DEEPSEEK_API_KEY

    save_config(src, data, api_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL)
    print(f"\n配置已保存到 .env 文件")
    print(f"  照片库: {src}")
    print(f"  缓存:   {data}")
    print(f"  API:    {api_key[:8]}...")


def run_scan():
    logger.info("扫描 Y 盘照片文件...")
    result = scan_drive()
    logger.info(f"完成: 总计 {result['total']} 文件, 新增 {result['new']}, 移除 {result['removed']}")
    return result


def run_classify():
    logger.info("LLM 文件夹分类中...")
    result = classify_folders()
    logger.info(f"分类完成: 已分类 {result['classified']}, 不确定 {result['unknown']}")
    return result


def run_index():
    logger.info("提取 EXIF 并生成缩略图...")
    result = index_photos()
    logger.info(f"完成: 索引 {result['indexed']}/{result['total']}")
    return result


def run_memories():
    logger.info("生成回忆...")
    results = generate_all_memories()
    for r in results:
        logger.info(f"  {r['category']}: {r.get('title', '跳过')}")
    return results


def run_all():
    run_scan()
    run_classify()
    run_index()
    run_memories()
    logger.info("全部完成！可以启动 UI 了。")


def main():
    parser = argparse.ArgumentParser(description="NAS 照片回忆系统")
    parser.add_argument("command", nargs="?", default="ui",
                        choices=["scan", "classify", "index", "memories", "all", "ui", "setup"],
                        help="执行步骤")
    args = parser.parse_args()
    logger.info(f"命令行参数: {args.command}")

    if args.command == "setup":
        run_setup()
        return

    from config import is_configured
    if not is_configured():
        print("错误: 尚未配置。请先编辑 .env 文件或运行: python main.py setup")
        print(f"  SOURCE_DRIVE=照片库路径")
        print(f"  PHOTO_DATA_DIR=缓存数据路径")
        print(f"  DEEPSEEK_API_KEY=sk-...")
        sys.exit(1)

    Database().init_tables()

    if args.command == "scan":
        run_scan()
    elif args.command == "classify":
        run_classify()
    elif args.command == "index":
        run_index()
    elif args.command == "memories":
        run_memories()
    elif args.command == "all":
        run_all()
    elif args.command == "ui":
        ui_main()


if __name__ == "__main__":
    main()
