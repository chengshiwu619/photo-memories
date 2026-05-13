import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), "storage", "photos.db")
HIST = os.path.join(os.path.dirname(__file__), "storage", "classification_history.txt")
UNKNOWN = os.path.join(os.path.dirname(__file__), "unknown_folders.txt")
CKPT1 = os.path.join(os.path.dirname(__file__), "storage", "scan_checkpoint.json")
CKPT2 = os.path.join(os.path.dirname(__file__), "storage", "index_checkpoint.json")

c = sqlite3.connect(DB)
c.execute("DELETE FROM folder_categories")
c.execute("DELETE FROM memories")
c.execute("DELETE FROM click_history")
c.execute("UPDATE photo_metadata SET is_starred = 0")
c.commit()

files = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
thumbs = c.execute("SELECT COUNT(*) FROM photo_metadata WHERE thumbnail_path IS NOT NULL").fetchone()[0]
c.close()

print(f"保留: files={files}, thumbnails={thumbs}")
print("已清除: folder_categories, memories, click_history, is_starred")

for path in [HIST, UNKNOWN, CKPT1, CKPT2]:
    if os.path.exists(path):
        os.remove(path)
        print(f"  已删除: {os.path.basename(path)}")
