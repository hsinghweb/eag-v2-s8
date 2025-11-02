"""
Helper script to set up Google OAuth credentials.
Run this once to generate token files.
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

def setup_gmail_oauth():
    """Set up Gmail OAuth credentials"""
    SCOPES = ['https://www.googleapis.com/auth/gmail.send']
    credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
    token_file = os.getenv("GMAIL_TOKEN_FILE", "gmail_token.json")
    
    if not os.path.exists(credentials_file):
        print(f"❌ Gmail credentials file not found: {credentials_file}")
        print("Please download OAuth2 credentials from Google Cloud Console")
        return False
    
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(token_file, 'w') as token:
        token.write(creds.to_json())
    
    print(f"✅ Gmail token saved to {token_file}")
    return True


def setup_sheets_drive_oauth():
    """Set up Google Sheets/Drive OAuth credentials"""
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    
    if not os.path.exists(credentials_file):
        print(f"❌ Google credentials file not found: {credentials_file}")
        print("Please download OAuth2 credentials from Google Cloud Console")
        return False
    
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(token_file, 'w') as token:
        token.write(creds.to_json())
    
    print(f"✅ Google Sheets/Drive token saved to {token_file}")
    return True


if __name__ == "__main__":
    import sys
    
    print("🔐 Google OAuth Setup")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "gmail":
            setup_gmail_oauth()
        elif sys.argv[1] == "sheets":
            setup_sheets_drive_oauth()
        else:
            print("Usage: python setup_google_oauth.py [gmail|sheets]")
    else:
        print("Setting up both Gmail and Sheets/Drive...")
        print("\n1. Gmail OAuth:")
        setup_gmail_oauth()
        print("\n2. Sheets/Drive OAuth:")
        setup_sheets_drive_oauth()
        print("\n✅ Setup complete!")

