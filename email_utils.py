# backend/email_utils.py
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER  = "info@ecoconnectservices.com"       # apna Gmail
GMAIL_PASS  = "kcvk vcek svcd rdqh"  # App Password (spaces theek hain)
ADMIN_EMAIL = "aryan@ecoconnectservices.com"       # jahan notification chahiye

def send_admin_notification(name: str, email: str, role: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🌱 New {role.capitalize()} Signup — {name}"
        msg["From"]    = GMAIL_USER
        msg["To"]      = ADMIN_EMAIL

        html = f"""
        <div style="font-family:sans-serif;max-width:480px;padding:24px;border:1px solid #e5e7eb;border-radius:12px">
          <h2 style="color:#059669">New User on Ecoconnect!</h2>
          <p><b>Name:</b> {name}</p>
          <p><b>Email:</b> {email}</p>
          <p><b>Role:</b> {role.capitalize()}</p>
          <hr style="border-color:#e5e7eb"/>
          <p style="color:#9ca3af;font-size:12px">Ecoconnect Auto-Notification</p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, ADMIN_EMAIL, msg.as_string())
    except Exception as e:
        print(f"[Email] Failed to send notification: {e}")
        # registration fail nahi hogi email ki wajah se


def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(to_email: str, name: str, otp: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Verify your Ecoconnect account"
        msg["From"]    = GMAIL_USER
        msg["To"]      = to_email

        html = f"""
        <div style="font-family:sans-serif;max-width:480px;padding:24px;border:1px solid #e5e7eb;border-radius:12px">
          <h2 style="color:#059669">Welcome to Ecoconnect, {name}!</h2>
          <p>Your verification OTP is:</p>
          <h1 style="color:#059669;letter-spacing:8px">{otp}</h1>
          <p style="color:#9ca3af">Valid for 10 minutes only.</p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
    except Exception as e:
        print(f"[Email] OTP send failed: {e}")

def send_welcome_email(to_email: str, name: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Welcome to Ecoconnect! 🌱"
        msg["From"]    = GMAIL_USER
        msg["To"]      = to_email

        html = f"""
        <div style="font-family:sans-serif;max-width:480px;padding:24px;border:1px solid #e5e7eb;border-radius:12px">
          <h2 style="color:#059669">Welcome to Ecoconnect, {name}! 🌱</h2>
          <p>Your account has been successfully verified.</p>
          <p>You can now:</p>
          <ul>
            <li>Browse sustainability projects</li>
            <li>Showcase your skills</li>
            <li>Connect with top companies</li>
          </ul>
          <a href="http://localhost:8081" 
             style="background:#059669;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin-top:16px">
            Get Started →
          </a>
          <p style="color:#9ca3af;font-size:12px;margin-top:24px">Ecoconnect Team</p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
    except Exception as e:
        print(f"[Email] Welcome email failed: {e}")