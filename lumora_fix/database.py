import os
import mysql.connector
from mysql.connector import Error

def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "lumora_db"),
            port=int(os.getenv("DB_PORT", "3306"))
        )
    except Error as e:
        print(f"Database Error: {e}")
        return None
