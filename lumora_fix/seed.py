import os
from database import get_db_connection

def run_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        print("schema.sql not found at", schema_path)
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # Strip CREATE DATABASE and USE statements so tables are created in the active database
    clean_lines = []
    for line in sql.splitlines():
        trimmed = line.strip().upper()
        if trimmed.startswith("CREATE DATABASE") or trimmed.startswith("USE "):
            continue
        clean_lines.append(line)
    
    clean_sql = "\n".join(clean_lines)

    cur = conn.cursor()
    for statement in clean_sql.split(";"):
        stmt = statement.strip()
        if stmt:
            try:
                cur.execute(stmt)
            except Exception as e:
                print(f"Notice on stmt: {e}")
    conn.commit()
    
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    print("Tables successfully created in database:", tables)
    cur.close()

def seed():
    conn = get_db_connection()
    if not conn:
        print("Database connection failed")
        return
    
    run_schema(conn)
    
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
