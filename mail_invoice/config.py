import os

class EmailConfig:
    """Email configuration settings"""
    
    # SMTP Settings - Update these with your actual email provider settings
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    
    # Email Credentials - UPDATE THESE WITH YOUR ACTUAL EMAIL
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'kuchigokul@gmail.com')  # Replace with your email
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', 'ezem gwms jzdl stst')  # Replace with your app password
    
    # Email Settings
    USE_TLS = True
    USE_SSL = False
    
    @classmethod
    def validate_config(cls):
        """Validate that required email configuration is present"""
        if not cls.SENDER_EMAIL or cls.SENDER_EMAIL == 'your-email@gmail.com':
            raise ValueError("Please update SENDER_EMAIL in config.py or set SENDER_EMAIL environment variable")
        if not cls.SENDER_PASSWORD or cls.SENDER_PASSWORD == 'your-app-password':
            raise ValueError("Please update SENDER_PASSWORD in config.py or set SENDER_PASSWORD environment variable")
        return True