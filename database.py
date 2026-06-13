import sqlite3
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repositories (
            id          TEXT PRIMARY KEY,
            url         TEXT NOT NULL,
            name        TEXT,
            framework   TEXT,
            language    TEXT,
            test_command TEXT,
            lint_command TEXT,
            summary     TEXT,
            local_path  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contributions (
            id              TEXT PRIMARY KEY,
            repo_id         TEXT,
            mode            TEXT,
            user_input      TEXT,
            status          TEXT DEFAULT 'pending',
            affected_files  TEXT,
            plan            TEXT,
            diff            TEXT,
            test_result     TEXT,
            review_score    REAL,
            review_notes    TEXT,
            branch_name     TEXT,
            pr_url          TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contribution_id TEXT,
            stage           TEXT,
            message         TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    print("Database initialised successfully.")


def log(contribution_id: str, stage: str, message: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO agent_log (contribution_id, stage, message) VALUES (?, ?, ?)",
        (contribution_id, stage, message)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()