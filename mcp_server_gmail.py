"""
MCP Server for Gmail (Stdio Transport)
Provides tools to send emails via Gmail API.
"""

from mcp.server.fastmcp import FastMCP
import sys
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from models import SendEmailInput, SendEmailOutput

load_dotenv()

mcp = FastMCP("Gmail")

# Gmail API Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Global service object
gmail_service = None


def get_gmail_credentials():
    """Get or refresh Gmail API credentials"""
    creds = None
    token_file = os.getenv("GMAIL_TOKEN_FILE", "gmail_token.json")
    credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
    
    # Load existing token
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {credentials_file}\n"
                    "Please download OAuth2 credentials from Google Cloud Console"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    
    return creds


def get_gmail_account_email():
    """Get the email address associated with the Gmail account"""
    try:
        token_file = os.getenv("GMAIL_TOKEN_FILE", "gmail_token.json")
        if os.path.exists(token_file):
            import json
            with open(token_file, 'r') as f:
                token_data = json.load(f)
                return token_data.get("account", "")
    except:
        pass
    return ""

def initialize_gmail_service():
    """Initialize Gmail service on first use"""
    global gmail_service
    if gmail_service is None:
        try:
            creds = get_gmail_credentials()
            gmail_service = build('gmail', 'v1', credentials=creds)
            # Try to get profile to get email
            try:
                profile = gmail_service.users().getProfile(userId='me').execute()
                email = profile.get('emailAddress', '')
                if email:
                    print(f"✅ Gmail service initialized for: {email}", file=sys.stderr)
                    # Save email to token file
                    token_file = os.getenv("GMAIL_TOKEN_FILE", "gmail_token.json")
                    if os.path.exists(token_file):
                        import json
                        with open(token_file, 'r') as f:
                            token_data = json.load(f)
                        token_data['account'] = email
                        with open(token_file, 'w') as f:
                            json.dump(token_data, f)
            except:
                print("✅ Gmail service initialized", file=sys.stderr)
        except Exception as e:
            print(f"❌ Failed to initialize Gmail service: {e}", file=sys.stderr)
            raise


def create_message(to: str, subject: str, body: str, link: str = None) -> dict:
    """Create a message for sending via Gmail API"""
    message = MIMEMultipart()
    message['to'] = to
    message['subject'] = subject
    
    # Add link to body if provided
    if link:
        html_body = f"""
        <html>
          <body>
            <p>{body}</p>
            <p><a href="{link}" target="_blank">Click here to open: {link}</a></p>
          </body>
        </html>
        """
        message.attach(MIMEText(html_body, 'html'))
    else:
        message.attach(MIMEText(body, 'plain'))
    
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw_message}


def get_user_email():
    """Helper to get user's Gmail email address from .env or OAuth token"""
    # First try to get from .env
    email_from_env = os.getenv("GMAIL_USER_EMAIL", "").strip()
    if email_from_env:
        return email_from_env
    
    # Fallback to OAuth account email
    initialize_gmail_service()
    email = get_gmail_account_email()
    if not email:
        try:
            profile = gmail_service.users().getProfile(userId='me').execute()
            email = profile.get('emailAddress', '')
        except:
            pass
    return email

@mcp.tool()
def send_email(input: SendEmailInput) -> SendEmailOutput:
    """
    Send an email via Gmail.
    Usage: send_email|input.to="user@example.com"|input.subject="F1 Standings"|input.body="Here is the sheet"|input.link="https://docs.google.com/spreadsheets/d/..."
    """
    try:
        initialize_gmail_service()
        
        # Handle both nested input and direct args
        if isinstance(input, dict):
            to = input.get("to")
            subject = input.get("subject")
            body = input.get("body")
            link = input.get("link")
        else:
            to = input.to
            subject = input.subject
            body = input.body
            link = input.link
        
        message = create_message(to, subject, body, link)
        
        sent_message = gmail_service.users().messages().send(
            userId='me',
            body=message
        ).execute()
        
        message_id = sent_message.get('id')
        
        print(f"✅ Email sent to {to}", file=sys.stderr)
        
        return SendEmailOutput(
            message_id=message_id,
            success=True
        )
    except HttpError as error:
        error_msg = f"Gmail API error: {error}"
        print(f"❌ {error_msg}", file=sys.stderr)
        return SendEmailOutput(
            message_id="",
            success=False
        )
    except Exception as e:
        error_msg = f"Failed to send email: {e}"
        print(f"❌ {error_msg}", file=sys.stderr)
        return SendEmailOutput(
            message_id="",
            success=False
        )


@mcp.tool()
def send_email_with_link(to: str, subject: str, body: str, sheet_link: str) -> SendEmailOutput:
    """
    Send an email with a Google Sheet link.
    Usage: send_email_with_link|to="user@example.com"|subject="F1 Standings"|body="Here is your F1 standings sheet"|sheet_link="https://docs.google.com/spreadsheets/d/..."
    
    Note: If 'to' parameter is not provided or is "me", will use the authenticated Gmail account.
    """
    # If 'to' is "me" or not provided, try to get from .env or credentials
    if not to or to.lower() in ["me", "", "self", "yourself", "<your_gmail_address>", "<your_email>", "<gmail_user_email_from_env>"]:
        # First try .env file
        email_from_env = os.getenv("GMAIL_USER_EMAIL", "").strip()
        if email_from_env:
            to = email_from_env
            print(f"Using Gmail email from .env: {to}", file=sys.stderr)
        else:
            # Fallback to OAuth account email
            initialize_gmail_service()
            email = get_user_email()  # This already checks .env first
            if email:
                to = email
                print(f"Using Gmail account email: {to}", file=sys.stderr)
    
    # If still no email, return error
    if not to or to.lower() in ["me", "self", "yourself"]:
        return SendEmailOutput(
            message_id="",
            success=False
        )
    
    return send_email(SendEmailInput(to=to, subject=subject, body=body, link=sheet_link))


if __name__ == "__main__":
    print("mcp_server_gmail.py starting")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")
        print("\nShutting down...")

