import sqlite3
from datetime import datetime

DB_NAME = "site.db"


def get_connection():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    return con


def create_tables():
    con = get_connection()
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        national_id TEXT,
        phone TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        category TEXT DEFAULT '',
        image TEXT DEFAULT '',
        price INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        fields_json TEXT DEFAULT '[]',
        documents_json TEXT DEFAULT '[]',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        service_id INTEGER,
        data_json TEXT DEFAULT '{}',
        status TEXT DEFAULT 'جدید',
        tracking_code TEXT UNIQUE,
        total_price INTEGER DEFAULT 0,
        paid_price INTEGER DEFAULT 0,
        payment_mode TEXT DEFAULT 'full',
        created_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(service_id) REFERENCES services(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        sender TEXT,
        message TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        title TEXT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        request_id INTEGER,
        amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        tracking_id TEXT,
        transaction_id TEXT,
        gateway TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS installments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        installment_number INTEGER,
        amount INTEGER DEFAULT 0,
        due_date TEXT,
        status TEXT DEFAULT 'pending',
        paid_at TEXT
    );

    CREATE TABLE IF NOT EXISTS discount_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        kind TEXT DEFAULT 'percent',
        value INTEGER DEFAULT 0,
        start_date TEXT,
        end_date TEXT,
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS payment_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        prepayment_percent INTEGER DEFAULT 0,
        installment_count INTEGER DEFAULT 0,
        installment_percent INTEGER DEFAULT 0,
        valid_until TEXT,
        service_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS free_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        valid_until TEXT,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'admin',
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admin_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        permission TEXT
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS sms_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        enabled INTEGER DEFAULT 0,
        provider TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        api_secret TEXT DEFAULT '',
        sender TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS payment_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        enabled INTEGER DEFAULT 0,
        gateway TEXT DEFAULT '',
        merchant_id TEXT DEFAULT '',
        test_mode INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        field_name TEXT,
        original_name TEXT,
        stored_name TEXT,
        file_type TEXT,
        created_at TEXT
    );
    """)

    # مدیر اولیه
    admin = cur.execute(
        "SELECT id FROM admins LIMIT 1"
    ).fetchone()

    if not admin:
        cur.execute(
            """
            INSERT INTO admins(username, password, role, active)
            VALUES (?, ?, ?, ?)
            """,
            ("admin", "123456", "admin", 1)
        )

    # تنظیمات اصلی سایت
    defaults = {
        "site_name": "کافی‌نت آنلاین نوین",
        "manager": "احمد محمدی مهر",
        "phone": "09920345139",
        "logo": "",
        "tracking_prefix": "NV-",
        "tracking_digits": "8",
        "tracking_separator": "",
        "warning_text":
            "توجه: پرداخت هزینه خدمات فقط از طریق درگاه رسمی همین سایت انجام می‌شود.",
    }

    for key, value in defaults.items():
        cur.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

    # تنظیمات پیامک
    cur.execute(
        """
        INSERT OR IGNORE INTO sms_settings
        (id, enabled, provider, api_key, api_secret, sender)
        VALUES (1, 0, '', '', '', '')
        """
    )

    # تنظیمات درگاه
    cur.execute(
        """
        INSERT OR IGNORE INTO payment_settings
        (id, enabled, gateway, merchant_id, test_mode)
        VALUES (1, 0, '', '', 1)
        """
    )

    con.commit()
    con.close()


def create_customer(name, national_id="", phone=""):
    con = get_connection()
    cur = con.cursor()

    customer = cur.execute(
        """
        SELECT id FROM customers
        WHERE national_id = ? OR phone = ?
        LIMIT 1
        """,
        (national_id, phone)
    ).fetchone()

    if customer:
        customer_id = customer["id"]

        cur.execute(
            """
            UPDATE customers
            SET name = ?, national_id = ?, phone = ?
            WHERE id = ?
            """,
            (name, national_id, phone, customer_id)
        )
    else:
        cur.execute(
            """
            INSERT INTO customers
            (name, national_id, phone, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                national_id,
                phone,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )

        customer_id = cur.lastrowid

    con.commit()
    con.close()

    return customer_id


def add_service(
    name,
    description="",
    category="",
    price=0,
    image="",
    fields_json="[]",
    documents_json="[]",
    active=1,
    sort_order=0
):
    con = get_connection()

    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO services
        (
            name,
            description,
            category,
            image,
            price,
            active,
            sort_order,
            fields_json,
            documents_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            description,
            category,
            image,
            price,
            active,
            sort_order,
            fields_json,
            documents_json,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    service_id = cur.lastrowid

    con.commit()
    con.close()

    return service_id


def add_request(
    customer_id,
    service_id,
    data_json="{}",
    total_price=0,
    tracking_code=""
):
    con = get_connection()

    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO requests
        (
            customer_id,
            service_id,
            data_json,
            status,
            tracking_code,
            total_price,
            paid_price,
            payment_mode,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            service_id,
            data_json,
            "جدید",
            tracking_code,
            total_price,
            0,
            "full",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    request_id = cur.lastrowid

    con.commit()
    con.close()

    return request_id
