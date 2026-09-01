#!/usr/bin/env python3
import base64
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Service account file
SERVICE_ACCOUNT_FILE = '/data/data/com.termux/files/home/storage/downloads/autocall-gang-9169ded0a679.json'

# The REAL Gmail user to impersonate (must be in your Google Workspace domain)
# If using personal Gmail, use your own email here
USER_TO_IMPERSONATE = "your-email@gmail.com"  # CHANGE THIS to your real Gmail

# Email details
TO_EMAIL = "mehtatrishala@gmail.com"
SUBJECT = "Test Email via Service Account"
BODY = """Hello Trishala,

This email was sent using a Google Service Account that is impersonating a real Gmail user.

Service Account: gang-82@autocall-gang.iam.gserviceaccount.com
Impersonating: {USER_TO_IMPERSONATE}

Best regards,
Automated System"""

def create_message(sender, to, subject, body):
    """Create a message for an email."""
    message = f"From: {sender}\nTo: {to}\nSubject: {subject}\n\n{body}"
    return {
        'raw': base64.urlsafe_b64encode(message.encode('utf-8')).decode('utf-8')
    }

def main():
    print("=" * 60)
    print("📧 Sending Email with Service Account Impersonation")
    print("=" * 60)
    
    try:
        # Load service account credentials
        print(f"📂 Loading service account...")
        
        # Create credentials with impersonation
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/gmail.send'],
            subject=USER_TO_IMPERSONATE  # Impersonate a real user
        )
        
        print(f"👤 Service Account: gang-82@autocall-gang.iam.gserviceaccount.com")
        print(f"👤 Impersonating: {USER_TO_IMPERSONATE}")
        
        # Build Gmail service
        print("🔗 Connecting to Gmail API...")
        service = build('gmail', 'v1', credentials=creds)
        
        # Create and send email
        print(f"📝 Creating email to: {TO_EMAIL}")
        message = create_message(USER_TO_IMPERSONATE, TO_EMAIL, SUBJECT, BODY)
        
        print("📤 Sending email...")
        result = service.users().messages().send(userId='me', body=message).execute()
        
        print(f"\n✅ Email sent successfully!")
        print(f"📧 Message ID: {result['id']}")
        print(f"📨 To: {TO_EMAIL}")
        print(f"📨 From: {USER_TO_IMPERSONATE}")
        print("=" * 60)
        
    except HttpError as error:
        print(f"\n❌ Gmail API Error: {error}")
        if "failedPrecondition" in str(error):
            print("\n💡 To fix this, you need to:")
            print("1. Use a REAL Gmail address for USER_TO_IMPERSONATE")
            print("2. The user must be in your Google Workspace domain (if using Workspace)")
            print("3. Or try the SMTP method with App Password (easier!)")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    main()
