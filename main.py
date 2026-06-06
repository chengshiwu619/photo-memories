import argparse
import sys

from logger_setup import logger, mark_startup, mark_ok_exit, check_previous_crash, _write_crash
from db_manager import Database
from ui.app import main as ui_main


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
                        choices=["ui", "setup"],
                        help="执行步骤: ui 或 setup")
    args = parser.parse_args()
    logger.info(f"命令行参数: {args.command}")

    if args.command == "setup":
        run_setup()
        mark_ok_exit()
        return

    from config import is_configured

    if is_configured():
        Database().init_tables()

    if args.command == "ui":
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
