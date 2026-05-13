from typing import Dict
from core.models import ClickHistory


class ClickHistoryRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, click: ClickHistory):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO click_history (file_id, folder_path, category, clicked_at) VALUES (?, ?, ?, ?)",
                click.as_row()
            )

    def get_folder_click_counts(self, category: int) -> Dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT folder_path, COUNT(*) as cnt FROM click_history WHERE category = ? GROUP BY folder_path", (category,)).fetchall()
        return {row[0]: row[1] for row in rows}
