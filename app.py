import os
import json
import sqlite3
import secrets
import shutil
import urllib.parse
import urllib.request
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "novin.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "novin-secret-key-change-this")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

SITE_NAME = "کافی نت آنلاین نوین"
MANAGER = "احمد محمدی مهر"
PHONE = "۰۹۹۲۰۳۴۵۱۳۹"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "123456")
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except Exception:
            pass


def to_latin_digits(s):
    if s is None:
        return ""
    s = str(s)
    p = "۰۱۲۳۴۵۶۷۸۹"
    a = "٠١٢٣٤٥٦٧٨٩"
    out = []
    for c in s:
        if c in p:
            out.append(str(p.index(c)))
        elif c in a:
            out.append(str(a.index(c)))
        else:
            out.append(c)
    return "".join(out)


def create_tables():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, value TEXT DEFAULT '')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        full_name TEXT DEFAULT '', role TEXT NOT NULL DEFAULT 'expert', active INTEGER NOT NULL DEFAULT 1,
        phone TEXT DEFAULT '', allowed_services TEXT DEFAULT '[]', allowed_sections TEXT DEFAULT '[]',
        expires_at TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT DEFAULT '',
        national_id TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT DEFAULT '',
        description TEXT DEFAULT '', price INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1, fields_json TEXT DEFAULT '[]', documents_json TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, service_id INTEGER, expert_id INTEGER,
        tracking_code TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'در انتظار بررسی',
        customer_note TEXT DEFAULT '', admin_note TEXT DEFAULT '', estimated_time TEXT DEFAULT '',
        total_price INTEGER DEFAULT 0, paid_price INTEGER DEFAULT 0, discount_code TEXT DEFAULT '',
        discount_amount INTEGER DEFAULT 0, payment_mode TEXT DEFAULT 'gateway', is_credit INTEGER DEFAULT 0,
        payment_confirmed INTEGER DEFAULT 0, form_data TEXT DEFAULT '{}', documents TEXT DEFAULT '[]',
        rejected_fields TEXT DEFAULT '[]', personal_note TEXT DEFAULT '', receipt_file TEXT DEFAULT '',
        invoice_code TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, request_id INTEGER,
        sender TEXT NOT NULL, sender_name TEXT DEFAULT '', message TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS discounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, kind TEXT NOT NULL DEFAULT 'percent',
        value INTEGER NOT NULL DEFAULT 0, max_uses INTEGER DEFAULT 0, used_count INTEGER DEFAULT 0,
        start_date TEXT DEFAULT '', end_date TEXT DEFAULT '', is_credit INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, customer_phone TEXT DEFAULT '',
        title TEXT DEFAULT '', body TEXT DEFAULT '', is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sms_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, body TEXT, status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    cols = [
        ("users", "full_name", "TEXT DEFAULT ''"),
        ("users", "phone", "TEXT DEFAULT ''"),
        ("users", "allowed_services", "TEXT DEFAULT '[]'"),
        ("users", "allowed_sections", "TEXT DEFAULT '[]'"),
        ("users", "expires_at", "TEXT DEFAULT ''"),
        ("customers", "national_id", "TEXT DEFAULT ''"),
        ("requests", "admin_note", "TEXT DEFAULT ''"),
        ("requests", "estimated_time", "TEXT DEFAULT ''"),
        ("requests", "discount_code", "TEXT DEFAULT ''"),
        ("requests", "discount_amount", "INTEGER DEFAULT 0"),
        ("requests", "expert_id", "INTEGER"),
        ("requests", "payment_mode", "TEXT DEFAULT 'gateway'"),
        ("requests", "is_credit", "INTEGER DEFAULT 0"),
        ("requests", "payment_confirmed", "INTEGER DEFAULT 0"),
        ("requests", "rejected_fields", "TEXT DEFAULT '[]'"),
        ("requests", "personal_note", "TEXT DEFAULT ''"),
        ("requests", "receipt_file", "TEXT DEFAULT ''"),
        ("requests", "invoice_code", "TEXT DEFAULT ''"),
        ("messages", "sender_name", "TEXT DEFAULT ''"),
        ("discounts", "is_credit", "INTEGER DEFAULT 0"),
    ]
    for table, column, definition in cols:
        add_column_if_missing(conn, table, column, definition)

    defaults = {
        "site_name": SITE_NAME, "manager": MANAGER, "phone": PHONE, "logo": "",
        "default_payment_mode": "gateway", "payment_merchant_code": "",
        "sms_api_key": "", "sms_phone": "", "backup_email": "",
        "seal_image": "", "theme_primary": "#0f5132", "theme_font": "Tahoma",
        "last_auto_backup": "",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))

    if not conn.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone():
        conn.execute(
            "INSERT INTO users(username, password, full_name, role, active) VALUES (?,?,?,?,1)",
            ("admin", generate_password_hash(ADMIN_PASSWORD), "مدیر اصلی", "admin")
        )
    conn.commit()
    conn.close()


def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    conn.commit()
    conn.close()


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, full_name, role, active, phone, allowed_services, allowed_sections, expires_at FROM users WHERE id=?",
        (uid,)
    ).fetchone()
    conn.close()
    if not user or not user["active"]:
        return None
    if user["expires_at"]:
        try:
            if datetime.now().strftime("%Y-%m-%d") > user["expires_at"]:
                return None
        except Exception:
            pass
    return user


@app.context_processor
def inject_globals():
    s = get_settings()
    return {
        "site_settings": s,
        "site_name": s.get("site_name", SITE_NAME),
        "manager": s.get("manager", MANAGER),
        "phone": s.get("phone", PHONE),
        "theme_primary": s.get("theme_primary", "#0f5132"),
        "theme_font": s.get("theme_font", "Tahoma"),
        "current_user": get_current_user(),
    }


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not get_current_user():
            return redirect(url_for("admin_login"))
        return f(*a, **k)
    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        u = get_current_user()
        if not u or u["role"] != "admin":
            flash("فقط مدیر.", "error")
            return redirect(url_for("admin"))
        return f(*a, **k)
    return w


def generate_tracking_code():
    while True:
        code = str(secrets.randbelow(9000) + 1000)
        conn = get_db()
        ex = conn.execute("SELECT id FROM requests WHERE tracking_code=?", (code,)).fetchone()
        conn.close()
        if not ex:
            return code


def to_int(v, d=0):
    try:
        return int(to_latin_digits(str(v)).replace(",", "").strip())
    except Exception:
        return d


def parse_json_list(v):
    if not v:
        return []
    try:
        r = json.loads(v)
        return r if isinstance(r, list) else []
    except Exception:
        return []


def parse_json_dict(v):
    if not v:
        return {}
    try:
        r = json.loads(v)
        return r if isinstance(r, dict) else {}
    except Exception:
        return {}


def save_uploaded_files(files):
    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        fn = secure_filename(f.filename)
        ext = os.path.splitext(fn)[1].lower()
        if ext not in ALLOWED_EXT:
            continue
        name = secrets.token_hex(8) + "_" + fn
        f.save(os.path.join(UPLOAD_FOLDER, name))
        saved.append(name)
    return saved


def send_sms(phone, text):
    phone = to_latin_digits((phone or "").strip().replace(" ", ""))
    text = (text or "").strip()
    if not phone or not text:
        return False
    s = get_settings()
    api_key = (s.get("sms_api_key") or "").strip()
    line = (s.get("sms_phone") or "").strip()
    status = "logged"
    ok = False
    if api_key:
        try:
            url = (
                f"https://api.kavenegar.com/v1/{urllib.parse.quote(api_key)}/sms/send.json"
                f"?receptor={urllib.parse.quote(phone)}"
                f"&message={urllib.parse.quote(text)}"
            )
            if line:
                url += f"&sender={urllib.parse.quote(line)}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                status = "sent" if resp.status == 200 else f"http_{resp.status}"
                ok = resp.status == 200
                app.logger.info("SMS: %s", body[:400])
        except Exception as e:
            status = f"error:{e}"
            app.logger.exception("SMS failed")
    try:
        conn = get_db()
        conn.execute("INSERT INTO sms_log (phone, body, status) VALUES (?,?,?)", (phone, text, status))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return ok


def add_notification(user_id=None, customer_phone="", title="", body=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO notifications (user_id, customer_phone, title, body) VALUES (?,?,?,?)",
        (user_id, to_latin_digits(customer_phone or ""), title, body)
    )
    conn.commit()
    conn.close()


def notify_staff(title, body, service_id=None, only_accountant=False):
    conn = get_db()
    users = conn.execute("SELECT id, role, allowed_services FROM users WHERE active=1").fetchall()
    conn.close()
    for u in users:
        if only_accountant:
            if u["role"] in ("admin", "accountant"):
                add_notification(user_id=u["id"], title=title, body=body)
            continue
        if u["role"] in ("admin", "accountant"):
            add_notification(user_id=u["id"], title=title, body=body)
        elif u["role"] == "expert":
            allowed = parse_json_list(u["allowed_services"] or "[]")
            if not service_id or not allowed or int(service_id) in [int(x) for x in allowed]:
                add_notification(user_id=u["id"], title=title, body=body)


def maybe_auto_backup():
    s = get_settings()
    last = s.get("last_auto_backup") or ""
    now = datetime.now()
    try:
        if last:
            prev = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            if (now - prev).total_seconds() < 1800:
                return
    except Exception:
        pass
    try:
        path = os.path.join(BACKUP_FOLDER, f"auto_{now.strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(DATABASE, path)
        set_setting("last_auto_backup", now.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def create_request_core(service_id, name, phone, national_id, customer_note, discount_code, form_data, uploaded):
    phone = to_latin_digits(phone)
    national_id = to_latin_digits(national_id)
    discount_code = to_latin_digits(discount_code).upper() if discount_code else ""

    conn = get_db()
    service_row = conn.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    if not service_row:
        conn.close()
        return None

    customer = None
    if phone:
        customer = conn.execute("SELECT * FROM customers WHERE phone=? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
    if customer:
        customer_id = customer["id"]
        conn.execute("UPDATE customers SET name=?, national_id=? WHERE id=?", (name, national_id, customer_id))
    else:
        cur = conn.execute("INSERT INTO customers (name, phone, national_id) VALUES (?,?,?)", (name, phone, national_id))
        customer_id = cur.lastrowid

    payment_mode = get_settings().get("default_payment_mode", "gateway")
    base_price = to_int(service_row["price"])
    discount_amount = 0
    is_credit = 0

    if discount_code:
        discount = conn.execute("SELECT * FROM discounts WHERE code=? AND active=1", (discount_code,)).fetchone()
        if discount:
            today = datetime.now().strftime("%Y-%m-%d")
            valid = True
            if discount["start_date"] and today < discount["start_date"]:
                valid = False
            if discount["end_date"] and today > discount["end_date"]:
                valid = False
            if discount["max_uses"] > 0 and discount["used_count"] >= discount["max_uses"]:
                valid = False
            if valid:
                if discount["is_credit"]:
                    is_credit = 1
                elif discount["kind"] == "percent":
                    discount_amount = int(base_price * discount["value"] / 100)
                else:
                    discount_amount = min(base_price, discount["value"])
                conn.execute("UPDATE discounts SET used_count=used_count+1 WHERE id=?", (discount["id"],))

    final_price = max(0, base_price - discount_amount)
    tracking_code = generate_tracking_code()
    payment_confirmed = 0
    if is_credit or final_price == 0:
        status = "در انتظار بررسی"
        payment_confirmed = 1
    else:
        status = "در انتظار پرداخت"
        payment_confirmed = 0

    cur = conn.execute(
        """INSERT INTO requests
        (customer_id, service_id, tracking_code, status, customer_note, total_price, paid_price,
         discount_code, discount_amount, payment_mode, is_credit, payment_confirmed, form_data, documents)
        VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?,?)""",
        (customer_id, service_id, tracking_code, status, customer_note, final_price,
         discount_code, discount_amount, payment_mode, is_credit, payment_confirmed,
         json.dumps(form_data, ensure_ascii=False), json.dumps(uploaded, ensure_ascii=False))
    )
    rid = cur.lastrowid
    conn.execute(
        "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
        (customer_id, rid, "system", "سامانه", f"درخواست با کد {tracking_code} ثبت شد. وضعیت: {status}")
    )
    conn.commit()
    conn.close()

    sms_text = f"کافی‌نت نوین\nکد پیگیری: {tracking_code}\nوضعیت: {status}"
    send_sms(phone, sms_text)
    add_notification(customer_phone=phone, title="ثبت درخواست", body=sms_text)

    if payment_confirmed:
        notify_staff("درخواست جدید", f"کد {tracking_code} — {name}", service_id)
    else:
        # اول حسابدار و مدیر
        notify_staff("در انتظار تأیید پرداخت", f"کد {tracking_code} — {name}", service_id, only_accountant=True)

    return {
        "id": rid, "tracking_code": tracking_code, "status": status,
        "total_price": final_price, "payment_mode": payment_mode,
        "payment_confirmed": payment_confirmed, "customer_name": name,
        "service_name": service_row["name"], "phone": phone, "customer_phone": phone
    }


@app.before_request
def _auto_backup_hook():
    if request.endpoint and not str(request.endpoint).startswith("static"):
        try:
            maybe_auto_backup()
        except Exception:
            pass


@app.route("/")
def index():
    conn = get_db()
    services = conn.execute("SELECT * FROM services WHERE active=1 ORDER BY sort_order ASC, id DESC").fetchall()
    conn.close()
    return render_template("index.html", services=services, settings=get_settings())


@app.route("/service/<int:service_id>", methods=["GET", "POST"])
def service(service_id):
    conn = get_db()
    service_row = conn.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    conn.close()
    if not service_row:
        abort(404)
    fields = parse_json_list(service_row["fields_json"])
    documents = parse_json_list(service_row["documents_json"])

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = to_latin_digits(request.form.get("phone", "").strip())
        national_id = to_latin_digits(request.form.get("national_id", "").strip())
        customer_note = request.form.get("customer_note", "").strip()
        discount_code = to_latin_digits(request.form.get("discount_code", "").strip()).upper()
        if not name:
            flash("نام را وارد کنید.", "error")
            return redirect(url_for("service", service_id=service_id))
        form_data = {}
        for i, field in enumerate(fields, start=1):
            key = f"field_{i}"
            label = field.get("label") or field.get("name") or key
            form_data[label] = to_latin_digits(request.form.get(key, ""))
        uploaded = save_uploaded_files(request.files.getlist("documents"))
        result = create_request_core(service_id, name, phone, national_id, customer_note, discount_code, form_data, uploaded)
        if not result:
            flash("خطا در ثبت.", "error")
            return redirect(url_for("index"))
        if result["payment_mode"] == "gateway" and result["total_price"] > 0 and not result["payment_confirmed"]:
            return redirect(url_for("payment_page", tracking_code=result["tracking_code"]))
        return render_template("tracking.html", result=result, history=[], tickets=[], created=True, settings=get_settings())

    return render_template("service.html", service=service_row, fields=fields, documents=documents, settings=get_settings())


@app.route("/payment/<tracking_code>", methods=["GET", "POST"])
def payment_page(tracking_code):
    conn = get_db()
    row = conn.execute(
        """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
           FROM requests r LEFT JOIN customers c ON c.id=r.customer_id
           LEFT JOIN services s ON s.id=r.service_id WHERE r.tracking_code=?""",
        (tracking_code,)
    ).fetchone()
    conn.close()
    if not row:
        abort(404)
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "UPDATE requests SET payment_confirmed=1, paid_price=total_price, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            ("در انتظار بررسی", row["id"])
        )
        conn.execute(
            "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
            (row["customer_id"], row["id"], "system", "سامانه", "پرداخت تأیید شد.")
        )
        conn.commit()
        conn.close()
        notify_staff("پرداخت تأیید شد", f"کد {tracking_code}", row["service_id"])
        send_sms(row["customer_phone"], f"پرداخت کد {tracking_code} تأیید شد.")
        flash("پرداخت ثبت شد.", "success")
        return redirect(url_for("tracking"))
    return render_template("payment.html", req=row, settings=get_settings())


@app.route("/tracking", methods=["GET", "POST"])
def tracking():
    result = None
    history = []
    tickets = []
    if request.method == "POST":
        tracking_code = to_latin_digits(request.form.get("tracking_code", "").strip())
        conn = get_db()
        if tracking_code:
            result = conn.execute(
                """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, c.national_id AS customer_national_id,
                          c.id AS cid, s.name AS service_name, u.full_name AS expert_name
                   FROM requests r
                   LEFT JOIN customers c ON c.id=r.customer_id
                   LEFT JOIN services s ON s.id=r.service_id
                   LEFT JOIN users u ON u.id=r.expert_id
                   WHERE r.tracking_code=?""",
                (tracking_code,)
            ).fetchone()
            if result:
                nid = result["customer_national_id"] or ""
                if nid:
                    history = conn.execute(
                        """SELECT r.tracking_code, r.status, r.created_at, s.name AS service_name
                           FROM requests r LEFT JOIN services s ON s.id=r.service_id
                           JOIN customers c ON c.id=r.customer_id
                           WHERE c.national_id=? ORDER BY r.id DESC LIMIT 30""",
                        (nid,)
                    ).fetchall()
                if result["customer_id"]:
                    tickets = conn.execute(
                        """SELECT * FROM messages WHERE customer_id=? AND request_id IS NULL
                           ORDER BY id DESC LIMIT 40""",
                        (result["customer_id"],)
                    ).fetchall()
            else:
                flash("کد پیدا نشد.", "error")
        conn.close()
    return render_template("tracking.html", result=result, history=history, tickets=tickets, settings=get_settings())


@app.route("/api/request-status/<tracking_code>")
def api_request_status(tracking_code):
    conn = get_db()
    row = conn.execute(
        "SELECT status, estimated_time, admin_note FROM requests WHERE tracking_code=?",
        (to_latin_digits(tracking_code),)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({}), 404
    return jsonify(dict(row))


@app.route("/resubmit/<tracking_code>", methods=["GET", "POST"])
def resubmit_docs(tracking_code):
    conn = get_db()
    row = conn.execute(
        """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
           FROM requests r LEFT JOIN customers c ON c.id=r.customer_id
           LEFT JOIN services s ON s.id=r.service_id WHERE r.tracking_code=?""",
        (to_latin_digits(tracking_code),)
    ).fetchone()
    if not row:
        conn.close()
        abort(404)
    if row["status"] != "نقص مدارک":
        conn.close()
        flash("فقط در نقص مدارک.", "error")
        return redirect(url_for("tracking"))
    form_data = parse_json_dict(row["form_data"])
    rejected = parse_json_list(row["rejected_fields"])
    if request.method == "POST":
        new_data = dict(form_data)
        for k in list(form_data.keys()):
            val = request.form.get("fix_" + k)
            if val is not None:
                new_data[k] = to_latin_digits(val)
        note = request.form.get("customer_note", "").strip()
        uploaded = save_uploaded_files(request.files.getlist("documents"))
        old_docs = parse_json_list(row["documents"])
        conn.execute(
            """UPDATE requests SET form_data=?, documents=?, customer_note=?, status=?, rejected_fields='[]',
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (json.dumps(new_data, ensure_ascii=False), json.dumps(old_docs + uploaded, ensure_ascii=False),
             note or row["customer_note"], "در انتظار بررسی", row["id"])
        )
        conn.execute(
            "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
            (row["customer_id"], row["id"], "customer", row["customer_name"] or "مشتری", note or "اصلاح ارسال شد.")
        )
        conn.commit()
        conn.close()
        notify_staff("اصلاح پرونده", f"کد {tracking_code}", row["service_id"])
        flash("ارسال شد.", "success")
        return redirect(url_for("tracking"))
    conn.close()
    return render_template("resubmit.html", req=row, form_data=form_data, rejected=rejected)


@app.route("/support", methods=["GET", "POST"])
def support():
    conn = get_db()
    experts = conn.execute(
        "SELECT id, username, full_name, role FROM users WHERE active=1 AND role IN ('admin','expert','accountant') ORDER BY role, username"
    ).fetchall()
    conn.close()
    if request.method == "POST":
        expert_id = request.form.get("expert_id")
        name = request.form.get("name", "").strip()
        phone = to_latin_digits(request.form.get("phone", "").strip())
        message = request.form.get("message", "").strip()
        if not all([expert_id, name, phone, message]):
            flash("همه فیلدها لازم است.", "error")
            return redirect(url_for("support"))
        conn = get_db()
        c = conn.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
        if c:
            cid = c["id"]
            conn.execute("UPDATE customers SET name=? WHERE id=?", (name, cid))
        else:
            cur = conn.execute("INSERT INTO customers (name, phone) VALUES (?,?)", (name, phone))
            cid = cur.lastrowid
        expert = conn.execute("SELECT full_name, username FROM users WHERE id=?", (expert_id,)).fetchone()
        ename = (expert["full_name"] or expert["username"]) if expert else ""
        conn.execute(
            "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
            (cid, None, "customer", name, f"[به {ename}] {message}")
        )
        conn.commit()
        conn.close()
        add_notification(user_id=int(expert_id), title="پشتیبانی", body=f"{name}: {message}")
        flash("ارسال شد.", "success")
        return redirect(url_for("index"))
    return render_template("support.html", experts=experts, settings=get_settings())


@app.route("/customer/notifications")
def customer_notifications():
    phone = to_latin_digits(request.args.get("phone", "").strip())
    if not phone:
        return jsonify({"items": []})
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE customer_phone=? AND is_read=0 ORDER BY id DESC LIMIT 20", (phone,)
    ).fetchall()
    data = [dict(r) for r in rows]
    if rows:
        conn.execute("UPDATE notifications SET is_read=1 WHERE customer_phone=? AND is_read=0", (phone,))
        conn.commit()
    conn.close()
    return jsonify({"items": data})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if get_current_user():
        return redirect(url_for("admin"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("admin"))
        flash("نام کاربری یا رمز اشتباه است.", "error")
    return render_template("admin_login.html", settings=get_settings())


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        flash("پس از اتصال پیامک ارسال می‌شود.", "success")
        return redirect(url_for("admin_login"))
    return render_template("forgot.html", title="فراموشی رمز", field_name="username", field_label="نام کاربری")


@app.route("/admin/forgot-username", methods=["GET", "POST"])
def forgot_username():
    if request.method == "POST":
        flash("پس از اتصال پیامک ارسال می‌شود.", "success")
        return redirect(url_for("admin_login"))
    return render_template("forgot.html", title="فراموشی نام کاربری", field_name="phone", field_label="موبایل")


@app.route("/admin")
@login_required
def admin():
    user = get_current_user()
    status_filter = request.args.get("status", "").strip()
    conn = get_db()

    if user["role"] == "accountant":
        q = """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
               FROM requests r LEFT JOIN customers c ON c.id=r.customer_id
               LEFT JOIN services s ON s.id=r.service_id
               WHERE r.payment_confirmed=0 AND r.status='در انتظار پرداخت'"""
        params = []
        if status_filter:
            q += " AND r.status=?"
            params.append(status_filter)
        q += " ORDER BY r.id DESC"
        requests_rows = conn.execute(q, params).fetchall()
        allowed_sections = ["accounting", "requests", "password"]
    elif user["role"] == "admin":
        q = """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
               FROM requests r LEFT JOIN customers c ON c.id=r.customer_id
               LEFT JOIN services s ON s.id=r.service_id WHERE 1=1"""
        params = []
        if status_filter:
            q += " AND r.status=?"
            params.append(status_filter)
        q += " ORDER BY r.id DESC"
        requests_rows = conn.execute(q, params).fetchall()
        allowed_sections = None
    else:
        allowed = parse_json_list(user["allowed_services"] or "[]")
        allowed_sections = parse_json_list(user["allowed_sections"] or "[]")
        if allowed:
            ph = ",".join("?" * len(allowed))
            params = [int(x) for x in allowed]
            q = f"""SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, s.name AS service_name
                    FROM requests r LEFT JOIN customers c ON c.id=r.customer_id
                    LEFT JOIN services s ON s.id=r.service_id
                    WHERE r.service_id IN ({ph}) AND r.payment_confirmed=1"""
            if status_filter:
                q += " AND r.status=?"
                params.append(status_filter)
            q += " ORDER BY r.id DESC"
            requests_rows = conn.execute(q, params).fetchall()
        else:
            requests_rows = []

    pending_warn = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status NOT IN ('انجام شد','رد شد','انصراف مشتری')"
    ).fetchone()[0]
    customers = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    services = conn.execute("SELECT * FROM services ORDER BY sort_order ASC, id DESC").fetchall()
    users = conn.execute(
        "SELECT id, username, full_name, role, active, phone, allowed_services, allowed_sections, expires_at FROM users ORDER BY id DESC"
    ).fetchall()
    discounts = conn.execute("SELECT * FROM discounts ORDER BY id DESC").fetchall()
    total_income = conn.execute("SELECT COALESCE(SUM(paid_price),0) FROM requests").fetchone()[0]
    total_debt = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN total_price>paid_price THEN total_price-paid_price ELSE 0 END),0) FROM requests"
    ).fetchone()[0]
    debts = conn.execute("""
        SELECT r.id, r.tracking_code, r.total_price, r.paid_price, (r.total_price-r.paid_price) AS debt,
               c.name AS customer_name, c.phone AS customer_phone, c.national_id AS customer_national_id, s.name AS service_name
        FROM requests r LEFT JOIN customers c ON c.id=r.customer_id LEFT JOIN services s ON s.id=r.service_id
        WHERE r.total_price > r.paid_price ORDER BY r.id DESC""").fetchall()
    support_messages = conn.execute("""
        SELECT m.*, c.name AS customer_name, c.phone AS customer_phone FROM messages m
        LEFT JOIN customers c ON c.id=m.customer_id WHERE m.request_id IS NULL ORDER BY m.id DESC LIMIT 100
    """).fetchall()
    conn.close()
    return render_template(
        "admin.html", requests=requests_rows, customers=customers, services=services, users=users,
        discounts=discounts, debts=debts, total_income=total_income, total_debt=total_debt,
        support_messages=support_messages, settings=get_settings(), current_user=user,
        allowed_sections=allowed_sections, status_filter=status_filter, pending_warn=pending_warn
    )


@app.route("/admin/api/live")
@login_required
def admin_live():
    user = get_current_user()
    conn = get_db()
    if user["role"] in ("admin", "accountant"):
        cnt = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    else:
        allowed = parse_json_list(user["allowed_services"] or "[]")
        if allowed:
            ph = ",".join("?" * len(allowed))
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM requests WHERE service_id IN ({ph}) AND payment_confirmed=1",
                [int(x) for x in allowed]
            ).fetchone()[0]
        else:
            cnt = 0
    notif = conn.execute(
        "SELECT id, title, body FROM notifications WHERE user_id=? AND is_read=0 ORDER BY id DESC LIMIT 10",
        (user["id"],)
    ).fetchall()
    if notif:
        conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0", (user["id"],))
        conn.commit()
    conn.close()
    return jsonify({"count": cnt, "notifications": [dict(x) for x in notif]})


@app.route("/admin/notifications")
@login_required
def admin_notifications():
    return admin_live()

@app.route("/admin/settings/save", methods=["POST"])
@login_required
def admin_settings_save():
    for key in ["site_name", "manager", "phone", "theme_primary", "theme_font"]:
        if key in request.form:
            set_setting(key, request.form.get(key, "").strip())
    logo = request.files.get("logo")
    if logo and logo.filename:
        fn = secrets.token_hex(8) + "_" + secure_filename(logo.filename)
        if fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            logo.save(os.path.join(UPLOAD_FOLDER, fn))
            set_setting("logo", fn)
    seal = request.files.get("seal_image")
    if seal and seal.filename:
        fn = secrets.token_hex(8) + "_" + secure_filename(seal.filename)
        if fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            seal.save(os.path.join(UPLOAD_FOLDER, fn))
            set_setting("seal_image", fn)
    flash("ذخیره شد.", "success")
    return redirect(url_for("admin") + "#settings")


@app.route("/admin/gateway-settings", methods=["POST"])
@login_required
def gateway_settings():
    set_setting("default_payment_mode", request.form.get("default_payment_mode", "gateway").strip())
    set_setting("payment_merchant_code", request.form.get("payment_merchant_code", "").strip())
    set_setting("sms_api_key", request.form.get("sms_api_key", "").strip())
    set_setting("sms_phone", request.form.get("sms_phone", "").strip())
    flash("ذخیره شد.", "success")
    return redirect(url_for("admin") + "#gateway")


@app.route("/admin/sms-test", methods=["POST"])
@login_required
def sms_test():
    phone = to_latin_digits(request.form.get("test_phone", "").strip())
    text = request.form.get("test_text", "تست پیامک کافی‌نت نوین").strip()
    ok = send_sms(phone, text)
    flash("تست پیامک انجام شد." if ok else "خطا در ارسال — لاگ را بررسی کنید.", "success" if ok else "error")
    return redirect(url_for("admin") + "#gateway")


@app.route("/admin/service/save", methods=["POST"])
@login_required
def admin_service_save():
    name = request.form.get("name", "").strip()
    if not name:
        flash("نام لازم است.", "error")
        return redirect(url_for("admin") + "#add-service")
    fields_json = request.form.get("fields_json", "[]")
    documents_json = request.form.get("documents_json", "[]")
    try:
        json.loads(fields_json)
    except Exception:
        fields_json = "[]"
    try:
        json.loads(documents_json)
    except Exception:
        documents_json = "[]"
    conn = get_db()
    conn.execute(
        """INSERT INTO services (name, category, description, price, sort_order, active, fields_json, documents_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (name, request.form.get("category", ""), request.form.get("description", ""),
         to_int(request.form.get("price")), to_int(request.form.get("sort_order")),
         1 if request.form.get("active", "1") == "1" else 0, fields_json, documents_json)
    )
    conn.commit()
    conn.close()
    flash("خدمت اضافه شد.", "success")
    return redirect(url_for("admin") + "#services")


@app.route("/admin/service/<int:service_id>/edit", methods=["GET", "POST"])
@login_required
def edit_service(service_id):
    conn = get_db()
    service = conn.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    if not service:
        conn.close()
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        fields_json = request.form.get("fields_json", "[]")
        documents_json = request.form.get("documents_json", "[]")
        try:
            json.loads(fields_json)
        except Exception:
            fields_json = "[]"
        try:
            json.loads(documents_json)
        except Exception:
            documents_json = "[]"
        conn.execute(
            """UPDATE services SET name=?, category=?, description=?, price=?, sort_order=?, active=?,
               fields_json=?, documents_json=? WHERE id=?""",
            (name, request.form.get("category", ""), request.form.get("description", ""),
             to_int(request.form.get("price")), to_int(request.form.get("sort_order")),
             1 if request.form.get("active") == "1" else 0, fields_json, documents_json, service_id)
        )
        conn.commit()
        conn.close()
        flash("ویرایش شد.", "success")
        return redirect(url_for("admin") + "#services")
    conn.close()
    return render_template("edit_service.html", service=service)


@app.route("/admin/service/<int:service_id>/delete", methods=["POST"])
@login_required
def delete_service(service_id):
    conn = get_db()
    conn.execute("DELETE FROM services WHERE id=?", (service_id,))
    conn.commit()
    conn.close()
    flash("حذف شد.", "success")
    return redirect(url_for("admin") + "#services")


@app.route("/admin/request/<int:rid>", methods=["GET", "POST"])
@login_required
def admin_request(rid):
    conn = get_db()
    row = conn.execute(
        """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, c.national_id AS customer_national_id,
                  s.name AS service_name, u.full_name AS expert_name
           FROM requests r LEFT JOIN customers c ON c.id=r.customer_id
           LEFT JOIN services s ON s.id=r.service_id LEFT JOIN users u ON u.id=r.expert_id WHERE r.id=?""",
        (rid,)
    ).fetchone()
    if not row:
        conn.close()
        abort(404)

    current = get_current_user()
    if current["role"] == "expert" and row["expert_id"] and row["expert_id"] != current["id"]:
        flash("پرونده نزد کارشناس دیگر است.", "error")
        conn.close()
        return redirect(url_for("admin"))

    if request.method == "POST":
        action = request.form.get("action", "update")
        sender_name = current["full_name"] or current["username"]

        if action == "message":
            message = request.form.get("message", "").strip()
            if message:
                conn.execute(
                    "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
                    (row["customer_id"], rid, "admin", sender_name, message)
                )
                conn.commit()
                send_sms(row["customer_phone"], f"{sender_name}:\n{message}\nکد: {row['tracking_code']}")
                add_notification(customer_phone=row["customer_phone"], title="پیام کارشناس", body=message)
                flash("پیام ارسال شد.", "success")
            return redirect(url_for("admin_request", rid=rid))

        if action == "note":
            note = request.form.get("personal_note", "").strip()
            conn.execute("UPDATE requests SET personal_note=? WHERE id=?", (note, rid))
            conn.commit()
            flash("یادداشت ذخیره شد.", "success")
            return redirect(url_for("admin_request", rid=rid))

        if action == "confirm_payment":
            if current["role"] in ("admin", "accountant"):
                conn.execute(
                    "UPDATE requests SET payment_confirmed=1, paid_price=total_price, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    ("در انتظار بررسی", rid)
                )
                conn.execute(
                    "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
                    (row["customer_id"], rid, "system", "سامانه", "پرداخت توسط حسابداری تأیید شد.")
                )
                conn.commit()
                notify_staff("پرداخت تأیید شد — ارسال برای کارشناسان", f"کد {row['tracking_code']}", row["service_id"])
                send_sms(row["customer_phone"], f"پرداخت کد {row['tracking_code']} تأیید شد.")
                flash("پرداخت تأیید و برای کارشناسان ارسال شد.", "success")
            return redirect(url_for("admin_request", rid=rid))

        if action == "receipt":
            files = save_uploaded_files(request.files.getlist("receipt"))
            if files:
                conn.execute("UPDATE requests SET receipt_file=? WHERE id=?", (files[0], rid))
                conn.commit()
                flash("رسید بارگذاری شد.", "success")
            return redirect(url_for("admin_request", rid=rid))

        status = request.form.get("status", row["status"]).strip()
        estimated_time = request.form.get("estimated_time", "").strip()
        admin_note = request.form.get("admin_note", "").strip()
        total_price = to_int(request.form.get("total_price", row["total_price"]))
        paid_price = to_int(request.form.get("paid_price", row["paid_price"]))
        paid_price = max(0, min(paid_price, total_price))
        rejected = request.form.getlist("rejected_field")

        expert_id = row["expert_id"]
        if status == "پذیرش شد" and not expert_id:
            expert_id = current["id"]

        invoice_code = row["invoice_code"] or ""
        if status == "انجام شد" and not invoice_code:
            invoice_code = "INV-" + row["tracking_code"] + "-" + secrets.token_hex(2).upper()

        conn.execute(
            """UPDATE requests SET status=?, estimated_time=?, admin_note=?, total_price=?, paid_price=?,
               expert_id=?, rejected_fields=?, invoice_code=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (status, estimated_time, admin_note, total_price, paid_price, expert_id,
             json.dumps(rejected, ensure_ascii=False), invoice_code, rid)
        )
        msg = f"وضعیت: {status}\nکد: {row['tracking_code']}\nکارشناس: {sender_name}"
        if estimated_time:
            msg += f"\nمدت تقریبی: {estimated_time}"
        if admin_note:
            msg += f"\nتوضیحات: {admin_note}"
        if status == "انجام شد" and invoice_code:
            inv_url = url_for("invoice_view", tracking_code=row["tracking_code"], _external=True)
            msg += f"\nفاکتور: {inv_url}"
        conn.execute(
            "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
            (row["customer_id"], rid, "system", sender_name, msg)
        )
        conn.commit()
        conn.close()
        send_sms(row["customer_phone"], msg)
        add_notification(customer_phone=row["customer_phone"], title="تغییر وضعیت", body=msg)
        notify_staff("تغییر وضعیت", f"{row['tracking_code']} → {status}", row["service_id"])
        flash("ذخیره شد.", "success")
        return redirect(url_for("admin_request", rid=rid))

    form_data = parse_json_dict(row["form_data"])
    docs = parse_json_list(row["documents"])
    rejected = parse_json_list(row["rejected_fields"])
    messages = conn.execute("SELECT * FROM messages WHERE request_id=? ORDER BY id ASC", (rid,)).fetchall()
    conn.close()
    return render_template(
        "admin_request.html", req=row, messages=messages, form_data=form_data, docs=docs, rejected=rejected
    )


@app.route("/invoice/<tracking_code>")
def invoice_view(tracking_code):
    conn = get_db()
    row = conn.execute(
        """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone, c.national_id AS customer_national_id,
                  s.name AS service_name, u.full_name AS expert_name
           FROM requests r LEFT JOIN customers c ON c.id=r.customer_id
           LEFT JOIN services s ON s.id=r.service_id LEFT JOIN users u ON u.id=r.expert_id
           WHERE r.tracking_code=?""",
        (to_latin_digits(tracking_code),)
    ).fetchone()
    conn.close()
    if not row:
        abort(404)
    return render_template("invoice.html", req=row, settings=get_settings())


@app.route("/admin/support/reply", methods=["POST"])
@login_required
def support_reply():
    customer_id = to_int(request.form.get("customer_id"))
    message = request.form.get("message", "").strip()
    current = get_current_user()
    sender_name = current["full_name"] or current["username"]
    if customer_id and message:
        conn = get_db()
        cust = conn.execute("SELECT phone FROM customers WHERE id=?", (customer_id,)).fetchone()
        conn.execute(
            "INSERT INTO messages (customer_id, request_id, sender, sender_name, message) VALUES (?,?,?,?,?)",
            (customer_id, None, "admin", sender_name, message)
        )
        conn.commit()
        conn.close()
        if cust and cust["phone"]:
            send_sms(cust["phone"], f"{sender_name}:\n{message}")
            add_notification(customer_phone=cust["phone"], title="پاسخ پشتیبانی", body=message)
        flash("پاسخ ارسال شد.", "success")
    return redirect(url_for("admin") + "#support")


@app.route("/admin/user/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()
    phone = to_latin_digits(request.form.get("phone", "").strip())
    role = request.form.get("role", "expert")
    expires_at = request.form.get("expires_at", "").strip()
    allowed_services = request.form.getlist("allowed_services")
    allowed_sections = request.form.getlist("allowed_sections")
    if not username or len(password) < 6:
        flash("اطلاعات ناقص.", "error")
        return redirect(url_for("admin") + "#users")
    conn = get_db()
    if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        conn.close()
        flash("نام کاربری تکراری.", "error")
        return redirect(url_for("admin") + "#users")
    conn.execute(
        """INSERT INTO users (username, password, full_name, role, active, phone, allowed_services, allowed_sections, expires_at)
           VALUES (?,?,?,?,1,?,?,?,?)""",
        (username, generate_password_hash(password), full_name, role, phone,
         json.dumps([int(x) for x in allowed_services if x]), json.dumps(allowed_sections), expires_at)
    )
    conn.commit()
    conn.close()
    flash("کاربر ایجاد شد.", "success")
    return redirect(url_for("admin") + "#users")


@app.route("/admin/user/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    if user_id == session.get("user_id"):
        flash("مجاز نیست.", "error")
        return redirect(url_for("admin") + "#users")
    conn = get_db()
    conn.execute("UPDATE users SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin") + "#users")


@app.route("/admin/sms-experts", methods=["POST"])
@admin_required
def sms_experts():
    message = request.form.get("message", "").strip()
    expert_ids = request.form.getlist("expert_ids")
    conn = get_db()
    for eid in expert_ids:
        u = conn.execute("SELECT phone FROM users WHERE id=?", (eid,)).fetchone()
        if u and u["phone"]:
            send_sms(u["phone"], message)
            add_notification(user_id=int(eid), title="پیام مدیر", body=message)
    conn.close()
    flash("پیام ثبت شد.", "success")
    return redirect(url_for("admin") + "#users")


@app.route("/admin/discount/create", methods=["POST"])
@login_required
def create_discount():
    code = to_latin_digits(request.form.get("code", "").strip()).upper()
    if not code:
        flash("کد لازم است.", "error")
        return redirect(url_for("admin") + "#discounts")
    conn = get_db()
    if conn.execute("SELECT id FROM discounts WHERE code=?", (code,)).fetchone():
        conn.close()
        flash("تکراری.", "error")
        return redirect(url_for("admin") + "#discounts")
    conn.execute(
        """INSERT INTO discounts (code, kind, value, max_uses, start_date, end_date, is_credit, active)
           VALUES (?,?,?,?,?,?,?,1)""",
        (code, request.form.get("kind", "percent"), to_int(request.form.get("value")),
         to_int(request.form.get("max_uses", 0)), request.form.get("start_date", ""),
         request.form.get("end_date", ""), 1 if request.form.get("is_credit") == "1" else 0)
    )
    conn.commit()
    conn.close()
    flash("ایجاد شد.", "success")
    return redirect(url_for("admin") + "#discounts")


@app.route("/admin/discount/generate-credit", methods=["POST"])
@login_required
def generate_credit_code():
    code = "CREDIT" + str(secrets.randbelow(9000) + 1000)
    conn = get_db()
    while conn.execute("SELECT id FROM discounts WHERE code=?", (code,)).fetchone():
        code = "CREDIT" + str(secrets.randbelow(9000) + 1000)
    conn.execute("INSERT INTO discounts (code, kind, value, max_uses, is_credit, active) VALUES (?,'fixed',0,1,1,1)", (code,))
    conn.commit()
    conn.close()
    flash(f"کد نسیه: {code}", "success")
    return redirect(url_for("admin") + "#discounts")


@app.route("/admin/discount/<int:discount_id>/delete", methods=["POST"])
@login_required
def delete_discount(discount_id):
    conn = get_db()
    conn.execute("DELETE FROM discounts WHERE id=?", (discount_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin") + "#discounts")


@app.route("/admin/password", methods=["POST"])
@login_required
def admin_password():
    password = request.form.get("password", "")
    new_username = request.form.get("new_username", "").strip()
    conn = get_db()
    uid = session["user_id"]
    if new_username:
        exists = conn.execute("SELECT id FROM users WHERE username=? AND id!=?", (new_username, uid)).fetchone()
        if exists:
            conn.close()
            flash("نام کاربری تکراری.", "error")
            return redirect(url_for("admin") + "#password")
        conn.execute("UPDATE users SET username=? WHERE id=?", (new_username, uid))
    if password and len(password) >= 6:
        conn.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(password), uid))
    conn.commit()
    conn.close()
    flash("ذخیره شد.", "success")
    return redirect(url_for("admin") + "#password")


@app.route("/admin/backup", methods=["POST"])
@admin_required
def create_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BACKUP_FOLDER, f"novin_backup_{ts}.db")
    shutil.copy2(DATABASE, path)
    email = get_settings().get("backup_email", "")
    msg = f"پشتیبان: {os.path.basename(path)}"
    if email:
        msg += f" — آماده برای {email}"
    flash(msg, "success")
    return redirect(url_for("admin") + "#backup")


@app.route("/admin/backup-email", methods=["POST"])
@admin_required
def backup_email_save():
    set_setting("backup_email", request.form.get("backup_email", "").strip())
    flash("ایمیل ذخیره شد.", "success")
    return redirect(url_for("admin") + "#backup")


@app.route("/admin/restore", methods=["POST"])
@admin_required
def restore_backup():
    f = request.files.get("backup_file")
    if not f or not f.filename.endswith(".db"):
        flash("فایل نامعتبر.", "error")
        return redirect(url_for("admin") + "#backup")
    temp = os.path.join(BACKUP_FOLDER, "temp_restore.db")
    f.save(temp)
    shutil.copy2(temp, DATABASE)
    os.remove(temp)
    flash("بازیابی شد.", "success")
    return redirect(url_for("admin") + "#backup")


@app.route("/admin/debt-sms", methods=["POST"])
@login_required
def debt_sms():
    phone = to_latin_digits(request.form.get("phone", "").strip())
    message = request.form.get("message", "").strip()
    if phone and message:
        send_sms(phone, message)
    flash("ثبت شد.", "success")
    return redirect(url_for("admin") + "#debts")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/uploads/logo/<path:filename>")
def uploaded_logo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.errorhandler(404)
def not_found(e):
    return render_template("base.html", content="صفحه پیدا نشد."), 404


@app.errorhandler(500)
def internal_error(e):
    app.logger.exception("Server Error")
    return "خطای سرور", 500


create_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
