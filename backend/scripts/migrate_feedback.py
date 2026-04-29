"""Add feedback column to messages table."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.core.database import engine

with engine.connect() as conn:
    # Check if column already exists
    result = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='messages' AND column_name='feedback'"
    ))
    if result.fetchone():
        print("✅ Column 'feedback' already exists")
    else:
        conn.execute(text("ALTER TABLE messages ADD COLUMN feedback VARCHAR(10)"))
        conn.commit()
        print("✅ Added 'feedback' column to messages table")
