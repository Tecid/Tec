
import psycopg2
from urllib.parse import urlparse
import os
from dotenv import load_dotenv

load_dotenv('server/.env')

# Get DB URL from env
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment!")
    exit(1)

print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")

try:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    
    print("Fixing hfm_ticket column type...")
    cur.execute("ALTER TABLE trade_history ALTER COLUMN hfm_ticket TYPE BIGINT;")
    print("DONE: hfm_ticket fixed.")
    
    print("Fixing equiti_ticket column type...")
    cur.execute("ALTER TABLE trade_history ALTER COLUMN equiti_ticket TYPE BIGINT;")
    print("DONE: equiti_ticket fixed.")
    
    cur.close()
    conn.close()
    print("\nSUCCESS: Database schema successfully patched!")

except Exception as e:
    print(f"\nFAILED to update database: {e}")
