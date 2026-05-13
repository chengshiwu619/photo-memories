import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "PROJECT_FULL_DUMP.txt")

INCLUDE_EXTENSIONS = {
    ".py", ".bat", ".txt", ".md", ".example",
    ".json", ".toml", ".cfg", ".ini", ".yaml", ".yml",
}

SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "storage", "thumbnails", "data",
}

SKIP_FILES = {
    ".gitignore", ".env",
    "es.exe", "es.exe.old",
    "Everything64.exe", "Everything.exe",
    "PROJECT_FULL_DUMP.txt",
    "merge_to_txt.py",
    os.path.basename(OUTPUT_FILE),
}

SKIP_EXTENSIONS = {
    ".pyc", ".exe", ".dll", ".so", ".pyd",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".mp4", ".mov", ".avi", ".mkv",
    ".zip", ".tar", ".gz", ".7z",
    ".db", ".sqlite", ".sqlite3",
    ".log",
}

DECORATION_WIDTH = 80


def should_include(filepath):
    filename = os.path.basename(filepath)
    if filename in SKIP_FILES:
        return False
    ext = os.path.splitext(filename)[1].lower()
    if ext in SKIP_EXTENSIONS:
        return False
    if ext not in INCLUDE_EXTENSIONS and ext != "":
        return False
    return True


def collect_files(root):
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in sorted(filenames):
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root)
            if should_include(full):
                result.append((full, rel))
    return result


def main():
    files = collect_files(PROJECT_ROOT)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("=" * DECORATION_WIDTH + "\n")
        out.write("NAS 照片回忆 - 项目完整源码导出\n")
        out.write(f"生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write(f"文件总数: {len(files)}\n")
        out.write("=" * DECORATION_WIDTH + "\n\n")

        out.write("── 目录结构 ──\n\n")
        dirs_seen = set()
        for _, rel in files:
            d = os.path.dirname(rel)
            if d not in dirs_seen:
                dirs_seen.add(d)
                out.write(f"  {d}/\n")
        out.write("\n" + "=" * DECORATION_WIDTH + "\n\n")

        for full_path, rel_path in files:
            out.write("-" * DECORATION_WIDTH + "\n")
            out.write(f"文件: {rel_path}\n")
            out.write("-" * DECORATION_WIDTH + "\n")

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                out.write("  [二进制或非 UTF-8 文件，跳过内容]\n")
            except Exception as e:
                out.write(f"  [读取失败: {e}]\n")
            else:
                out.write(content)
                if not content.endswith("\n"):
                    out.write("\n")

            out.write("\n")

        out.write("=" * DECORATION_WIDTH + "\n")
        out.write("导出完成\n")
        out.write("=" * DECORATION_WIDTH + "\n")

    print(f"完成! 共 {len(files)} 个文件 → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
