import csv
import io
import os
import secrets
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import get_db_connection

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "lumora-dev-change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024

AVATAR_FOLDER = os.path.join("static", "uploads", "avatars")
COVER_FOLDER = os.path.join("static", "uploads", "covers")
ILLUSTRATION_FOLDER = os.path.join("static", "uploads", "illustrations")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "ogg", "mov"}
ALLOWED_DOC_EXTENSIONS = {"pdf", "epub"}
DOCUMENT_FOLDER = os.path.join("static", "uploads", "books")

for folder in (AVATAR_FOLDER, COVER_FOLDER, ILLUSTRATION_FOLDER, DOCUMENT_FOLDER):
    os.makedirs(folder, exist_ok=True)

def db():
    return get_db_connection()

def is_ajax():
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
        or request.path.startswith("/api/")
        or request.path.startswith("/save-book")
        or request.path.startswith("/unsave-book")
        or request.path.startswith("/track-")
        or request.path.startswith("/update-progress")
    )

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if is_ajax():
                return jsonify({"error": "Authentication required"}), 401
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            if is_ajax():
                return jsonify({"error": "Administrator access required"}), 403
            flash("Administrator access required.", "danger")
            return redirect(url_for("home"))
        return fn(*args, **kwargs)
    return wrapper

def ensure_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]

def get_site_settings():
    """Read site settings, including videos uploaded from Admin > Settings."""
    conn = db()
    if not conn:
        return {}
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT setting_key, setting_value FROM site_settings")
        settings = {row["setting_key"]: row["setting_value"] for row in cur.fetchall()}
        cur.close()
        conn.close()
        return settings
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return {}

@app.context_processor
def inject_globals():
    settings = get_site_settings()
    videos = find_videos()
    # Admin-uploaded videos take priority. Bundled videos remain as fallback.
    def usable_video(setting_value, fallback_group):
        if setting_value:
            # Uploaded videos are stored as /static/... paths. Only use the
            # saved setting when the file still exists; otherwise fall back to
            # the bundled LUMORA video so the page never loses its video.
            rel = setting_value.lstrip("/")
            if os.path.isfile(rel):
                return setting_value
        return (videos.get(fallback_group) or [{}])[0].get("url")

    # LUMORA's permanent visual identity: these two bundled videos are
    # always used for the public site. They are shipped inside the project,
    # so they do not disappear when the database/settings are changed.
    # Admin settings may still store uploaded files, but the public pages
    # intentionally keep these two approved LUMORA videos.
    fixed_hero = "/static/uploads/illustrations/lumora-home-library.mp4"
    fixed_about = "/static/uploads/illustrations/lumora-about-reading.mp4"
    hero_url = fixed_hero if os.path.isfile(fixed_hero.lstrip("/")) else usable_video(settings.get("hero_video"), "hero")
    about_url = fixed_about if os.path.isfile(fixed_about.lstrip("/")) else usable_video(settings.get("about_video"), "about")
    return {
        "csrf_token": ensure_csrf(),
        "current_user": session.get("user_name"),
        "current_role": session.get("role"),
        "hero_videos": videos,
        "about_videos": videos,
        "hero_video_url": hero_url,
        "about_video_url": about_url,
        "hero_video_type": video_mime(hero_url or ""),
        "about_video_type": video_mime(about_url or ""),
        "video_mime": video_mime,
        "site_settings": settings,
    }

@app.before_request
def csrf_guard():
    ensure_csrf()
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.endpoint in {"static"}:
        return None
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or not secrets.compare_digest(str(token), str(session.get("csrf_token", ""))):
        if is_ajax():
            return jsonify({"error": "Invalid CSRF token"}), 403
        flash("Your form session expired. Please try again.", "danger")
        return redirect(request.referrer or url_for("home"))
    return None

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_video(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def save_upload(file_storage, folder, prefix=""):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        raise ValueError("Unsupported image format. Use PNG, JPG, JPEG, WEBP, or GIF.")
    ext=file_storage.filename.rsplit(".",1)[1].lower()
    filename=secure_filename(f"{prefix}{secrets.token_hex(6)}.{ext}")
    file_storage.save(os.path.join(folder,filename))
    return f"/static/uploads/{Path(folder).name}/{filename}"

def save_video(file_storage,prefix):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_video(file_storage.filename):
        raise ValueError("Unsupported video format. Use MP4, WEBM, OGG, or MOV.")
    ext=file_storage.filename.rsplit(".",1)[1].lower()
    filename=secure_filename(f"{prefix}-{secrets.token_hex(6)}.{ext}")
    file_storage.save(os.path.join(ILLUSTRATION_FOLDER,filename))
    return f"/static/uploads/illustrations/{filename}"


def save_document(file_storage, prefix="book"):
    if not file_storage or not file_storage.filename: return None
    ext=file_storage.filename.rsplit(".",1)[1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_DOC_EXTENSIONS: raise ValueError("Only PDF or EPUB files are allowed.")
    filename=secure_filename(f"{prefix}-{secrets.token_hex(6)}.{ext}")
    file_storage.save(os.path.join(DOCUMENT_FOLDER,filename))
    return f"/static/uploads/books/{filename}"

def find_video(preferred):
    files=[]
    for name in os.listdir(ILLUSTRATION_FOLDER):
        if os.path.isfile(os.path.join(ILLUSTRATION_FOLDER,name)) and allowed_video(name):
            files.append(name)
    for pref in preferred:
        for name in files:
            if name.lower()==pref.lower():
                return f"/static/uploads/illustrations/{name}"
    return f"/static/uploads/illustrations/{files[0]}" if files else None

def find_videos():
    """Return deterministic hero/about video selections.

    Files named hero* are used for the home hero and files named about* for
    the About page. If either group is missing, the first available browser-
    compatible video is used as a fallback so adding any video still works.
    """
    files = []
    hero = []
    about = []
    for name in sorted(os.listdir(ILLUSTRATION_FOLDER)):
        full = os.path.join(ILLUSTRATION_FOLDER, name)
        if os.path.isfile(full) and allowed_video(name):
            item = {"url": url_for("static", filename=f"uploads/illustrations/{name}"),
                    "name": name}
            files.append(item)
            low = name.lower()
            if low.startswith("hero") or "hero" in low:
                hero.append(item)
            if low.startswith("about") or "about" in low:
                about.append(item)

    # Homepage and About intentionally require separate video groups.
    # Never silently reuse the same video on both pages: that would break
    # the visual storytelling and the LUMORA two-scene design.
    return {
        "all": files,
        "hero": hero[:1],
        "about": about[:1],
    }

def video_mime(path):
    ext=path.rsplit('.',1)[-1].lower() if '.' in path else ''
    return {"mp4":"video/mp4","webm":"video/webm","ogg":"video/ogg","mov":"video/quicktime"}.get(ext,"video/mp4")

def get_book(cur, book_id):
    cur.execute(
        """SELECT b.*, a.name AS author_name, s.name AS source_name
           FROM books b
           LEFT JOIN authors a ON b.author_id=a.id
           LEFT JOIN sources s ON b.source_id=s.id
           WHERE b.id=%s""",
        (book_id,),
    )
    return cur.fetchone()

def get_user_by_id(cur, user_id):
    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    return cur.fetchone()

@app.route("/")
def home():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT b.*,a.name AS author_name FROM books b
                   LEFT JOIN authors a ON b.author_id=a.id
                   WHERE b.is_featured=1 ORDER BY b.views DESC LIMIT 6""")
    featured = cur.fetchall()
    cur.execute("SELECT * FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur.close(); conn.close()
    return render_template("index.html", featured=featured, categories=categories)

@app.route("/library")
def library():
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", "").strip()
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    sql = """SELECT b.*,a.name AS author_name FROM books b
             LEFT JOIN authors a ON b.author_id=a.id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (b.title LIKE %s OR a.name LIKE %s OR b.isbn LIKE %s)"
        term = f"%{q}%"
        params += [term, term, term]
    if cat:
        sql += """ AND EXISTS (
            SELECT 1 FROM book_categories bc
            JOIN categories c ON c.id=bc.category_id
            WHERE bc.book_id=b.id AND c.slug=%s)"""
        params.append(cat)
    sql += " ORDER BY b.is_featured DESC,b.views DESC,b.title"
    cur.execute(sql, params)
    books = cur.fetchall()
    cur.execute("SELECT * FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur.close(); conn.close()
    return render_template("library.html", books=books, categories=categories)

@app.route("/api/book/<int:book_id>")
def api_book(book_id):
    conn = db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    cur = conn.cursor(dictionary=True)
    book = get_book(cur, book_id)
    if not book:
        cur.close(); conn.close()
        return jsonify({"error": "Book not found"}), 404
    cur.execute("UPDATE books SET views=views+1 WHERE id=%s", (book_id,))
    conn.commit()
    book["views"] = int(book["views"] or 0) + 1
    saved = False
    if session.get("user_id"):
        cur.execute("SELECT 1 FROM favorites WHERE user_id=%s AND book_id=%s",
                    (session["user_id"], book_id))
        saved = bool(cur.fetchone())
    book["saved"] = saved
    cur.close(); conn.close()
    return jsonify(book)

@app.route("/track-read/<int:book_id>", methods=["POST"])
@login_required
def track_read(book_id):
    conn = db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    cur = conn.cursor()
    cur.execute("SELECT id FROM books WHERE id=%s", (book_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error": "Book not found"}), 404
    cur.execute(
        """INSERT INTO reading_history(user_id,book_id,progress)
           VALUES(%s,%s,0)
           ON DUPLICATE KEY UPDATE last_read=CURRENT_TIMESTAMP""",
        (session["user_id"], book_id),
    )
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "ok"})

@app.route("/update-progress/<int:book_id>", methods=["POST"])
@login_required
def update_progress(book_id):
    payload = request.get_json(silent=True) or {}
    try:
        progress = max(0, min(100, int(payload.get("progress", 0))))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid progress"}), 400

    conn = db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    cur = conn.cursor()
    cur.execute("SELECT id FROM books WHERE id=%s", (book_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error": "Book not found"}), 404
    cur.execute(
        """INSERT INTO reading_history(user_id,book_id,progress)
           VALUES(%s,%s,%s)
           ON DUPLICATE KEY UPDATE progress=VALUES(progress),last_read=CURRENT_TIMESTAMP""",
        (session["user_id"], book_id, progress),
    )
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "ok", "progress": progress})

@app.route("/track-download/<int:book_id>", methods=["POST"])
@login_required
def track_download(book_id):
    fmt = request.args.get("format", "").lower()
    if fmt not in {"pdf", "epub"}:
        return jsonify({"error": "Unsupported format"}), 400
    conn = db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    cur = conn.cursor(dictionary=True)
    book = get_book(cur, book_id)
    if not book:
        cur.close(); conn.close()
        return jsonify({"error": "Book not found"}), 404
    if not book.get(f"{fmt}_url"):
        cur.close(); conn.close()
        return jsonify({"error": f"{fmt.upper()} is unavailable"}), 400
    cur.execute("INSERT INTO downloads(user_id,book_id,format) VALUES(%s,%s,%s)",
                (session["user_id"], book_id, fmt))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "ok"})

@app.route("/save-book/<int:book_id>", methods=["POST"])
@login_required
def save_book(book_id):
    conn = db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    cur = conn.cursor()
    cur.execute("SELECT id FROM books WHERE id=%s", (book_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error": "Book not found"}), 404
    cur.execute("INSERT IGNORE INTO favorites(user_id,book_id) VALUES(%s,%s)",
                (session["user_id"], book_id))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "ok", "saved": True})

@app.route("/unsave-book/<int:book_id>", methods=["POST"])
@login_required
def unsave_book(book_id):
    conn = db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    cur = conn.cursor()
    cur.execute("DELETE FROM favorites WHERE user_id=%s AND book_id=%s",
                (session["user_id"], book_id))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "ok", "saved": False})

@app.route("/collections")
@login_required
def collections():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT c.*,COUNT(cb.book_id) AS book_count
                   FROM collections c LEFT JOIN collection_books cb ON c.id=cb.collection_id
                   WHERE c.user_id=%s GROUP BY c.id ORDER BY c.created_at DESC""",
                (session["user_id"],))
    data = cur.fetchall()
    cur.close(); conn.close()
    return render_template("collections.html", collections=data)

@app.route("/collections/create", methods=["POST"])
@login_required
def create_collection():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Collection name is required.", "danger")
        return redirect(url_for("collections"))
    if len(name) > 150:
        flash("Collection name is too long.", "danger")
        return redirect(url_for("collections"))
    conn = db()
    if not conn:
        flash("Database unavailable.", "danger")
        return redirect(url_for("collections"))
    cur = conn.cursor()
    cur.execute("INSERT INTO collections(user_id,name) VALUES(%s,%s)",
                (session["user_id"], name))
    conn.commit()
    cur.close(); conn.close()
    flash("Collection created.", "success")
    return redirect(url_for("collections"))

def owned_collection(cur, collection_id):
    cur.execute("SELECT * FROM collections WHERE id=%s AND user_id=%s",
                (collection_id, session["user_id"]))
    return cur.fetchone()

@app.route("/collections/<int:collection_id>")
@login_required
def collection_detail(collection_id):
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    collection = owned_collection(cur, collection_id)
    if not collection:
        cur.close(); conn.close()
        flash("Collection not found.", "danger")
        return redirect(url_for("collections"))
    cur.execute("""SELECT b.*,a.name AS author_name FROM books b
                   LEFT JOIN authors a ON a.id=b.author_id
                   JOIN collection_books cb ON cb.book_id=b.id
                   WHERE cb.collection_id=%s ORDER BY b.title""", (collection_id,))
    books = cur.fetchall()
    cur.execute("""SELECT b.*,a.name AS author_name FROM books b
                   LEFT JOIN authors a ON a.id=b.author_id
                   WHERE NOT EXISTS (
                       SELECT 1 FROM collection_books cb
                       WHERE cb.collection_id=%s AND cb.book_id=b.id)
                   ORDER BY b.title""", (collection_id,))
    available = cur.fetchall()
    cur.close(); conn.close()
    return render_template("collection_detail.html", collection=collection,
                           books=books, available_books=available)

@app.route("/collections/<int:collection_id>/rename", methods=["POST"])
@login_required
def rename_collection(collection_id):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Collection name is required.", "danger")
        return redirect(url_for("collections"))
    conn = db()
    if not conn:
        flash("Database unavailable.", "danger")
        return redirect(url_for("collections"))
    cur = conn.cursor()
    cur.execute("UPDATE collections SET name=%s WHERE id=%s AND user_id=%s",
                (name, collection_id, session["user_id"]))
    conn.commit()
    changed = cur.rowcount
    cur.close(); conn.close()
    flash("Collection renamed." if changed else "Collection not found.", "success" if changed else "danger")
    return redirect(url_for("collections"))

@app.route("/collections/<int:collection_id>/delete", methods=["POST"])
@login_required
def delete_collection(collection_id):
    conn = db()
    if conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM collections WHERE id=%s AND user_id=%s",
                    (collection_id, session["user_id"]))
        conn.commit()
        changed = cur.rowcount
        cur.close(); conn.close()
        flash("Collection deleted." if changed else "Collection not found.",
              "info" if changed else "danger")
    return redirect(url_for("collections"))

@app.route("/collections/<int:collection_id>/add-book", methods=["POST"])
@login_required
def add_book_to_collection(collection_id):
    book_id = request.form.get("book_id", type=int)
    conn = db()
    if not conn:
        flash("Database unavailable.", "danger")
        return redirect(url_for("collection_detail", collection_id=collection_id))
    cur = conn.cursor()
    cur.execute("SELECT id FROM collections WHERE id=%s AND user_id=%s",
                (collection_id, session["user_id"]))
    collection_ok = cur.fetchone()
    cur.execute("SELECT id FROM books WHERE id=%s", (book_id,))
    book_ok = cur.fetchone() if book_id else None
    if collection_ok and book_ok:
        cur.execute("INSERT IGNORE INTO collection_books(collection_id,book_id) VALUES(%s,%s)",
                    (collection_id, book_id))
        conn.commit()
        flash("Book added to collection.", "success")
    else:
        flash("Invalid collection or book.", "danger")
    cur.close(); conn.close()
    return redirect(url_for("collection_detail", collection_id=collection_id))

@app.route("/collections/<int:collection_id>/remove-book", methods=["POST"])
@login_required
def remove_book_from_collection(collection_id):
    book_id = request.form.get("book_id", type=int)
    conn = db()
    if conn:
        cur = conn.cursor()
        cur.execute("""DELETE cb FROM collection_books cb
                       JOIN collections c ON c.id=cb.collection_id
                       WHERE cb.collection_id=%s AND cb.book_id=%s AND c.user_id=%s""",
                    (collection_id, book_id, session["user_id"]))
        conn.commit()
        cur.close(); conn.close()
        flash("Book removed.", "info")
    return redirect(url_for("collection_detail", collection_id=collection_id))

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        if not all([name, email, subject, message]) or "@" not in email:
            flash("Please complete all fields with a valid email.", "danger")
            return redirect(url_for("contact"))
        conn = db()
        if not conn:
            flash("Database unavailable.", "danger")
            return redirect(url_for("contact"))
        cur = conn.cursor()
        cur.execute("""INSERT INTO contact_messages(name,email,subject,message)
                       VALUES(%s,%s,%s,%s)""", (name,email,subject,message))
        conn.commit()
        cur.close(); conn.close()
        flash("Message sent successfully.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(name) < 2 or "@" not in email or len(password) < 6:
            flash("Enter a valid name, email, and password of at least 6 characters.", "danger")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
        conn = db()
        if not conn:
            flash("Database unavailable.", "danger")
            return render_template("register.html")
        cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO users(name,email,password_hash,role)
                           VALUES(%s,%s,%s,'user')""",
                        (name,email,generate_password_hash(password)))
            conn.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        except Exception:
            conn.rollback()
            flash("That email is already registered.", "danger")
        finally:
            cur.close(); conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = db()
        if not conn:
            flash("Database unavailable.", "danger")
            return render_template("login.html")
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close(); conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["csrf_token"] = secrets.token_urlsafe(32)
            session.update({
                "user_id": user["id"],
                "user_name": user["name"],
                "role": user["role"],
                "theme": user["theme_preference"],
            })
            return redirect(url_for("admin_overview") if user["role"] == "admin"
                            else url_for("dashboard_overview"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/read/<int:book_id>")
def read_book(book_id):
    conn=db()
    if not conn:
        return "Database unavailable.",500
    cur=conn.cursor(dictionary=True)
    book=get_book(cur,book_id)
    if not book:
        cur.close(); conn.close(); return "Book not found.",404
    cur.execute("UPDATE books SET views=views+1 WHERE id=%s",(book_id,))
    conn.commit()
    cur.close(); conn.close()
    return render_template("reader.html",book=book)

@app.route("/export/<int:book_id>")
@login_required
def export_metadata(book_id):
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    book = get_book(cur, book_id)
    cur.close(); conn.close()
    if not book:
        return "Book not found.", 404
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title","Author","Year","Language","License","ISBN","Publisher","Source"])
    writer.writerow([
        book["title"], book["author_name"] or "", book["pub_year"] or "",
        book["language"] or "", book["license_info"] or "", book["isbn"] or "",
        book["publisher"] or "", book["source_name"] or ""
    ])
    filename = secure_filename(book["title"]) or "book"
    return send_file(io.BytesIO(output.getvalue().encode("utf-8")),
                     mimetype="text/csv", as_attachment=True,
                     download_name=f"{filename}.csv")

@app.route("/api/theme", methods=["POST"])
@login_required
def update_theme():
    payload = request.get_json(silent=True) or {}
    theme = payload.get("theme")
    if theme not in {"light", "dark"}:
        return jsonify({"error": "Invalid theme"}), 400
    conn = db()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    cur = conn.cursor()
    cur.execute("UPDATE users SET theme_preference=%s WHERE id=%s",
                (theme, session["user_id"]))
    conn.commit()
    session["theme"] = theme
    cur.close(); conn.close()
    return jsonify({"status": "ok"})

@app.route("/dashboard")
@login_required
def dashboard_overview():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS cnt FROM favorites WHERE user_id=%s", (session["user_id"],))
    saved = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM collections WHERE user_id=%s", (session["user_id"],))
    collections_count = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM reading_history WHERE user_id=%s", (session["user_id"],))
    reading = cur.fetchone()["cnt"]
    cur.close(); conn.close()
    return render_template("dashboard/overview.html",
                           stats={"saved":saved,"collections":collections_count,"read":reading})

@app.route("/dashboard/library")
@login_required
def dashboard_library():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT b.*,a.name AS author_name FROM books b
                   JOIN favorites f ON f.book_id=b.id
                   LEFT JOIN authors a ON a.id=b.author_id
                   WHERE f.user_id=%s ORDER BY b.title""", (session["user_id"],))
    books = cur.fetchall()
    cur.close(); conn.close()
    return render_template("dashboard/library.html", books=books)

@app.route("/dashboard/reading")
@login_required
def dashboard_reading():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT b.*,a.name AS author_name,rh.last_read,rh.progress
                   FROM reading_history rh JOIN books b ON b.id=rh.book_id
                   LEFT JOIN authors a ON a.id=b.author_id
                   WHERE rh.user_id=%s ORDER BY rh.last_read DESC""",
                (session["user_id"],))
    history = cur.fetchall()
    cur.close(); conn.close()
    return render_template("dashboard/reading.html", history=history)

@app.route("/dashboard/profile", methods=["GET", "POST"])
@login_required
def dashboard_profile():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        pic = request.files.get("profile_pic")
        cur = conn.cursor()
        if not name:
            flash("Name is required.", "danger")
            cur.close(); conn.close()
            return redirect(url_for("dashboard_profile"))
        if pic and pic.filename:
            if not allowed_file(pic.filename):
                flash("Only PNG, JPG, JPEG, and WebP images are allowed.", "danger")
                cur.close(); conn.close()
                return redirect(url_for("dashboard_profile"))
            ext = pic.filename.rsplit(".", 1)[1].lower()
            filename = secure_filename(f"user_{session['user_id']}.{ext}")
            pic.save(os.path.join(AVATAR_FOLDER, filename))
            cur.execute("UPDATE users SET profile_pic=%s WHERE id=%s",
                        (filename, session["user_id"]))
        cur.execute("UPDATE users SET name=%s WHERE id=%s",
                    (name, session["user_id"]))
        if password:
            if len(password) < 6:
                flash("New password must be at least 6 characters.", "danger")
                cur.close(); conn.close()
                return redirect(url_for("dashboard_profile"))
            cur.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                        (generate_password_hash(password), session["user_id"]))
        conn.commit()
        session["user_name"] = name
        cur.close(); conn.close()
        flash("Profile updated.", "success")
        return redirect(url_for("dashboard_profile"))

    cur = conn.cursor(dictionary=True)
    user = get_user_by_id(cur, session["user_id"])
    cur.close(); conn.close()
    return render_template("dashboard/profile.html", user=user)

@app.route("/admin")
@admin_required
def admin_overview():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS cnt FROM books")
    books = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    users = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM contact_messages")
    messages = cur.fetchone()["cnt"]
    cur.close(); conn.close()
    return render_template("admin/overview.html", books=books, users=users, messages=messages)

@app.route("/admin/library")
@admin_required
def admin_library():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT b.*,a.name AS author_name FROM books b
                   LEFT JOIN authors a ON a.id=b.author_id
                   ORDER BY b.created_at DESC""")
    books = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin/library.html", books=books)

def admin_form_data(cur):
    cur.execute("SELECT * FROM authors ORDER BY name")
    authors = cur.fetchall()
    cur.execute("SELECT * FROM sources ORDER BY name")
    sources = cur.fetchall()
    cur.execute("SELECT * FROM categories ORDER BY name")
    categories = cur.fetchall()
    return authors, sources, categories

@app.route("/admin/authors/quick-add", methods=["POST"])
@admin_required
def admin_quick_add_author():
    """Create an author from the Add Book/Novel/Story form and return its id."""
    conn = db()
    if not conn:
        return jsonify({"ok": False, "error": "Database unavailable."}), 500
    cur = conn.cursor(dictionary=True)
    try:
        name = (request.form.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "Author name is required."}), 400
        cur.execute("SELECT id, name FROM authors WHERE LOWER(name)=LOWER(%s) LIMIT 1", (name,))
        row = cur.fetchone()
        if row:
            return jsonify({"ok": True, "id": row["id"], "name": row["name"], "existing": True})
        cur.execute("INSERT INTO authors(name) VALUES(%s)", (name,))
        author_id = cur.lastrowid
        conn.commit()
        return jsonify({"ok": True, "id": author_id, "name": name, "existing": False})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        cur.close(); conn.close()

@app.route("/admin/authors", methods=["GET", "POST"])
@admin_required
def admin_authors():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Author name is required.", "danger")
        else:
            try:
                cur.execute("INSERT INTO authors(name) VALUES(%s)", (name,))
                conn.commit()
                flash("Author added successfully.", "success")
            except Exception as exc:
                conn.rollback()
                if "Duplicate" in str(exc) or "1062" in str(exc):
                    flash("That author already exists.", "danger")
                else:
                    flash("Could not add author.", "danger")
        cur.close(); conn.close()
        return redirect(url_for("admin_authors"))
    cur.execute("""SELECT a.id, a.name, COUNT(b.id) AS book_count
                   FROM authors a LEFT JOIN books b ON b.author_id=a.id
                   GROUP BY a.id, a.name ORDER BY a.name""")
    authors = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin/authors.html", authors=authors)

@app.route("/admin/authors/<int:author_id>/delete", methods=["POST"])
@admin_required
def admin_delete_author(author_id):
    conn = db()
    if conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM authors WHERE id=%s", (author_id,))
        conn.commit()
        cur.close(); conn.close()
        flash("Author deleted. Books using this author now show Unknown author.", "info")
    return redirect(url_for("admin_authors"))

def resolve_author(cur, author_id, new_author_name):
    """Return an existing/new author id so every saved book has its author."""
    name = (new_author_name or "").strip()
    if name:
        cur.execute("SELECT id FROM authors WHERE LOWER(name)=LOWER(%s) LIMIT 1", (name,))
        row = cur.fetchone()
        if row:
            return row["id"] if isinstance(row, dict) else row[0]
        cur.execute("INSERT INTO authors(name) VALUES(%s)", (name,))
        return cur.lastrowid
    return author_id or None

@app.route("/admin/books/add", methods=["GET", "POST"])
@admin_required
def admin_add_book():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            if not title:
                raise ValueError("Title is required.")
            author_id = resolve_author(cur, request.form.get("author_id", type=int) or None, request.form.get("new_author_name", ""))
            source_id = request.form.get("source_id", type=int) or None
            year_raw = request.form.get("pub_year", "").strip()
            year = int(year_raw) if year_raw else None
            cover_url=request.form.get("cover_url","").strip()
            if request.files.get("cover_file") and request.files["cover_file"].filename:
                cover_url=save_upload(request.files["cover_file"],COVER_FOLDER,"cover-")
            pdf_url=request.form.get("pdf_url","").strip()
            epub_url=request.form.get("epub_url","").strip()
            if request.files.get("pdf_file") and request.files["pdf_file"].filename: pdf_url=save_document(request.files["pdf_file"],"pdf")
            if request.files.get("epub_file") and request.files["epub_file"].filename: epub_url=save_document(request.files["epub_file"],"epub")
            cur.execute(
                """INSERT INTO books(title,author_id,description,cover_url,isbn,publisher,pub_year,
                language,source_id,license_info,read_url,pdf_url,epub_url,is_featured)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (title,author_id,request.form.get("description","").strip(),
                 cover_url,request.form.get("isbn","").strip(),
                 request.form.get("publisher","").strip(),year,
                 request.form.get("language","English").strip() or "English",source_id,
                 request.form.get("license_info","Public Domain").strip() or "Public Domain",
                 request.form.get("read_url","").strip(),pdf_url,epub_url,bool(request.form.get("is_featured")))
            )
            book_id = cur.lastrowid
            for cid in request.form.getlist("categories"):
                if cid.isdigit():
                    cur.execute("INSERT IGNORE INTO book_categories(book_id,category_id) VALUES(%s,%s)",
                                (book_id, int(cid)))
            conn.commit()
            flash("Book added.", "success")
            cur.close(); conn.close()
            return redirect(url_for("admin_library"))
        except Exception as exc:
            conn.rollback()
            flash(str(exc), "danger")
    authors, sources, categories = admin_form_data(cur)
    cur.close(); conn.close()
    return render_template("admin/book_form.html", edit_mode=False, book={},
                           book_cats=[], authors=authors, sources=sources, categories=categories)

@app.route("/admin/books/<int:book_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_book(book_id):
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    book = get_book(cur, book_id)
    if not book:
        cur.close(); conn.close()
        flash("Book not found.", "danger")
        return redirect(url_for("admin_library"))
    if request.method == "POST":
        try:
            year_raw = request.form.get("pub_year", "").strip()
            year = int(year_raw) if year_raw else None
            cover_url=request.form.get("cover_url","").strip() or book.get("cover_url","")
            if request.files.get("cover_file") and request.files["cover_file"].filename:
                cover_url=save_upload(request.files["cover_file"],COVER_FOLDER,"cover-")
            pdf_url=request.form.get("pdf_url","").strip() or book.get("pdf_url","")
            epub_url=request.form.get("epub_url","").strip() or book.get("epub_url","")
            if request.files.get("pdf_file") and request.files["pdf_file"].filename: pdf_url=save_document(request.files["pdf_file"],"pdf")
            if request.files.get("epub_file") and request.files["epub_file"].filename: epub_url=save_document(request.files["epub_file"],"epub")
            cur.execute(
                """UPDATE books SET title=%s,author_id=%s,description=%s,cover_url=%s,isbn=%s,
                publisher=%s,pub_year=%s,language=%s,source_id=%s,license_info=%s,read_url=%s,
                pdf_url=%s,epub_url=%s,is_featured=%s WHERE id=%s""",
                (request.form.get("title","").strip(),
                 resolve_author(cur, request.form.get("author_id", type=int) or None, request.form.get("new_author_name", "")),
                 request.form.get("description","").strip(),
                 cover_url,
                 request.form.get("isbn","").strip(),
                 request.form.get("publisher","").strip(),year,
                 request.form.get("language","English").strip() or "English",
                 request.form.get("source_id", type=int) or None,
                 request.form.get("license_info","Public Domain").strip() or "Public Domain",
                 request.form.get("read_url","").strip(),
                 pdf_url,
                 epub_url,
                 bool(request.form.get("is_featured")), book_id)
            )
            cur.execute("DELETE FROM book_categories WHERE book_id=%s", (book_id,))
            for cid in request.form.getlist("categories"):
                if cid.isdigit():
                    cur.execute("INSERT IGNORE INTO book_categories(book_id,category_id) VALUES(%s,%s)",
                                (book_id, int(cid)))
            conn.commit()
            flash("Book updated.", "success")
            cur.close(); conn.close()
            return redirect(url_for("admin_library"))
        except Exception as exc:
            conn.rollback()
            flash(str(exc), "danger")
    cur.execute("SELECT category_id FROM book_categories WHERE book_id=%s", (book_id,))
    book_cats = [r["category_id"] for r in cur.fetchall()]
    authors, sources, categories = admin_form_data(cur)
    cur.close(); conn.close()
    return render_template("admin/book_form.html", edit_mode=True, book=book,
                           book_cats=book_cats, authors=authors,
                           sources=sources, categories=categories)

@app.route("/admin/books/<int:book_id>/delete", methods=["POST"])
@admin_required
def admin_delete_book(book_id):
    conn = db()
    if conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM books WHERE id=%s", (book_id,))
        conn.commit()
        cur.close(); conn.close()
        flash("Book deleted.", "info")
    return redirect(url_for("admin_library"))

@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    conn=db()
    if not conn: return "Database unavailable.",500
    cur=conn.cursor(dictionary=True)
    if request.method=="POST":
        name=request.form.get("name","").strip()
        slug=request.form.get("slug","").strip().lower().replace(" ","-")
        if not name: return redirect(url_for("admin_categories"))
        if not slug: slug='-'.join(''.join(ch.lower() if ch.isalnum() else '-' for ch in name).split('-'))
        try:
            cur.execute("INSERT INTO categories(name,slug) VALUES(%s,%s)",(name,slug))
            conn.commit()
        except Exception:
            conn.rollback()
        return redirect(url_for("admin_categories"))
    cur.execute("SELECT c.*,COUNT(bc.book_id) AS book_count FROM categories c LEFT JOIN book_categories bc ON c.id=bc.category_id GROUP BY c.id ORDER BY c.name")
    categories=cur.fetchall(); cur.close(); conn.close()
    return render_template("admin/categories.html",categories=categories)

@app.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def admin_delete_category(category_id):
    conn=db()
    if conn:
        cur=conn.cursor(); cur.execute("DELETE FROM categories WHERE id=%s",(category_id,)); conn.commit(); cur.close(); conn.close()
    return redirect(url_for("admin_categories"))

@app.route("/admin/users")
@admin_required
def admin_users():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id,name,email,role,profile_pic,created_at FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin/users.html", users=users)

@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@admin_required
def admin_change_role(user_id):
    role = request.form.get("role")
    if role not in {"user", "admin"}:
        flash("Invalid role.", "danger")
        return redirect(url_for("admin_users"))
    if user_id == session["user_id"] and role != "admin":
        flash("You cannot remove your own administrator role.", "danger")
        return redirect(url_for("admin_users"))
    conn = db()
    if conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role=%s WHERE id=%s", (role, user_id))
        conn.commit()
        cur.close(); conn.close()
        flash("User role updated.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session["user_id"]:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin_users"))
    conn = db()
    if conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        cur.close(); conn.close()
        flash("User deleted.", "info")
    return redirect(url_for("admin_users"))

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    conn = db()
    if not conn:
        return "Database unavailable.", 500
    if request.method == "POST":
        cur = conn.cursor()
        for key in ("site_title", "library_desc"):
            value = request.form.get(key, "").strip()
            cur.execute("""INSERT INTO site_settings(setting_key,setting_value)
                           VALUES(%s,%s)
                           ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)""",
                        (key, value))
        try:
            hero=save_video(request.files.get("hero_video"),"hero")
            about=save_video(request.files.get("about_video"),"about")
            if hero:
                cur.execute("INSERT INTO site_settings(setting_key,setting_value) VALUES('hero_video',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",(hero,))
            if about:
                cur.execute("INSERT INTO site_settings(setting_key,setting_value) VALUES('about_video',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",(about,))
        except ValueError as exc:
            conn.rollback(); cur.close(); conn.close(); flash(str(exc),"danger"); return redirect(url_for("admin_settings"))
        conn.commit()
        cur.close(); conn.close()
        flash("Settings saved.", "success")
        return redirect(url_for("admin_settings"))
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM site_settings")
    settings = {row["setting_key"]: row["setting_value"] for row in cur.fetchall()}
    cur.close(); conn.close()
    return render_template("admin/settings.html", settings=settings)

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
