import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load the API folder's .env regardless of the directory from which
# uvicorn is started.
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_FILE)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "nyaymitra")
DB_USER = os.getenv("DB_USER", "nyaymitra")
DB_PASSWORD = os.getenv("DB_PASSWORD", "nyaymitra_dev_password")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )
