import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'flowaccount.db')

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(document_item)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'details' not in columns:
            print("Adding 'details' column to document_item table...")
            cursor.execute("ALTER TABLE document_item ADD COLUMN details TEXT DEFAULT ''")
            conn.commit()
            print("Migration successful: 'details' column added.")
        else:
            print("'details' column already exists.")
            
        # Check company table for signature_path
        cursor.execute("PRAGMA table_info(company)")
        company_columns = [info[1] for info in cursor.fetchall()]

        if 'signature_path' not in company_columns:
            print("Adding 'signature_path' column to company table...")
            cursor.execute("ALTER TABLE company ADD COLUMN signature_path TEXT DEFAULT ''")
            conn.commit()
            print("Migration successful: 'signature_path' column added.")
        else:
            print("'signature_path' column already exists.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
