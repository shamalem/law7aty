import os
from datetime import datetime
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

app = Flask(__name__)

# --- إعدادات البيئة (Environment Variables) ---
app.secret_key = os.environ.get("SECRET_KEY", "law7aty-secure-key-2026")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
DATABASE_URL = os.environ.get("DATABASE_URL")

# إعدادات سوبابيس لتخزين الصور
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# أصول ثابتة (Assets)
HOME_IMAGE_URL = "/static/home.jpg"
ACRYLIC_IMAGE_URL = "/static/acrylic1.png"
INSTAGRAM_URL = os.environ.get(
    "INSTAGRAM_URL",
    "https://www.instagram.com/law7atiii"
)

# --- مساعدات قاعدة البيانات (Database Helpers) ---
def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Add it in Render Environment Variables.")
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # جدول الورشات
    cur.execute("""
    CREATE TABLE IF NOT EXISTS workshops (
        id SERIAL PRIMARY KEY,
        title TEXT,
        description TEXT,
        location TEXT,
        seats_total INTEGER,
        image_url TEXT
    )
    """)

    # جدول التسجيلات
    cur.execute("""
    CREATE TABLE IF NOT EXISTS registrations (
        id SERIAL PRIMARY KEY,
        workshop_id INTEGER,
        name TEXT,
        phone TEXT,
        age INTEGER,
        notes TEXT,
        created_at TEXT
    )
    """)

    # جدول معرض إبداعات الطلاب
    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_gallery (
        id SERIAL PRIMARY KEY,
        image_url TEXT,
        student_name TEXT
    )
    """)

    conn.commit()
    cur.close()
    conn.close()

# تشغيل تهيئة قاعدة البيانات عند بدء التطبيق
init_db()

# --- مزخرف الحماية (Auth Decorator) ---
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

# --- مسارات الزوار (CUSTOMER ROUTES) ---

@app.route("/")
def customer_page():
    conn = get_db()
    cur = conn.cursor()
    # جلب الورشات مع عدد المسجلين (reg_count) لكل واحدة
    cur.execute("""
        SELECT w.*, 
        (SELECT COUNT(*) FROM registrations r WHERE r.workshop_id = w.id) AS reg_count
        FROM workshops w 
        ORDER BY id DESC
    """)
    workshops = cur.fetchall()
    cur.close()
    conn.close()

    # حساب المقاعد المتبقية (seats_left) لمنع خطأ Jinja2
    enriched_workshops = []
    for w in workshops:
        item = dict(w)
        seats_total = int(w.get('seats_total') or 0)
        reg_count = int(w.get('reg_count') or 0)
        item['seats_left'] = max(0, seats_total - reg_count)
        enriched_workshops.append(item)

    return render_template("index.html", workshops=enriched_workshops, instagram_url=INSTAGRAM_URL)

@app.route("/gallery")
def student_creations():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM student_gallery ORDER BY id DESC")
    images = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("gallery.html", images=images, instagram_url=INSTAGRAM_URL)

@app.route("/register", methods=["POST"])
def register():
    workshop_id = request.form.get("workshop_id")
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    age = request.form.get("age", "").strip()

    if not (workshop_id and name and phone and age):
        return redirect(url_for("customer_page"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO registrations (workshop_id, name, phone, age, created_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (int(workshop_id), name, phone, int(age), datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("customer_page"))

# --- مسارات الإدارة (ADMIN ROUTES) ---

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    msg = ""
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_page"))
        msg = "كلمة المرور غير صحيحة ❌"
    return render_template("admin_login.html", message=msg)

@app.route("/admin")
@admin_required
def admin_page():
    conn = get_db()
    cur = conn.cursor()
    # جلب الورشات مع عدد المسجلين
    cur.execute("""
        SELECT w.*, 
        (SELECT COUNT(*) FROM registrations r WHERE r.workshop_id = w.id) AS reg_count 
        FROM workshops w ORDER BY id DESC
    """)
    workshops = cur.fetchall()
    # جلب صور المعرض
    cur.execute("SELECT * FROM student_gallery ORDER BY id DESC")
    gallery_items = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("admin.html", workshops=workshops, gallery_items=gallery_items)

@app.route("/admin/gallery/add", methods=["POST"])
@admin_required
def admin_add_gallery():
    name = request.form.get("student_name", "").strip()
    file = request.files.get("img")

    if file and supabase_client:
        filename = f"gallery/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        supabase_client.storage.from_('law7aty-gallery').upload(filename, file.read())
        image_url = supabase_client.storage.from_('law7aty-gallery').get_public_url(filename)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO student_gallery (image_url, student_name) VALUES (%s, %s)", 
                    (image_url, name))
        conn.commit()
        cur.close()
        conn.close()

    return redirect(url_for("admin_page"))

@app.route("/admin/gallery/delete", methods=["POST"])
@admin_required
def admin_delete_gallery():
    post_id = request.form.get("post_id")
    if post_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM student_gallery WHERE id = %s", (int(post_id),))
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
    seats_total = request.form.get("seats_total", "0")
    file = request.files.get("workshop_img")
    
    image_url = ACRYLIC_IMAGE_URL
    if file and supabase_client:
        filename = f"workshops/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        supabase_client.storage.from_('law7aty-gallery').upload(filename, file.read())
        image_url = supabase_client.storage.from_('law7aty-gallery').get_public_url(filename)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workshops (title, description, location, seats_total, image_url)
        VALUES (%s, %s, %s, %s, %s)
    """, (title, description, location, int(seats_total), image_url))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("admin_page"))

@app.route("/admin/workshops/delete", methods=["POST"])
@admin_required
def admin_delete_workshop():
    workshop_id = request.form.get("workshop_id")
    if workshop_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM registrations WHERE workshop_id = %s", (int(workshop_id),))
        cur.execute("DELETE FROM workshops WHERE id = %s", (int(workshop_id),))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for("admin_page"))

@app.route("/admin/registrations/<int:workshop_id>")
@admin_required
def admin_view_registrations(workshop_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM workshops WHERE id = %s", (workshop_id,))
    workshop = cur.fetchone()
    cur.execute("SELECT * FROM registrations WHERE workshop_id = %s ORDER BY id DESC", (workshop_id,))
    regs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("registrations.html", workshop=workshop, registrations=regs)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("customer_page"))

if __name__ == "__main__":
    app.run(debug=True)
