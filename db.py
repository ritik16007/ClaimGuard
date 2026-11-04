from __future__ import annotations
import hashlib, os, sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent
def connect(path):
    conn=sqlite3.connect(path, timeout=15)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db(path, policy_dir=None, build_index=True):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    conn=connect(path)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('employee','authority')), password_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, stored_name TEXT NOT NULL, original_name TEXT NOT NULL, mime_type TEXT NOT NULL, extracted_text TEXT NOT NULL DEFAULT '', extraction_status TEXT NOT NULL DEFAULT 'uncertain', uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS claims(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES users(id), receipt_id INTEGER REFERENCES receipts(id), category TEXT NOT NULL, expense_date TEXT NOT NULL, amount REAL, merchant TEXT NOT NULL DEFAULT '', business_purpose TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, risk TEXT NOT NULL, reason TEXT NOT NULL, duplicate_of INTEGER REFERENCES claims(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT, payment_confirmed_by INTEGER REFERENCES users(id), payment_confirmed_at TEXT);
    CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), claim_id INTEGER REFERENCES claims(id), action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS policy_vectors(id INTEGER PRIMARY KEY, document TEXT NOT NULL, page INTEGER NOT NULL, heading TEXT NOT NULL, content TEXT NOT NULL, embedding BLOB NOT NULL, UNIQUE(document,page));
    CREATE INDEX IF NOT EXISTS claims_status_idx ON claims(status);
    CREATE INDEX IF NOT EXISTS claims_employee_idx ON claims(employee_id);
    """)
    users=[("asha","Asha Employee","employee","ClaimGuard123!"),("morgan","Morgan Authority","authority","Authority123!")]
    for username,name,role,password in users:
        conn.execute("INSERT OR IGNORE INTO users(username,full_name,role,password_hash) VALUES(?,?,?,?)",(username,name,role,generate_password_hash(password)))
    from rag import index_policies,write_policy_pdfs
    if build_index:index_policies(conn)
    if policy_dir:
        from policy_content import write_sources
        write_sources(Path(policy_dir)); write_policy_pdfs(Path(policy_dir))
    conn.commit(); conn.close()

