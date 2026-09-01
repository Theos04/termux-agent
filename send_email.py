import base64
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Service account credentials file
SERVICE_ACCOUNT_FILE = '/data/data/com.termux/files/home/storage/downloads/service_account.json'

# Email details
TO_EMAIL = 'mehtatrishala@gmail.com'
FROM_EMAIL = 'your-service-account-email@your-project.iam.gserviceaccount.com'  # You'll find this in the JSON
SUBJECT = 'Test Email from Service Account'
BODY = """Hello Trishala,

This is a test email sent using the Gmail API with a service account.

Best regards,
Automated System"""

def create_message(sender, to, subject, body):
    """Create a message for an email."""
    message = f"""From: {sender}
To: {to}
Subject: {subject}

{body}"""
    return {'raw': base64.urlsafe_b64encode(message.encode('utf-8')).decode('utf-8')}

def send_email(service, user_id, message):
    """Send an email message."""
    try:
        message = service.users().messages().send(userId=user_id, body=message).execute()
        print(f"Message sent! Message ID: {message['id']}")
        return message
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def main():
    try:
        # Load credentials
        with open(SERVICE_ACCOUNT_FILE, 'r') as f:
            creds_data = json.load(f)
        
        # Get the service account email
        service_account_email = creds_data.get('client_email')
        print(f"Service Account: {service_account_email}")
        
        # Create credentials
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/gmail.send']
        )
        
        # Build the Gmail service
        service = build('gmail', 'v1', credentials=creds)
        
        # Create and send email
        message = create_message(service_account_email, TO_EMAIL, SUBJECT, BODY)
        send_email(service, 'me', message)
        
    except FileNotFoundError:
        print(f"Error: Service account file not found at {SERVICE_ACCOUNT_FILE}")
    except Exception as e:
        print(f"An error occurred: {e}")
        print("\nMake sure you've enabled the Gmail API in Google Cloud Console and added the service account to your Gmail settings.")

if __name__ == '__main__':
    main()
