import os
import json
import sqlite3
import secrets
import shutil
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort
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
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_tables():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'expert',
            active INTEGER NOT NULL DEFAULT 1,
            allowed_services TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT '',
            description TEXT DEFAULT '',
            price INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            fields_json TEXT DEFAULT '[]',
            documents_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            service_id INTEGER,
            expert_id INTEGER,
            tracking_code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'در انتظار بررسی',
            customer_note TEXT DEFAULT '',
            admin_note TEXT DEFAULT '',
            estimated_time TEXT DEFAULT '',
            total_price INTEGER DEFAULT 0,
            paid_price INTEGER DEFAULT 0,
            discount_code TEXT DEFAULT '',
            discount_amount INTEGER DEFAULT 0,
            payment_mode TEXT DEFAULT 'gateway',
            form_data TEXT DEFAULT '{}',
            documents TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE SET NULL,
            FOREIGN KEY(expert_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            request_id INTEGER,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS discounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL DEFAULT 'percent',
            value INTEGER NOT NULL DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    add_column_if_missing(conn, "customers", "national_id", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "admin_note", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "estimated_time", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_code", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "requests", "discount_amount", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "requests", "expert_id", "INTEGER")
    add_column_if_missing(conn, "requests", "payment_mode", "TEXT DEFAULT 'gateway'")
    add_column_if_missing(conn, "users", "allowed_services", "TEXT DEFAULT '[]'")

    defaults = {
        "site_name": SITE_NAME,
        "manager": MANAGER,
        "phone": PHONE,
        "manager_text": "ارائه کلیه خدمات اینترنتی و کافی نتی",
        "home_text": "",
        "footer_text": "تمامی حقوق محفوظ است",
        "logo": "",
        "default_payment_mode": "gateway",
    }

    for key, value in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))

    admin = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(username, password, role, active) VALUES (?, ?, 'admin', 1)",
            ("admin", generate_password_hash(ADMIN_PASSWORD))
        )

    conn.commit()
    conn.close()


def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value)
    )
    conn.commit()
    conn.close()


@app.context_processor
def inject_globals():
    settings = get_settings()
    return {
        "site_settings": settings,
        "site_name": settings.get("site_name", SITE_NAME),
        "manager": settings.get("manager", MANAGER),
        "phone": settings.get("phone", PHONE),
        "current_user": get_current_user(),
    }


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, role, active, allowed_services FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    if not user or not user["active"]:
        return None
    return user


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or user["role"] != "admin":
            flash("دسترسی فقط برای مدیر امکان‌پذیر است.", "error")
            return redirect(url_for("admin"))
        return func(*args, **kwargs)
    return wrapper


def generate_tracking_code():
    while True:
        code = str(secrets.randbelow(9000) + 1000)
        conn = get_db()
        exists = conn.execute("SELECT id FROM requests WHERE tracking_code = ?", (code,)).fetchone()
        conn.close()
        if not exists:
            return code


def to_int(value, default=0):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception
