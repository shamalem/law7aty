import os
from datetime import datetime
from functools import wraps
from pathlib import Path

import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

DATABASE_URL = os.environ.get("DATABASE_URL")

# On Render Disk, set this env var to: /var/data/uploads
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "static/uploads")
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

INSTAGRAM_URL = os.environ.get(
    "INSTAGRAM_URL",
    "https://www.instagram.com/law7atiii?igsh=MXN5YnQ0bTM0c3l3Zg%3D%3D&utm_source=qr"
)


# ---------------------------
# Database helpers
# ---------------------------
def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Add it in Render Environment Variables.")

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def _safe_add_column(cur, table, col_def_sql):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def_sql}")
    except psycopg2.errors.DuplicateColumn:
        cur.connection.rollback()
    except Exception:
        cur.connection.rollback()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS workshops (
        id SERIAL PRIMARY KEY,
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS registrations (
        id SERIAL PRIMARY KEY,
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY,
        hero_image_url TEXT
    )
    """)

    conn.commit()

    cur.execute("INSERT INTO settings (id, hero_image_url) VALUES (1, '') ON CONFLICT (id) DO NOTHING")
    conn.commit()

    cur.close()
    conn.close()


init_db()


# ---------------------------
# Upload helpers
# ---------------------------
def save_uploaded_file(file, prefix="img"):
    if not file or not file.filename:
        return ""

    filename = secure_filename(file.filename)
    filename = f"{prefix}_{int(datetime.now().timestamp())}_{filename}"

    path = Path(UPLOAD_FOLDER) / filename
    file.save(path)

    return url_for("uploaded_file", filename=filename)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ---------------------------
# Admin auth
# ---------------------------
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------
# Customer routes
# ---------------------------
@app.route("/")
def customer_page():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT w.*,
        (
            SELECT COUNT(*)
            FROM registrations r
            WHERE r.workshop_id = w.id
        ) AS reg_count
        FROM workshops w
        ORDER BY COALESCE(w.date, '') ASC, w.id DESC
    """)
    workshops = cur.fetchall()

    cur.execute("SELECT hero_image_url FROM settings WHERE id = 1")
    settings = cur.fetchone()

    cur.close()
    conn.close()

    hero_image_url = settings["hero_image_url"] if settings and settings["hero_image_url"] else ""

    enriched = []
    for w in workshops:
        reg_count = int(w["reg_count"] or 0)
        seats_total = int(w["seats_total"] or 0)
        seats_left = max(0, seats_total - reg_count)

        item = dict(w)
        item["seats_left"] = seats_left
        enriched.append(item)

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
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO registrations
        (workshop_id, name, phone, age, notes, created_at, contacted, canceled, paid, paid_amount)
        VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 0, NULL)
    """, (
        int(workshop_id),
        name,
        phone,
        int(age),
        notes,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("customer_page"))


# ---------------------------
# Admin login/logout
# ---------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    msg = ""

    if request.method == "POST":
        password = request.form.get("password", "")

        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_page"))

        msg = "كلمة المرور غير صحيحة ❌"

    return render_template("admin_login.html", message=msg)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("customer_page"))


# ---------------------------
# Admin routes
# ---------------------------
@app.route("/admin")
@admin_required
def admin_page():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT w.*,
        (
            SELECT COUNT(*)
            FROM registrations r
            WHERE r.workshop_id = w.id
        ) AS reg_count
        FROM workshops w
        ORDER BY COALESCE(w.date, '') ASC, w.id DESC
    """)
    workshops = cur.fetchall()

    cur.execute("SELECT hero_image_url FROM settings WHERE id = 1")
    settings = cur.fetchone()

    cur.close()
    conn.close()

    hero_image_url = settings["hero_image_url"] if settings and settings["hero_image_url"] else ""

    return render_template(
        "admin.html",
        workshops=workshops,
        hero_image_url=hero_image_url
    )


@app.route("/admin/settings/hero", methods=["POST"])
@admin_required
def admin_update_hero():
    image = request.files.get("hero_image")
    hero_url = save_uploaded_file(image, "hero")

    if hero_url:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("UPDATE settings SET hero_image_url = %s WHERE id = 1", (hero_url,))

        conn.commit()
        cur.close()
        conn.close()

    return redirect(url_for("admin_page"))


@app.route("/admin/workshops/add", methods=["POST"])
@admin_required
def admin_add_workshop():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()

    date = request.form.get("date", "").strip()
    time = request.form.get("time", "").strip()

    seats_total = request.form.get("seats_total", "").strip()
    age_range = request.form.get("age_range", "").strip()

    lessons = request.form.get("lessons_count", "").strip()
    lessons_val = int(lessons) if lessons.isdigit() else None

    if not (title and description and location and seats_total.isdigit()):
        return redirect(url_for("admin_page"))

    image = request.files.get("image")
    image_url = save_uploaded_file(image, "workshop")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO workshops
        (title, description, location, date, time, seats_total, lessons_count, age_range, image_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        title,
        description,
        location,
        date,
        time,
        int(seats_total),
        lessons_val,
        age_range,
        image_url
    ))

    conn.commit()
    cur.close()
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
    new_image_url = save_uploaded_file(image, "workshop")

    conn = get_db()
    cur = conn.cursor()

    if new_image_url:
        cur.execute("""
            UPDATE workshops
            SET title = %s,
                description = %s,
                location = %s,
                date = %s,
                time = %s,
                seats_total = %s,
                lessons_count = %s,
                age_range = %s,
                image_url = %s
            WHERE id = %s
        """, (
            title,
            description,
            location,
            date,
            time,
            int(seats_total),
            lessons_val,
            age_range,
            new_image_url,
            int(workshop_id)
        ))
    else:
        cur.execute("""
            UPDATE workshops
            SET title = %s,
                description = %s,
                location = %s,
                date = %s,
                time = %s,
                seats_total = %s,
                lessons_count = %s,
                age_range = %s
            WHERE id = %s
        """, (
            title,
            description,
            location,
            date,
            time,
            int(seats_total),
            lessons_val,
            age_range,
            int(workshop_id)
        ))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("admin_page"))


@app.route("/admin/workshops/delete", methods=["POST"])
@admin_required
def admin_delete_workshop():
    workshop_id = request.form.get("workshop_id", "").strip()

    if not workshop_id.isdigit():
        return redirect(url_for("admin_page"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM registrations WHERE workshop_id = %s", (int(workshop_id),))
    cur.execute("DELETE FROM workshops WHERE id = %s", (int(workshop_id),))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("admin_page"))


@app.route("/admin/workshops/<int:workshop_id>/registrations")
@admin_required
def admin_view_registrations(workshop_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM workshops WHERE id = %s", (workshop_id,))
    workshop = cur.fetchone()

    cur.execute("""
        SELECT *
        FROM registrations
        WHERE workshop_id = %s
        ORDER BY created_at DESC
    """, (workshop_id,))
    registrations = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "registrations.html",
        workshop=workshop,
        registrations=registrations
    )


# ---------------------------
# Registration management
# ---------------------------
@app.route("/admin/registrations/<int:reg_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_registration(reg_id):
    field = request.form.get("field", "")

    if field not in ("contacted", "canceled", "paid"):
        return redirect(request.referrer or url_for("admin_page"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT workshop_id, contacted, canceled, paid FROM registrations WHERE id = %s",
        (reg_id,)
    )
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return redirect(url_for("admin_page"))

    current_val = int(row[field] or 0)
    new_val = 0 if current_val == 1 else 1

    if field == "paid" and new_val == 0:
        cur.execute(
            "UPDATE registrations SET paid = %s, paid_amount = NULL WHERE id = %s",
            (new_val, reg_id)
        )
    else:
        cur.execute(
            f"UPDATE registrations SET {field} = %s WHERE id = %s",
            (new_val, reg_id)
        )

    conn.commit()

    workshop_id = int(row["workshop_id"])

    cur.close()
    conn.close()

    return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))


@app.route("/admin/registrations/<int:reg_id>/set_paid_amount", methods=["POST"])
@admin_required
def admin_set_paid_amount(reg_id):
    amount_raw = (request.form.get("paid_amount") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT workshop_id, paid FROM registrations WHERE id = %s", (reg_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return redirect(url_for("admin_page"))

    workshop_id = int(row["workshop_id"])

    if int(row["paid"] or 0) != 1:
        cur.close()
        conn.close()
        return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))

    try:
        amount_val = float(amount_raw)
        if amount_val < 0:
            amount_val = None
    except Exception:
        amount_val = None

    cur.execute(
        "UPDATE registrations SET paid_amount = %s WHERE id = %s",
        (amount_val, reg_id)
    )

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))


@app.route("/admin/registrations/<int:reg_id>/delete", methods=["POST"])
@admin_required
def admin_delete_registration(reg_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT workshop_id FROM registrations WHERE id = %s", (reg_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return redirect(url_for("admin_page"))

    workshop_id = int(row["workshop_id"])

    cur.execute("DELETE FROM registrations WHERE id = %s", (reg_id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("admin_view_registrations", workshop_id=workshop_id))


# ---------------------------
# Health check
# ---------------------------
@app.route("/health")
def health():
    return {
        "status": "ok",
        "database": "postgres",
        "upload_folder": UPLOAD_FOLDER
    }


if __name__ == "__main__":
    app.run(debug=True)
