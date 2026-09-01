# test_google_sheets.py
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Your spreadsheet ID from the URL
SPREADSHEET_ID = '1BYBAjhZ4Z1s02qkuHnWmM5UxfFKTeGIVdlJdHU7xgm0'

# Service account file
SERVICE_ACCOUNT_FILE = 'client_secret_myagent.json'

# The scopes required for Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def test_sheets_write():
    """Test writing 'hello' to Google Sheets"""
    try:
        # 1. Load the service account credentials
        creds = None
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            print(f"✅ Loaded credentials from {SERVICE_ACCOUNT_FILE}")
        else:
            print(f"❌ Service account file not found: {SERVICE_ACCOUNT_FILE}")
            return False
        
        # 2. Build the Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        print("✅ Connected to Google Sheets API")
        
        # 3. Write "hello" to cell A1
        body = {
            'values': [
                ['hello', 'timestamp', 'from_script'],
                ['test', 'row2', 'data']
            ]
        }
        
        result = sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range='Sheet1!A1',  # Write starting at A1
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        print(f"✅ Successfully wrote 'hello' to sheet!")
        print(f"   Updated cells: {result.get('updatedCells')}")
        print(f"   Updated range: {result.get('updatedRange')}")
        return True
        
    except HttpError as err:
        print(f"❌ Google API error: {err}")
        if err.resp.status == 403:
            print("   This usually means:")
            print("   1. Domain-Wide Delegation is not enabled")
            print("   2. The service account doesn't have permission to write")
            print("   3. You need to share the sheet with the service account email")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def share_sheet_with_service_account():
    """Print instructions to share sheet with service account"""
    # Extract the service account email from the JSON file
    try:
        with open(SERVICE_ACCOUNT_FILE, 'r') as f:
            data = json.load(f)
            client_email = data.get('client_email')
            print("\n📋 IMPORTANT: Share your Google Sheet with this email:")
            print(f"   {client_email}")
            print("\n   Steps:")
            print(f"   1. Open: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
            print("   2. Click 'Share' button (top-right)")
            print(f"   3. Add '{client_email}' as Editor")
            print("   4. Click 'Send'")
    except:
        print("\n📋 Check your service account email in the JSON file")

if __name__ == "__main__":
    print("🧪 Testing Google Sheets Integration")
    print("=" * 40)
    
    # Show the service account email
    share_sheet_with_service_account()
    
    print("\n" + "=" * 40)
    print("🔄 Attempting to write to sheet...")
    
    success = test_sheets_write()
    
    if success:
        print("\n🎉 Success! Check your sheet:")
        print(f"   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    else:
        print("\n❌ Failed. Check the error above and try these fixes:")
        print("1. Share the sheet with the service account email shown above")
        print("2. If using Domain-Wide Delegation, verify it's configured")
        print("3. Check that the service account has the right permissions")
