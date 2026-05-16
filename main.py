import sys
import argparse

from logger_setup import logger, mark_startup, mark_ok_exit, check_previous_crash, _write_crash
from db_manager import Database
from ui.app import main as ui_main

_DEPRECATED_COMMANDS = {"scan", "classify", "index", "memories", "all"}


def run_setup():
    from config import save_config, get_settings
    s = get_settings()

    print("=== NAS 照片回忆 - 初始配置 ===\n")
    print("按回车使用当前值\n")

    src = input(f"照片库文件夹 [{s.source_drive}]: ").strip()
    if not src:
        src = s.source_drive

    data = input(f"缓存数据文件夹 [{s.photo_data_dir}]: ").strip()
    if not data:
        data = s.photo_data_dir

    api_key = input(f"DeepSeek API Key [{s.deepseek_api_key[:8]}...]: ").strip()
    if not api_key:
        api_key = s.deepseek_api_key

    save_config(src, data, api_key, s.deepseek_base_url, s.deepseek_model)
    print(f"\n配置已保存到 .env 文件")
    print(f"  照片库: {src}")
    print(f"  缓存:   {data}")
    print(f"  API:    {api_key[:8]}...")


def main():
    mark_startup()
    check_previous_crash()

    parser = argparse.ArgumentParser(description="NAS 照片回忆系统")
    parser.add_argument("command", nargs="?", default="ui",
                        choices=["scan", "classify", "index", "memories", "all", "ui", "setup"],
                        help="执行步骤 (scan/classify/index/memories/all 已废弃，请使用 ui)")
    args = parser.parse_args()
    logger.info(f"命令行参数: {args.command}")

    if args.command in _DEPRECATED_COMMANDS:
        logger.warning(f"CLI 子命令 '{args.command}' 已废弃，请通过 UI 界面操作。该命令将在下个版本移除。")

    if args.command == "setup":
        run_setup()
        mark_ok_exit()
        return

    from config import is_configured

    if args.command != "ui":
        if not is_configured():
            print("错误: 尚未配置。请先编辑 .env 文件或运行: python main.py setup")
            sys.exit(1)
        Database().init_tables()
    elif is_configured():
        Database().init_tables()

    if args.command == "scan":
        from business.scanner.fast_scan import full_scan as scan_drive
        logger.info("=== Stage: Scan start ===")
        result = scan_drive()
        logger.info(f"完成: 总计 {result['total']} 文件, 新增 {result['new']}, 移除 {result['removed']}")
    elif args.command == "classify":
        from business.classifier.folder_classifier import classify_folders
        logger.info("=== Stage: Classify start ===")
        result = classify_folders()
        logger.info(f"分类完成: 已分类 {result['classified']}, 不确定 {result['unknown']}")
    elif args.command == "index":
        from business.indexer.photo_indexer import index_photos
        logger.info("=== Stage: Index start ===")
        result = index_photos()
        logger.info(f"完成: 索引 {result['indexed']}/{result['total']}")
    elif args.command == "memories":
        from memory.memory_generator import generate_all_memories
        logger.info("=== Stage: Memories start ===")
        results = generate_all_memories()
        for r in results:
            logger.info(f"  {r['category']}: {r.get('title', '跳过')}")
    elif args.command == "all":
        from business.scanner.fast_scan import full_scan as scan_drive
        from business.classifier.folder_classifier import classify_folders
        from business.indexer.photo_indexer import index_photos
        from memory.memory_generator import generate_all_memories

        logger.info("=== Stage: Scan start ===")
        scan_drive()
        logger.info("=== Stage: Classify start ===")
        classify_folders()
        logger.info("=== Stage: Index start ===")
        index_photos()
        logger.info("=== Stage: Memories start ===")
        generate_all_memories()
        logger.info("全部完成！可以启动 UI 了。")
    elif args.command == "ui":
        ui_main()

    mark_ok_exit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        exc_type, exc_value, exc_tb = sys.exc_info()
        _write_crash(exc_type, exc_value, exc_tb, source="main")
        traceback.print_exc()
        try:
            import tkinter.messagebox as mb
            mb.showerror(
                "NAS 照片回忆 - 启动失败",
                f"程序遇到错误，详情请查看 storage/logs/crash.log\n\n{exc_value}",
            )
        except Exception:
            pass
