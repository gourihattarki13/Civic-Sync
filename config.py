
import os
import secrets
from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv(override=False)

class Config:
    # A random fallback prevents a predictable signing key; set SECRET_KEY in .env for stable sessions.
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
    ADMIN_REGISTRATION_CODE = os.getenv("ADMIN_REGISTRATION_CODE", "")
    DEPARTMENT_REGISTRATION_CODE = os.getenv("DEPARTMENT_REGISTRATION_CODE", "")

    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "civic_issue_db")

    SQLALCHEMY_DATABASE_URI = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        query={"charset": "utf8mb4"}
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
