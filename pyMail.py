import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
# from LogHandler import init_logger

# logger = init_logger("Mail_Alert")  # uncomment if logging is available
email_list = [".com"]

SMTPSERVER = "10.28.32.81"
PORT = 587
SENDER = "lsi_server_admin@mnf2.rohmthai.com"
#no pass


def mail_to_stakeholder(event, location, detail):
    """
    Send the same emergency alert to all stakeholders.
    """
    for receiver in email_list:
        send_emergency_email(
            smtp_server=SMTPSERVER,
            port=PORT,
            sender_email=SENDER,
            sender_pass=APP_AUTH,
            receiver=receiver,
            event_name=event,
            location=location,
            detail=detail
        )

def send_emergency_email(
    smtp_server: str,
    port: int,
    sender_email: str,
    sender_pass: str,
    receiver: str,
    event_name: str = "Emergency Alert",
    location: str = "Main Station",
    detail: str = "",
):
    """
    Send email alert to managers when emergency is ACTIVATED.
    """
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = f"🚨 Emergency Activated — {event_name} at {location}"

        html = f"""
        <html>
        <body style="font-family:Segoe UI,Arial,sans-serif; color:#222;">
            <div style="border-left:5px solid #d32f2f; padding:14px 20px;">
                <h2 style="color:#d32f2f;">⚠️ Emergency Activated</h2>
                <p><b>Location:</b> {location}</p>
                <p><b>Event:</b> {event_name}</p>
                <p><b>Triggered at:</b> {now}</p>
                <p><b>Details:</b> {detail or 'No further information provided.'}</p>
            </div>
            <br>
            <p style="font-size:13px; color:#777;">
                This is an automatic alert from the safety monitoring system.<br>
                Please take immediate action and verify system condition.
            </p>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = receiver  # just a single email string, not joined
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()
            server.login(sender_email, sender_pass)
            server.sendmail(sender_email, [receiver], msg.as_string())

        print(f"Emergency email sent to {receiver}")

    except Exception as e:
        print(f"Failed to send emergency email: {e}")

mail_to_stakeholder("Testing", "Workplace", "Tesing mailer function")