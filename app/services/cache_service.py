import sqlite3
from datetime import datetime, timedelta  # timedelta 추가
import json
import os
import logging

class CacheService:
    def __init__(self, db_path='cache/scholar_cache.db', cache_duration_days=7):
        self.db_path = db_path
        self.cache_duration = timedelta(days=cache_duration_days)  # 이제 작동할 것입니다
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        logging.info(f"Cache database path: {self.db_path}")
        self._init_db()


    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS citations (
                        paper_id TEXT PRIMARY KEY,
                        title TEXT,
                        authors TEXT,
                        citation_count INTEGER,
                        citation_network TEXT,
                        last_updated TIMESTAMP,
                        search_count INTEGER DEFAULT 0
                    )
                ''')
                conn.commit()
        except Exception as e:
            print(f"DB initialization error: {e}")

    def get_citation(self, paper_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT citation_count, last_updated FROM citations WHERE paper_id = ?', 
                    (paper_id,)
                )
                result = cursor.fetchone()
                if result:
                    count, timestamp = result
                    last_updated = datetime.fromisoformat(timestamp)
                    if datetime.now() - last_updated < self.cache_duration:
                        return {'citation_count': count}
                return None
        except Exception as e:
            print(f"Cache retrieval error: {e}")
            return None

    def update_citation(self, paper_id, title, authors, citation_count):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO citations 
                    (paper_id, title, authors, citation_count, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    paper_id, 
                    title,
                    authors,
                    citation_count,
                    datetime.now().isoformat()
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"Cache update error: {e}")
            return False