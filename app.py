import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session

# ---------------------------
# App config
# ---------------------------
app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")  # local fallback

app.config["UPLOAD_FOLDER"] = "static/uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

DB_PATH = "law7aty.db"

# Instagram URL (you gave)
INSTAGRAM_URL = os.environ.get(
    "INSTAGRAM_URL",
    "https://www.instagram.com/law7atiii?igsh=MXN5YnQ0bTM0c3l3Zg%3D%3D&utm_source=qr"
)

# ---------------------------
# Database helpers
# ---------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _safe_add_column(cur, table, col_def_sql):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def_sql}")
    except Exception:
        pass

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Workshops table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS workshops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        location TEXT,
        date TEXT,
        time TEXT,
        seats_total INTEGER,
        lessons_count INTEGER,
        age_range TEXT,
        image_url TEXT
    )
    """)

    # Registrations table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workshop_id INTEGER,
        name TEXT,
        phone TEXT,
        age INTEGER,
        notes TEXT,
        created_at TEXT,
        contacted INTEGER DEFAULT 0,
        canceled INTEGER DEFAULT 0,
        paid INTEGER DEFAULT 0,
        paid_amount REAL
    )
    """)

    # Settings table (one row)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        hero_image_url TEXT
    )
    """)

    # Backward compatible adds
    _safe_add_column(cur, "workshops", "lessons_count INTEGER")
    _safe_add_column(cur, "registrations", "contacted INTEGER DEFAULT 0")
    _safe_add_column(cur, "registrations", "canceled INTEGER DEFAULT 0")
    _safe_add_column(cur, "registrations", "paid INTEGER DEFAULT 0")
    _safe_add_column(cur, "registrations", "paid_amount REAL")
    _safe_add_column(cur, "settings", "hero_image_url TEXT")

    # Ensure settings row exists
    cur.execute("INSERT OR IGNORE INTO settings (id, hero_image_url) VALUES (1, '')")

    conn.commit()
    conn.close()

init_db()

# ---------------------------
# Admin auth helper
# ---------------------------
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

# ---------------------------
# CUSTOMER ROUTES
# ---------------------------
@app.route("/")
def customer_page():
    conn = get_db()

    workshops = conn.execute("""
        SELECT w.*,
        (SELECT COUNT(*) FROM registrations r WHERE r.workshop_id = w.id) AS reg_count
        FROM workshops w
        ORDER BY COALESCE(w.date, '') ASC, w.id DESC
    """).fetchall()

    settings = conn.execute("SELECT hero_image_url FROM settings WHERE id=1").fetchone()
    conn.close()

    hero_image_url = settings["hero_image_url"] if settings and settings["hero_image_url"] else ""

    enriched = []
    for w in workshops:
        reg_count = int(w["reg_count"] or 0)
        seats_total = int(w["seats_total"] or 0)
        seats_left = max(0, seats_total - reg_count)
        enriched.append(dict(w, seats_left=seats_left))

    return render_template(
        "index.html",
        workshops=enriched,
        hero_image_url=hero_image_url,
        instagram_url=INSTAGRAM_URL
    )

@app.route("/register", methods=["POST"])
def register():
    workshop_id = request.form.get("workshop_id")
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    age = request.form.get("age", "").strip()
    notes = request.form.get("notes", "").strip()

    if not (workshop_id and name and phone and age):
        return redirect(url_for("customer_page"))

    conn = get_db()
    conn.execute("""
        INSERT INTO registrations
        (workshop_id, name, phone, age, notes, created_at, contacted, canceled, paid, paid_amount)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, NULL)
    """, (
        workshop_id,
        name,
        phone,
        int(age),
        notes,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))
    conn.commit()
    conn.close()

    return redirect(url_for("customer_page"))

# ---------------------------
# ADMIN LOGIN/LOGOUT
# ---------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    msg = ""
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_page"))
        msg = "Wrong password ❌"
    return render_template("admin_login.html", message=msg)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("customer_page"))

# ---------------------------
# ADMIN ROUTES
# ---------------------------
@app.route("/admin")
@admin_required
def admin_page():
    conn = get_db()
    workshops = conn.execute("""
        SELECT w.*,
        (SELECT COUNT(*) FROM registrations r WHERE r.workshop_id = w.id) AS reg_count
        FROM workshops w
        ORDER BY COALESCE(w.date, '') ASC, w.id DESC
    """).fetchall()

    settings = conn.execute("SELECT hero_image_url FROM settings WHERE id=1").fetchone()
    conn.close()

    hero_image_url = settings["hero_image_url"] if settings and settings["hero_image_url"] else ""

    return render_template("admin.html", workshops=workshops, hero_image_url=hero_image_url)

@app.route("/admin/settings/hero", methods=["POST"])
@admin_required
def admin_update_hero():
    image = request.files.get("hero_image")

    hero_url = ""
    if image and image.filename:
        filename = f"hero_{int(datetime.now().timestamp())}_{image.filename}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(path)
        hero_url = "/" + path.replace("\\", "/")

    conn = get_db()
    conn.execute("UPDATE settings SET hero_image_url=? WHERE id=1", (hero_url,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/add", methods=["POST"])
@admin_required
def admin_add_workshop():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()

    date = request.form.get("date", "").strip()   # optional
    time = request.form.get("time", "").strip()   # optional

    seats_total = request.form.get("seats_total", "").strip()
    age_range = request.form.get("age_range", "").strip()

    lessons = request.form.get("lessons_count", "").strip()  # optional
    lessons_val = int(lessons) if lessons.isdigit() else None

    if not (title and description and location and seats_total.isdigit()):
        return redirect(url_for("admin_page"))

    image = request.files.get("image")
    image_url = ""
    if image and image.filename:
        filename = f"{int(datetime.now().timestamp())}_{image.filename}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(path)
        image_url = "/" + path.replace("\\", "/")

    conn = get_db()
    conn.execute("""
        INSERT INTO workshops
        (title, description, location, date, time, seats_total, lessons_count, age_range, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title, description, location, date, time,
        int(seats_total), lessons_val, age_range, image_url
    ))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/update", methods=["POST"])
@admin_required
def admin_update_workshop():
    workshop_id = request.form.get("workshop_id", "").strip()

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()

    date = request.form.get("date", "").strip()
    time = request.form.get("time", "").strip()

    seats_total = request.form.get("seats_total", "").strip()
    age_range = request.form.get("age_range", "").strip()

    lessons = request.form.get("lessons_count", "").strip()
    lessons_val = int(lessons) if lessons.isdigit() else None

    if not (workshop_id.isdigit() and title and description and location and seats_total.isdigit()):
        return redirect(url_for("admin_page"))

    image = request.files.get("image")
    new_image_url = None
    if image and image.filename:
        filename = f"{int(datetime.now().timestamp())}_{image.filename}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(path)
        new_image_url = "/" + path.replace("\\", "/")

    conn = get_db()
    if new_image_url:
        conn.execute("""
            UPDATE workshops
            SET title=?, description=?, location=?, date=?, time=?,
                seats_total=?, lessons_count=?, age_range=?, image_url=?
            WHERE id=?
        """, (
            title, description, location, date, time,
            int(seats_total), lessons_val, age_range, new_image_url,
            int(workshop_id)
        ))
    else:
        conn.execute("""
            UPDATE workshops
            SET title=?, description=?, location=?, date=?, time=?,
                seats_total=?, lessons_count=?, age_range=?
            WHERE id=?
        """, (
            title, description, location, date, time,
            int(seats_total), lessons_val, age_range,
            int(workshop_id)
        ))

    conn.commit()
    conn.close()
    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/delete", methods=["POST"])
@admin_required
def admin_delete_workshop():
    workshop_id = request.form.get("workshop_id", "").strip()
    if not workshop_id.isdigit():
        return redirect(url_for("admin_page"))

    conn = get_db()
    conn.execute("DELETE FROM registrations WHERE workshop_id=?", (int(workshop_id),))
    conn.execute("DELETE FROM workshops WHERE id=?", (int(workshop_id),))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/<int:workshop_id>/registrations")
@admin_required
def admin_view_registrations(workshop_id):
    conn = get_db()
    workshop = conn.execute("SELECT * FROM workshops WHERE id=?", (workshop_id,)).fetchone()
    registrations = conn.execute("""
        SELECT * FROM registrations
        WHERE workshop_id=?
        ORDER BY created_at DESC
    """, (workshop_id,)).fetchall()
    conn.close()

    return render_template("registrations.html", workshop=workshop, registrations=registrations)

# ---------------------------
# Registration management (admin)
# ---------------------------
@app.route("/admin/registrations/<int:reg_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_registration(reg_id):
    field = request.form.get("field", "")
    if field not in ("contacted", "canceled", "paid"):
        return redirect(request.referrer or url_for("admin_page"))

    conn = get_db()
    row = conn.execute(
        "SELECT workshop_id, contacted, canceled, paid FROM registrations WHERE id=?",
        (reg_id,)
    ).fetchone()

    if not row:
        conn.close()
        return redirect(url_for("admin_page"))

    new_val = 0 if int(row[field] or 0) == 1 else 1

    if field == "paid" and new_val == 0:
        conn.execute("UPDATE registrations SET paid=?, paid_amount=NULL WHERE id=?", (new_val, reg_id))
    else:
        conn.execute(f"UPDATE registrations SET {field}=? WHERE id=?", (new_val, reg_id))

    conn.commit()
    workshop_id = int(row["workshop_id"])
    conn.close()

    return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))

@app.route("/admin/registrations/<int:reg_id>/set_paid_amount", methods=["POST"])
@admin_required
def admin_set_paid_amount(reg_id):
    amount_raw = (request.form.get("paid_amount") or "").strip()

    conn = get_db()
    row = conn.execute("SELECT workshop_id, paid FROM registrations WHERE id=?", (reg_id,)).fetchone()
    if not row:
        conn.close()
        return redirect(url_for("admin_page"))

    workshop_id = int(row["workshop_id"])
    if int(row["paid"] or 0) != 1:
        conn.close()
        return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))

    amount_val = None
    try:
        amount_val = float(amount_raw)
        if amount_val < 0:
            amount_val = None
    except Exception:
        amount_val = None

    conn.execute("UPDATE registrations SET paid_amount=? WHERE id=?", (amount_val, reg_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))

@app.route("/admin/registrations/<int:reg_id>/delete", methods=["POST"])
@admin_required
def admin_delete_registration(reg_id):
    conn = get_db()
    row = conn.execute("SELECT workshop_id FROM registrations WHERE id=?", (reg_id,)).fetchone()
    if not row:
        conn.close()
        return redirect(url_for("admin_page"))

    workshop_id = int(row["workshop_id"])
    conn.execute("DELETE FROM registrations WHERE id=?", (reg_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))

# ---------------------------
# Run locally
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
