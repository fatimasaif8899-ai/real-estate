import os
import mysql.connector
from database import get_db_connection

def run_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if os.path.exists(schema_path):
        print("Creating tables from schema.sql...")
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        cur = conn.cursor()
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    print(f"Schema notice: {e}")
        conn.commit()
        cur.close()
        print("Schema initialized successfully.")

def seed():
    conn = get_db_connection()
    if not conn:
        print("Database connection failed")
        return
    
    # 1. First create all database tables
    run_schema(conn)
    
    # 2. Seed initial admin user
    try:
        from werkzeug.security import generate_password_hash
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM users WHERE email=%s", ("admin@lumora.lib",))
        if not cur.fetchone():
            pw = generate_password_hash("Admin@1234")
            cur.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'admin')", ("Admin", "admin@lumora.lib", pw))
            conn.commit()
            print("Admin user seeded (admin@lumora.lib / Admin@1234).")
        cur.close()
    except Exception as e:
        print(f"Seed note: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed()
