import sqlite3
from datetime import datetime

DB_NAME = "online_novin.db"


def get_connection():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    return con


def create_tables():
    con = get_connection()
    cur = con.cursor()

    # مشتریان
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        national_id TEXT UNIQUE,
        created_at TEXT
    )
    """)

    # خدمات مشتری
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customer_services(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        service_name TEXT,
        status TEXT DEFAULT 'جدید',
        estimated_time TEXT,
        customer_note TEXT,
        total_price INTEGER DEFAULT 0,
        paid_price INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    )
    """)

    # خدمات
    cur.execute("""
    CREATE TABLE IF NOT EXISTS services(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        active INTEGER DEFAULT 1
    )
    """)

    # پیام‌های چت
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        sender TEXT,
        message TEXT,
        created_at TEXT
    )
    """)

    con.commit()
    con.close()


def create_customer(name, phone, national_id):
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
    INSERT INTO customers
    (name, phone, national_id, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        name,
        phone,
        national_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    con.commit()
    customer_id = cur.lastrowid
    con.close()

    return customer_id


def add_service(customer_id, service_name, total_price=0):
    con = get_connection()

    con.execute("""
    INSERT INTO customer_services
    (customer_id, service_name, total_price, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        customer_id,
        service_name,
        total_price,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    con.commit()
    con.close()
