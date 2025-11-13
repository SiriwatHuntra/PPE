import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import json
from pathlib import Path

# Load Config (alertMail.json)
CONFIG_PATH = Path(__file__).parent / "alertMail.json"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

EMAIL_CONFIG = config["settings"]
EMAIL_LIST = [item for item in config["emails"] if item["enabled"]]

SMTP_SERVER = EMAIL_CONFIG["smtpServer"]
PORT = EMAIL_CONFIG["port"]
SENDER = EMAIL_CONFIG["sender"]
USE_TLS = EMAIL_CONFIG.get("useTLS", True)


# Send alert to all emails defined inside alertMail.json
def mail_to_stakeholder(event, location, detail):
    for entry in EMAIL_LIST:
        send_emergency_email(
            smtp_server=SMTP_SERVER,
            port=PORT,
            sender_email=SENDER,
            receiver=entry["recipient"],
            subject=entry["subject"],
            body=entry["body"],
            priority=entry["priority"],
            event_name=event,
            location=location,
            detail=detail
        )


# -------------------------------------------------------
# Single email send
# -------------------------------------------------------
def send_emergency_email(
    smtp_server: str,
    port: int,
    sender_email: str,
    receiver: str,
    subject: str,
    body: str,
    priority: str,
    event_name: str,
    location: str,
    detail: str,
):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        final_subject = f"🚨 {subject} — {event_name} at {location}"
        final_body = f"""
        <html>
        <body style="font-family:Segoe UI,Arial,sans-serif; color:#222;">
            <div style="border-left:5px solid #d32f2f; padding:14px 20px;">
                <h2 style="color:#d32f2f;">⚠️ {priority.upper()} Alert</h2>
                <p><b>Location:</b> {location}</p>
                <p><b>Event:</b> {event_name}</p>
                <p><b>Triggered at:</b> {now}</p>
                <p><b>Details:</b> {detail or body}</p>
            </div>
            <br>
            <p style="font-size:13px; color:#777;">
                This is an automatic alert from the safety monitoring system.
            </p>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = final_subject
        msg["From"] = sender_email
        msg["To"] = receiver
        msg.attach(MIMEText(final_body, "html"))

        with smtplib.SMTP(smtp_server, port) as server:
            if USE_TLS:
                server.starttls()

            # login (empty pw supported on your environment)
            server.login(sender_email, "")

            server.sendmail(sender_email, [receiver], msg.as_string())

        print(f"[OK] Email sent → {receiver}")

    except Exception as e:
        print(f"[ERROR] Failed to send email → {receiver}: {e}")


# -------------------------------------------------------
# Manual test
# -------------------------------------------------------
if __name__ == "__main__":
    mail_to_stakeholder("Testing", "Workplace", "Testing mailer function")
