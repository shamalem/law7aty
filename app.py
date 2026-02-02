import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for

# ---------------------------
# App config
# ---------------------------
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

DB_PATH = "law7aty.db"

# ---------------------------
# Database helpers
# ---------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

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
        ORDER BY w.date
    """).fetchall()
    conn.close()

    enriched = []
    for w in workshops:
        seats_left = max(0, w["seats_total"] - w["reg_count"])
        enriched.append(dict(w, seats_left=seats_left))

    return render_template("index.html", workshops=enriched)

@app.route("/register", methods=["POST"])
def register():
    conn = get_db()
    conn.execute("""
        INSERT INTO registrations
        (workshop_id, name, phone, age, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        request.form["workshop_id"],
        request.form["name"],
        request.form["phone"],
        request.form["age"],
        request.form.get("notes", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))
    conn.commit()
    conn.close()
    return redirect(url_for("customer_page"))

# ---------------------------
# ADMIN ROUTES
# ---------------------------
@app.route("/admin")
def admin_page():
    conn = get_db()
    workshops = conn.execute("""
        SELECT w.*,
        (SELECT COUNT(*) FROM registrations r WHERE r.workshop_id = w.id) AS reg_count
        FROM workshops w
        ORDER BY w.date
    """).fetchall()
    conn.close()

    return render_template("admin.html", workshops=workshops)

@app.route("/admin/workshops/add", methods=["POST"])
def admin_add_workshop():
    image = request.files.get("image")
    image_url = ""

    if image and image.filename:
        filename = f"{int(datetime.now().timestamp())}_{image.filename}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(path)
        image_url = "/" + path

    conn = get_db()
    conn.execute("""
        INSERT INTO workshops
        (title, description, location, date, time, seats_total, age_range, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form["title"],
        request.form["description"],
        request.form["location"],
        request.form["date"],
        request.form["time"],
        request.form["seats_total"],
        request.form.get("age_range", ""),
        image_url
    ))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/update", methods=["POST"])
def admin_update_workshop():
    workshop_id = request.form["workshop_id"]
    image = request.files.get("image")

    conn = get_db()

    image_url = None
    if image and image.filename:
        filename = f"{int(datetime.now().timestamp())}_{image.filename}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(path)
        image_url = "/" + path

    if image_url:
        conn.execute("""
            UPDATE workshops
            SET title=?, description=?, location=?, date=?, time=?,
                seats_total=?, age_range=?, image_url=?
            WHERE id=?
        """, (
            request.form["title"],
            request.form["description"],
            request.form["location"],
            request.form["date"],
            request.form["time"],
            request.form["seats_total"],
            request.form.get("age_range", ""),
            image_url,
            workshop_id
        ))
    else:
        conn.execute("""
            UPDATE workshops
            SET title=?, description=?, location=?, date=?, time=?,
                seats_total=?, age_range=?
            WHERE id=?
        """, (
            request.form["title"],
            request.form["description"],
            request.form["location"],
            request.form["date"],
            request.form["time"],
            request.form["seats_total"],
            request.form.get("age_range", ""),
            workshop_id
        ))

    conn.commit()
    conn.close()
    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/delete", methods=["POST"])
def admin_delete_workshop():
    workshop_id = request.form["workshop_id"]
    conn = get_db()
    conn.execute("DELETE FROM registrations WHERE workshop_id=?", (workshop_id,))
    conn.execute("DELETE FROM workshops WHERE id=?", (workshop_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/<int:workshop_id>/registrations")
def admin_view_registrations(workshop_id):
    conn = get_db()
    workshop = conn.execute(
        "SELECT * FROM workshops WHERE id=?", (workshop_id,)
    ).fetchone()

    registrations = conn.execute(
        "SELECT * FROM registrations WHERE workshop_id=? ORDER BY created_at DESC",
        (workshop_id,)
    ).fetchall()
    conn.close()

    return render_template(
        "registrations.html",
        workshop=workshop,
        registrations=registrations
    )

# ---------------------------
# Run locally
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
