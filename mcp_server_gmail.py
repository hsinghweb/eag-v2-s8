"""
MCP Server for Gmail (Stdio Transport)
Provides tools to send emails via Gmail SMTP.
"""

from mcp.server.fastmcp import FastMCP
import sys
import os
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

from models import SendEmailInput, SendEmailOutput

load_dotenv()

mcp = FastMCP("Gmail")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def mcp_log(level: str, message: str) -> None:
    """Log to stderr for MCP server"""
    sys.stderr.write(f"{level}: {message}\n")
    sys.stderr.flush()


def send_email_via_smtp(to: str, subject: str, body: str, link: str = None) -> dict:
    """
    Send an email via Gmail SMTP using app password.
    Uses fixed sender (GMAIL_ADDRESS) and recipient (RECIPIENT_EMAIL) from .env
    """
    try:
        # Retrieve Gmail credentials and recipient from .env
        gmail_address = os.getenv("GMAIL_ADDRESS")
        gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
        recipient_email = os.getenv("RECIPIENT_EMAIL")
        
        if not all([gmail_address, gmail_app_password, recipient_email]):
            error_msg = "Missing GMAIL_ADDRESS, GMAIL_APP_PASSWORD, or RECIPIENT_EMAIL in .env file"
            mcp_log("ERROR", error_msg)
            return {
                "message_id": "",
                "success": False,
                "error": error_msg
            }
        
        # Validate Gmail address and recipient email format
        if not (gmail_address.endswith('@gmail.com') and '@' in recipient_email):
            error_msg = f"Invalid email format: GMAIL_ADDRESS={gmail_address}, RECIPIENT_EMAIL={recipient_email}"
            mcp_log("ERROR", error_msg)
            return {
                "message_id": "",
                "success": False,
                "error": error_msg
            }
        
        # Use RECIPIENT_EMAIL from .env (ignore 'to' parameter)
        actual_recipient = recipient_email
        
        # Create the email message
        if link:
            # Create HTML email with link
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = gmail_address
            msg['To'] = actual_recipient
            
            html_body = f"""
            <html>
              <body>
                <p>{body}</p>
                <p><strong>Google Sheet Link:</strong></p>
                <p><a href="{link}" target="_blank" style="color: #1a73e8; text-decoration: none; font-size: 16px; font-weight: bold;">{link}</a></p>
                <p><em>Click the link above to open the Google Sheet in your browser.</em></p>
              </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))
        else:
            # Plain text email
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = gmail_address
            msg['To'] = actual_recipient
        
        # Connect to Gmail's SMTP server
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                mcp_log("INFO", "Connecting to Gmail SMTP server (smtp.gmail.com:465)")
                server.login(gmail_address, gmail_app_password)
                mcp_log("INFO", f"Logged in as {gmail_address}")
                server.sendmail(gmail_address, actual_recipient, msg.as_string())
                mcp_log("INFO", f"Email sent successfully to {actual_recipient}")
                
                return {
                    "message_id": "smtp_sent",
                    "success": True,
                    "error": None
                }
        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP Authentication failed: {str(e)}. Ensure GMAIL_APP_PASSWORD is correct and 2-Step Verification is enabled."
            mcp_log("ERROR", error_msg)
            return {
                "message_id": "",
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Failed to send email: {str(e)}"
            mcp_log("ERROR", error_msg)
            return {
                "message_id": "",
                "success": False,
                "error": error_msg
            }
        
    except Exception as e:
        error_msg = f"Error in send_email_via_smtp: {str(e)}"
        mcp_log("ERROR", error_msg)
        mcp_log("ERROR", traceback.format_exc())
        return {
            "message_id": "",
            "success": False,
            "error": error_msg
        }


@mcp.tool()
def send_email(input: SendEmailInput) -> SendEmailOutput:
    """
    Send an email via Gmail SMTP.
    Uses fixed sender (GMAIL_ADDRESS) and recipient (RECIPIENT_EMAIL) from .env.
    Usage: send_email|input.to="user@example.com"|input.subject="F1 Standings"|input.body="Here is the sheet"|input.link="https://docs.google.com/spreadsheets/d/..."
    
    Note: The 'to' parameter is ignored - always uses RECIPIENT_EMAIL from .env
    """
    try:
        # Handle both nested input and direct args
        if isinstance(input, dict):
            subject = input.get("subject", "")
            body = input.get("body", "")
            link = input.get("link")
        else:
            subject = input.subject
            body = input.body
            link = input.link
        
        result = send_email_via_smtp(
            to="",  # Ignored - uses RECIPIENT_EMAIL from .env
            subject=subject,
            body=body,
            link=link
        )
        
        return SendEmailOutput(
            message_id=result.get("message_id", ""),
            success=result.get("success", False)
        )
    except Exception as e:
        error_msg = f"Failed to send email: {e}"
        mcp_log("ERROR", error_msg)
        return SendEmailOutput(
            message_id="",
            success=False
        )


@mcp.tool()
def send_email_with_link(to: str, subject: str, body: str, sheet_link: str) -> SendEmailOutput:
    """
    Send an email with a Google Sheet link via Gmail SMTP.
    Uses fixed sender (GMAIL_ADDRESS) and recipient (RECIPIENT_EMAIL) from .env.
    Usage: send_email_with_link|to="user@example.com"|subject="F1 Standings"|body="Here is your F1 standings sheet"|sheet_link="https://docs.google.com/spreadsheets/d/..."
    
    Note: The 'to' parameter is ignored - always uses RECIPIENT_EMAIL from .env
    """
    try:
        # Validate sheet_link is provided and is a valid Google Sheets URL
        if not sheet_link or not sheet_link.strip():
            error_msg = "sheet_link parameter is required and cannot be empty"
            mcp_log("ERROR", error_msg)
            return SendEmailOutput(
                message_id="",
                success=False
            )
        
        if not sheet_link.startswith("https://docs.google.com/spreadsheets/d/"):
            mcp_log("WARNING", f"sheet_link may not be a valid Google Sheets URL: {sheet_link[:50]}...")
        
        mcp_log("INFO", f"Sending email with Google Sheet link: {sheet_link[:80]}...")
        
        result = send_email_via_smtp(
            to="",  # Ignored - uses RECIPIENT_EMAIL from .env
            subject=subject,
            body=body,
            link=sheet_link
        )
        
        if result.get("success"):
            mcp_log("INFO", f"✅ Email sent successfully with Google Sheet link to {os.getenv('RECIPIENT_EMAIL', 'recipient')}")
        else:
            mcp_log("ERROR", f"❌ Failed to send email: {result.get('error', 'Unknown error')}")
        
        return SendEmailOutput(
            message_id=result.get("message_id", ""),
            success=result.get("success", False)
        )
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        mcp_log("ERROR", error_msg)
        return SendEmailOutput(
            message_id="",
            success=False
        )


if __name__ == "__main__":
    print("mcp_server_gmail.py starting")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")
        print("\nShutting down...")
