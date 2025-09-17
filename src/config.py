import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:datchu1505@localhost:5432/store_db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "change_me")
