#!/usr/bin/env python3
import smtplib
import json
import getpass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Load service account info
SERVICE_ACCOUNT_FILE = '/data/data/com.termux/files/home/storage/downloads/autocall-gang-9169ded0a679.json'

try:
    with open(SERVICE_ACCOUNT_FILE, 'r') as f:
        creds = json.load(f)
        service_account_email = creds.get('client_email')
except:
    service_account_email = "Not loaded"

print("=" * 60)
print("📧 Send Email via SMTP")
print("=" * 60)
print(f"📌 Service Account: {service_account_email}")
print("=" * 60)

# Get credentials interactively
YOUR_EMAIL = input("📧 Your Gmail address: ").strip()
APP_PASSWORD = getpass.getpass("🔑 App Password (16 chars): ").strip()
TO_EMAIL = input("📨 To email address: ").strip() or "mehtatrishala@gmail.com"
SUBJECT = input("📌 Subject: ").strip() or "Test from Termux"

# Create email
msg = MIMEMultipart()
msg['From'] = YOUR_EMAIL
msg['To'] = TO_EMAIL
msg['Subject'] = SUBJECT

body = f"""Hello,

This email was sent from Termux on Android.

📌 Service Account: {service_account_email}
📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📱 Sent from: Termux

Best regards,
Automated System"""

msg.attach(MIMEText(body, 'plain'))

# Send
try:
    print("\n📤 Connecting to Gmail SMTP...")
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    print("🔐 Logging in...")
    server.login(YOUR_EMAIL, APP_PASSWORD)
    print("📨 Sending...")
    server.send_message(msg)
    server.quit()
    print("\n✅ EMAIL SENT SUCCESSFULLY!")
    print(f"📧 From: {YOUR_EMAIL}")
    print(f"📨 To: {TO_EMAIL}")
except Exception as e:
    print(f"\n❌ Error: {e}")

