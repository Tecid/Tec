import sys
import os

# Add 'server' to path so we can import database models
sys.path.append(os.path.join(os.getcwd(), 'server'))

try:
    from database import get_db, UserSettings, close_db
except ImportError:
    print("Error: Could not import database module. Make sure you are running this from the project root folder.")
    sys.exit(1)

def enable_clicker():
    print("Connecting to database...")
    db = get_db()
    try:
        # Get the first user's settings (assuming single-user local setup)
        settings = db.query(UserSettings).first()
        
        if not settings:
            print("❌ No settings found!")
            print("Please run the Dashboard (start.bat) and create an account/save settings first.")
            return
        
        print(f"Found settings for User ID: {settings.user_id}")
        print(f"Current Mode: {settings.trade_mode}")
        
        # Update to CLICK mode
        settings.trade_mode = 'CLICK'
        db.commit()
        
        print("✅ SUCCESS: Trade Mode updated to 'CLICK'.")
        print("The bot will now use physical mouse clicks on the One-Click Trading panel.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        close_db(db)

if __name__ == "__main__":
    enable_clicker()
