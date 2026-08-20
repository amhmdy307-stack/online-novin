import sqlite3
from datetime import datetime


DB_NAME = "site.db"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_connection():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def column_exists(cur, table, column):
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def add_column(cur, table, column, definition):
    if not column_exists(cur, table, column):
        cur.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


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

    CREATE TABLE IF NOT EXISTS systems (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        image TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
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
        system_id INTEGER,
        parent_id INTEGER,
        created_at TEXT,
        FOREIGN KEY(system_id) REFERENCES systems(id),
        FOREIGN KEY(parent_id) REFERENCES services(id)
    );

    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT NOT NULL,
        name TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        role TEXT DEFAULT 'admin',
        active INTEGER DEFAULT 1,
        notifications_enabled INTEGER DEFAULT 1,
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
        assigned_admin_id INTEGER,
        accepted_at TEXT,
        estimated_time TEXT DEFAULT '',
        expert_name TEXT DEFAULT '',
        customer_note TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(service_id) REFERENCES services(id),
        FOREIGN KEY(assigned_admin_id) REFERENCES admins(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        sender TEXT,
        sender_admin_id INTEGER,
        message TEXT,
        file_id INTEGER,
        created_at TEXT,
        FOREIGN KEY(request_id) REFERENCES requests(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(sender_admin_id) REFERENCES admins(id)
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        admin_id INTEGER,
        request_id INTEGER,
        title TEXT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(admin_id) REFERENCES admins(id),
        FOREIGN KEY(request_id) REFERENCES requests(id)
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
        created_at TEXT,
        paid_at TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(request_id) REFERENCES requests(id)
    );

    CREATE TABLE IF NOT EXISTS financial_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        admin_id INTEGER,
        type TEXT DEFAULT 'income',
        category TEXT DEFAULT '',
        amount INTEGER DEFAULT 0,
        description TEXT DEFAULT '',
        reference TEXT DEFAULT '',
        created_at TEXT,
        FOREIGN KEY(request_id) REFERENCES requests(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(admin_id) REFERENCES admins(id)
    );

    CREATE TABLE IF NOT EXISTS installments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        installment_number INTEGER,
        amount INTEGER DEFAULT 0,
        due_date TEXT,
        status TEXT DEFAULT 'pending',
        paid_at TEXT,
        FOREIGN KEY(request_id) REFERENCES requests(id)
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
        active INTEGER DEFAULT 1,
        FOREIGN KEY(service_id) REFERENCES services(id)
    );

    CREATE TABLE IF NOT EXISTS payment_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        prepayment_percent INTEGER DEFAULT 0,
        installment_count INTEGER DEFAULT 0,
        installment_percent INTEGER DEFAULT 0,
        valid_until TEXT,
        service_id INTEGER,
        active INTEGER DEFAULT 1,
        FOREIGN KEY(service_id) REFERENCES services(id)
    );

    CREATE TABLE IF NOT EXISTS free_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        valid_until TEXT,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0,
        service_id INTEGER,
        active INTEGER DEFAULT 1,
        FOREIGN KEY(service_id) REFERENCES services(id)
    );

    CREATE TABLE IF NOT EXISTS admin_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        permission TEXT,
        system_id INTEGER,
        service_id INTEGER,
        created_at TEXT,
        UNIQUE(admin_id, permission, system_id, service_id),
        FOREIGN KEY(admin_id) REFERENCES admins(id) ON DELETE CASCADE,
        FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE CASCADE,
        FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS request_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        admin_id INTEGER,
        old_status TEXT,
        new_status TEXT,
        description TEXT DEFAULT '',
        created_at TEXT,
        FOREIGN KEY(request_id) REFERENCES requests(id),
        FOREIGN KEY(admin_id) REFERENCES admins(id)
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
        username TEXT DEFAULT '',
        password TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        test_mode INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS notification_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        browser_enabled INTEGER DEFAULT 1,
        customer_enabled INTEGER DEFAULT 1,
        admin_enabled INTEGER DEFAULT 1,
        sms_enabled INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        customer_id INTEGER,
        admin_id INTEGER,
        field_name TEXT,
        original_name TEXT,
        stored_name TEXT,
        file_type TEXT,
        downloadable INTEGER DEFAULT 1,
        created_at TEXT,
        FOREIGN KEY(request_id) REFERENCES requests(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(admin_id) REFERENCES admins(id)
    );

    """)

    add_column(cur, "services", "system_id", "INTEGER")
    add_column(cur, "services", "parent_id", "INTEGER")

    add_column(cur, "requests", "assigned_admin_id", "INTEGER")
    add_column(cur, "requests", "accepted_at", "TEXT")
    add_column(cur, "requests", "estimated_time", "TEXT DEFAULT ''")
    add_column(cur, "requests", "expert_name", "TEXT DEFAULT ''")
    add_column(cur, "requests", "customer_note", "TEXT DEFAULT ''")
    add_column(cur, "requests", "updated_at", "TEXT")

    add_column(cur, "messages", "sender_admin_id", "INTEGER")
    add_column(cur, "messages", "file_id", "INTEGER")

    add_column(cur, "notifications", "admin_id", "INTEGER")
    add_column(cur, "notifications", "request_id", "INTEGER")

    add_column(cur, "payments", "paid_at", "TEXT")

    add_column(cur, "admins", "name", "TEXT DEFAULT ''")
    add_column(cur, "admins", "phone", "TEXT DEFAULT ''")
    add_column(cur, "admins", "notifications_enabled", "INTEGER DEFAULT 1")
    add_column(cur, "admins", "created_at", "TEXT")

    add_column(cur, "files", "admin_id", "INTEGER")
    add_column(cur, "files", "downloadable", "INTEGER DEFAULT 1")

    admin = cur.execute(
        "SELECT id FROM admins ORDER BY id LIMIT 1"
    ).fetchone()

    if not admin:
        cur.execute(
            """
            INSERT INTO admins
            (
                username,
                password,
                name,
                role,
                active,
                notifications_enabled,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                "123456",
                "مدیر اصلی",
                "superadmin",
                1,
                1,
                now()
            )
        )
    else:
        cur.execute(
            """
            UPDATE admins
            SET role = 'superadmin'
            WHERE id = ?
            """,
            (admin["id"],)
        )

    defaults = {
        "site_name": "کافی‌نت آنلاین نوین",
        "manager": "احمد محمدی مهر",
        "phone": "09920345139",
        "logo": "",
        "tracking_prefix": "",
        "tracking_digits": "3",
        "tracking_separator": "",
        "warning_text": "توجه: پرداخت هزینه خدمات فقط از طریق درگاه رسمی همین سایت انجام می‌شود.",
        "currency": "ریال",
        "free_request_after_100_discount": "1",
        "notifications_once_permission": "1",
        "admin_request_notification": "1",
        "customer_request_notification": "1",
        "support_enabled": "1",
        "support_title": "ارتباط با پشتیبانی",
        "support_description": "در صورت نیاز به راهنمایی یا پیگیری، پیام خود را برای پشتیبانی ارسال کنید."
    }

    for key, value in defaults.items():
        cur.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

    cur.execute(
        """
        INSERT OR IGNORE INTO sms_settings
        (id, enabled, provider, api_key, api_secret, sender)
        VALUES (1, 0, '', '', '', '')
        """
    )

    cur.execute(
        """
        INSERT OR IGNORE INTO payment_settings
        (id, enabled, gateway, merchant_id, username, password, api_key, test_mode)
        VALUES (1, 0, '', '', '', '', '', 1)
        """
    )

    cur.execute(
        """
        INSERT OR IGNORE INTO notification_settings
        (id, browser_enabled, customer_enabled, admin_enabled, sms_enabled)
        VALUES (1, 1, 1, 1, 0)
        """
    )

    con.commit()
    con.close()


def create_customer(name, national_id="", phone=""):

    con = get_connection()
    cur = con.cursor()

    customer = cur.execute(
        """
        SELECT id
        FROM customers
        WHERE
            (national_id != '' AND national_id = ?)
            OR
            (phone != '' AND phone = ?)
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
            INSERT INTO customers(name, national_id, phone, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, national_id, phone, now())
        )

        customer_id = cur.lastrowid

    con.commit()
    con.close()

    return customer_id


def add_system(name, description="", image="", active=1, sort_order=0):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO systems
        (name, description, image, active, sort_order, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, description, image, active, sort_order, now())
    )

    system_id = cur.lastrowid

    con.commit()
    con.close()

    return system_id


def add_service(
    name,
    description="",
    category="",
    price=0,
    image="",
    fields_json="[]",
    documents_json="[]",
    active=1,
    sort_order=0,
    system_id=None,
    parent_id=None
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
            system_id,
            parent_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            system_id,
            parent_id,
            now()
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
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            now(),
            now()
        )
    )

    request_id = cur.lastrowid

    setting = cur.execute(
        """
        SELECT value FROM settings
        WHERE key = 'admin_request_notification'
        """
    ).fetchone()

    if not setting or str(setting["value"]) != "0":

        admins = cur.execute(
            """
            SELECT id FROM admins
            WHERE active = 1
            AND notifications_enabled = 1
            """
        ).fetchall()

        customer = cur.execute(
            "SELECT name FROM customers WHERE id = ?",
            (customer_id,)
        ).fetchone()

        service = cur.execute(
            "SELECT name FROM services WHERE id = ?",
            (service_id,)
        ).fetchone()

        customer_name = customer["name"] if customer else "مشتری"
        service_name = service["name"] if service else "خدمت"

        for admin in admins:
            cur.execute(
                """
                INSERT INTO notifications
                (
                    admin_id,
                    request_id,
                    title,
                    message,
                    is_read,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    admin["id"],
                    request_id,
                    "درخواست جدید",
                    f"درخواست جدید از {customer_name} برای خدمت «{service_name}» ثبت شد.",
                    now()
                )
            )

    con.commit()
    con.close()

    return request_id


def accept_request(
    request_id,
    admin_id,
    estimated_time="",
    expert_name=""
):

    con = get_connection()
    cur = con.cursor()

    request = cur.execute(
        """
        SELECT id,status,assigned_admin_id,customer_id,tracking_code
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()

    if not request:
        con.close()
        return False

    if (
        request["assigned_admin_id"] is not None
        and request["assigned_admin_id"] != admin_id
    ):
        con.close()
        return False

    current_time = now()

    cur.execute(
        """
        UPDATE requests
        SET
            assigned_admin_id = ?,
            accepted_at = ?,
            estimated_time = ?,
            expert_name = ?,
            status = 'پذیرش شد',
            updated_at = ?
        WHERE id = ?
        AND
        (
            assigned_admin_id IS NULL
            OR assigned_admin_id = ?
        )
        """,
        (
            admin_id,
            current_time,
            estimated_time,
            expert_name,
            current_time,
            request_id,
            admin_id
        )
    )

    success = cur.rowcount > 0

    if success:

        cur.execute(
            """
            INSERT INTO request_history
            (
                request_id,
                admin_id,
                old_status,
                new_status,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                admin_id,
                request["status"],
                "پذیرش شد",
                "پرونده توسط مدیر یا کارشناس پذیرفته شد.",
                current_time
            )
        )

        if request["customer_id"]:
            cur.execute(
                """
                INSERT INTO notifications
                (
                    customer_id,
                    request_id,
                    title,
                    message,
                    is_read,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    request["customer_id"],
                    request_id,
                    "درخواست شما پذیرفته شد",
                    "درخواست شما توسط مدیر یا کارشناس پذیرفته شد و در حال بررسی است.",
                    current_time
                )
            )

    con.commit()
    con.close()

    return success


def update_request_status(
    request_id,
    admin_id,
    status,
    description="",
    estimated_time=None,
    expert_name=None
):

    con = get_connection()
    cur = con.cursor()

    request = cur.execute(
        """
        SELECT status,customer_id,tracking_code
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()

    if not request:
        con.close()
        return False

    old_status = request["status"]

    estimated_time = estimated_time or ""
    expert_name = expert_name or ""

    current_time = now()

    cur.execute(
        """
        UPDATE requests
        SET
            status = ?,
            estimated_time =
                CASE WHEN ? != '' THEN ? ELSE estimated_time END,
            expert_name =
                CASE WHEN ? != '' THEN ? ELSE expert_name END,
            customer_note = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            estimated_time,
            estimated_time,
            expert_name,
            expert_name,
            description,
            current_time,
            request_id
        )
    )

    success = cur.rowcount > 0

    if success:

        cur.execute(
            """
            INSERT INTO request_history
            (
                request_id,
                admin_id,
                old_status,
                new_status,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                admin_id,
                old_status,
                status,
                description,
                current_time
            )
        )

        if request["customer_id"]:

            message = (
                f"وضعیت درخواست شما از «{old_status}» "
                f"به «{status}» تغییر کرد."
            )

            if description:
                message += f" توضیحات: {description}"

            cur.execute(
                """
                INSERT INTO notifications
                (
                    customer_id,
                    request_id,
                    title,
                    message,
                    is_read,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    request["customer_id"],
                    request_id,
                    "به‌روزرسانی درخواست",
                    message,
                    current_time
                )
            )

    con.commit()
    con.close()

    return success


def add_message(
    request_id,
    customer_id=None,
    sender="customer",
    message="",
    sender_admin_id=None,
    file_id=None
):

    con = get_connection()
    cur = con.cursor()

    request = cur.execute(
        """
        SELECT customer_id,assigned_admin_id,tracking_code
        FROM requests
        WHERE id = ?
        """,
        (request_id,)
    ).fetchone()

    if not request:
        con.close()
        return None

    current_time = now()

    cur.execute(
        """
        INSERT INTO messages
        (
            request_id,
            customer_id,
            sender,
            sender_admin_id,
            message,
            file_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            customer_id,
            sender,
            sender_admin_id,
            message,
            file_id,
            current_time
        )
    )

    message_id = cur.lastrowid

    if sender == "customer":

        admins = cur.execute(
            """
            SELECT id FROM admins
            WHERE active = 1
            AND notifications_enabled = 1
            """
        ).fetchall()

        for admin in admins:
            cur.execute(
                """
                INSERT INTO notifications
                (
                    admin_id,
                    request_id,
                    title,
                    message,
                    is_read,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    admin["id"],
                    request_id,
                    "پیام جدید مشتری",
                    "مشتری برای یک پرونده پیام جدید ارسال کرده است.",
                    current_time
                )
            )

    else:

        target_customer_id = request["customer_id"] or customer_id

        if target_customer_id:

            sender_name = "پشتیبانی"

            if sender_admin_id:

                admin = cur.execute(
                    """
                    SELECT name FROM admins
                    WHERE id = ?
                    """,
                    (sender_admin_id,)
                ).fetchone()

                if admin and admin["name"]:
                    sender_name = admin["name"]

            cur.execute(
                """
                INSERT INTO notifications
                (
                    customer_id,
                    request_id,
                    title,
                    message,
                    is_read,
                    created_at
                )
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    target_customer_id,
                    request_id,
                    "پاسخ جدید پشتیبانی",
                    f"{sender_name} برای درخواست شما پیام جدید ارسال کرده است.",
                    current_time
                )
            )

    con.commit()
    con.close()

    return message_id


def create_support_request(customer_id, message="", admin_id=None):

    con = get_connection()
    cur = con.cursor()

    existing = cur.execute(
        """
        SELECT id
        FROM requests
        WHERE customer_id = ?
        AND service_id IS NULL
        AND status NOT IN ('بسته شد', 'لغو شد')
        ORDER BY id DESC
        LIMIT 1
        """,
        (customer_id,)
    ).fetchone()

    if existing:
        request_id = existing["id"]
    else:

        tracking_code = (
            f"SUP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

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
                created_at,
                updated_at
            )
            VALUES (?, NULL, '{}', ?, ?, 0, 0, 'full', ?, ?)
            """,
            (
                customer_id,
                "پشتیبانی",
                tracking_code,
                now(),
                now()
            )
        )

        request_id = cur.lastrowid

    con.commit()
    con.close()

    if message:
        add_message(
            request_id=request_id,
            customer_id=customer_id,
            sender="customer",
            message=message
        )

    return request_id


def add_support_message(customer_id, message, admin_id=None):

    request_id = create_support_request(
        customer_id=customer_id
    )

    return add_message(
        request_id=request_id,
        customer_id=customer_id,
        sender="admin" if admin_id else "customer",
        message=message,
        sender_admin_id=admin_id
    )


def add_customer_notification(
    customer_id,
    title,
    message,
    request_id=None
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO notifications
        (
            customer_id,
            request_id,
            title,
            message,
            is_read,
            created_at
        )
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (
            customer_id,
            request_id,
            title,
            message,
            now()
        )
    )

    notification_id = cur.lastrowid

    con.commit()
    con.close()

    return notification_id


def add_admin_notification(
    admin_id,
    title,
    message,
    request_id=None
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO notifications
        (
            admin_id,
            request_id,
            title,
            message,
            is_read,
            created_at
        )
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (
            admin_id,
            request_id,
            title,
            message,
            now()
        )
    )

    notification_id = cur.lastrowid

    con.commit()
    con.close()

    return notification_id


def notify_all_admins(title, message, request_id=None):

    con = get_connection()
    cur = con.cursor()

    admins = cur.execute(
        """
        SELECT id FROM admins
        WHERE active = 1
        AND notifications_enabled = 1
        """
    ).fetchall()

    for admin in admins:
        cur.execute(
            """
            INSERT INTO notifications
            (
                admin_id,
                request_id,
                title,
                message,
                is_read,
                created_at
            )
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                admin["id"],
                request_id,
                title,
                message,
                now()
            )
        )

    con.commit()
    con.close()


def add_admin(
    username,
    password,
    name="",
    phone="",
    role="admin"
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO admins
        (
            username,
            password,
            name,
            phone,
            role,
            active,
            notifications_enabled,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, 1, 1, ?)
        """,
        (
            username,
            password,
            name,
            phone,
            role,
            now()
        )
    )

    admin_id = cur.lastrowid

    con.commit()
    con.close()

    return admin_id


def set_admin_permission(
    admin_id,
    permission,
    system_id=None,
    service_id=None
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO admin_permissions
        (
            admin_id,
            permission,
            system_id,
            service_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            admin_id,
            permission,
            system_id,
            service_id,
            now()
        )
    )

    con.commit()
    con.close()


def remove_admin_permission(
    admin_id,
    permission,
    system_id=None,
    service_id=None
):

    con = get_connection()
    cur = con.cursor()

    if system_id is None and service_id is None:
        cur.execute(
            """
            DELETE FROM admin_permissions
            WHERE admin_id = ?
            AND permission = ?
            AND system_id IS NULL
            AND service_id IS NULL
            """,
            (admin_id, permission)
        )

    elif system_id is None:
        cur.execute(
            """
            DELETE FROM admin_permissions
            WHERE admin_id = ?
            AND permission = ?
            AND system_id IS NULL
            AND service_id = ?
            """,
            (admin_id, permission, service_id)
        )

    elif service_id is None:
        cur.execute(
            """
            DELETE FROM admin_permissions
            WHERE admin_id = ?
            AND permission = ?
            AND system_id = ?
            AND service_id IS NULL
            """,
            (admin_id, permission, system_id)
        )

    else:
        cur.execute(
            """
            DELETE FROM admin_permissions
            WHERE admin_id = ?
            AND permission = ?
            AND system_id = ?
            AND service_id = ?
            """,
            (
                admin_id,
                permission,
                system_id,
                service_id
            )
        )

    con.commit()
    con.close()


def has_permission(
    admin_id,
    permission,
    system_id=None,
    service_id=None
):

    con = get_connection()
    cur = con.cursor()

    admin = cur.execute(
        """
        SELECT role,active
        FROM admins
        WHERE id = ?
        """,
        (admin_id,)
    ).fetchone()

    if not admin or not admin["active"]:
        con.close()
        return False

    if admin["role"] == "superadmin":
        con.close()
        return True

    row = cur.execute(
        """
        SELECT id
        FROM admin_permissions
        WHERE
            admin_id = ?
            AND permission = ?
            AND
            (
                service_id = ?
                OR service_id IS NULL
            )
            AND
            (
                system_id = ?
                OR system_id IS NULL
            )
        LIMIT 1
        """,
        (
            admin_id,
            permission,
            service_id,
            system_id
        )
    ).fetchone()

    con.close()

    return row is not None


def add_file(
    request_id,
    customer_id=None,
    admin_id=None,
    field_name="",
    original_name="",
    stored_name="",
    file_type="",
    downloadable=1
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO files
        (
            request_id,
            customer_id,
            admin_id,
            field_name,
            original_name,
            stored_name,
            file_type,
            downloadable,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            customer_id,
            admin_id,
            field_name,
            original_name,
            stored_name,
            file_type,
            downloadable,
            now()
        )
    )

    file_id = cur.lastrowid

    con.commit()
    con.close()

    return file_id


def add_financial_transaction(
    amount,
    transaction_type="income",
    category="",
    description="",
    request_id=None,
    customer_id=None,
    admin_id=None,
    reference=""
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO financial_transactions
        (
            request_id,
            customer_id,
            admin_id,
            type,
            category,
            amount,
            description,
            reference,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            customer_id,
            admin_id,
            transaction_type,
            category,
            amount,
            description,
            reference,
            now()
        )
    )

    transaction_id = cur.lastrowid

    con.commit()
    con.close()

    return transaction_id


def add_payment(
    customer_id,
    request_id,
    amount,
    gateway="",
    tracking_id="",
    transaction_id="",
    status="pending"
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO payments
        (
            customer_id,
            request_id,
            amount,
            status,
            tracking_id,
            transaction_id,
            gateway,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            request_id,
            amount,
            status,
            tracking_id,
            transaction_id,
            gateway,
            now()
        )
    )

    payment_id = cur.lastrowid

    con.commit()
    con.close()

    return payment_id


def mark_payment_paid(payment_id, transaction_id=""):

    con = get_connection()
    cur = con.cursor()

    payment = cur.execute(
        """
        SELECT * FROM payments
        WHERE id = ?
        """,
        (payment_id,)
    ).fetchone()

    if not payment:
        con.close()
        return False

    if payment["status"] == "paid":
        con.close()
        return False

    current_time = now()

    cur.execute(
        """
        UPDATE payments
        SET status = 'paid',
            transaction_id = ?,
            paid_at = ?
        WHERE id = ?
        """,
        (
            transaction_id,
            current_time,
            payment_id
        )
    )

    if payment["request_id"]:
        cur.execute(
            """
            UPDATE requests
            SET paid_price = paid_price + ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                payment["amount"],
                current_time,
                payment["request_id"]
            )
        )

    cur.execute(
        """
        INSERT INTO financial_transactions
        (
            request_id,
            customer_id,
            type,
            category,
            amount,
            description,
            reference,
            created_at
        )
        VALUES (?, ?, 'income', ?, ?, ?, ?, ?)
        """,
        (
            payment["request_id"],
            payment["customer_id"],
            "پرداخت مشتری",
            payment["amount"],
            "پرداخت آنلاین خدمت",
            transaction_id,
            current_time
        )
    )

    if payment["customer_id"]:
        cur.execute(
            """
            INSERT INTO notifications
            (
                customer_id,
                request_id,
                title,
                message,
                is_read,
                created_at
            )
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                payment["customer_id"],
                payment["request_id"],
                "پرداخت موفق",
                "پرداخت شما با موفقیت ثبت شد.",
                current_time
            )
        )

    con.commit()
    con.close()

    return True


def add_discount_code(
    code,
    kind="percent",
    value=0,
    start_date=None,
    end_date=None,
    max_uses=0,
    service_id=None
):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO discount_codes
        (
            code,
            kind,
            value,
            start_date,
            end_date,
            max_uses,
            used_count,
            service_id,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, 1)
        """,
        (
            code,
            kind,
            value,
            start_date,
            end_date,
            max_uses,
            service_id
        )
    )

    code_id = cur.lastrowid

    con.commit()
    con.close()

    return code_id


def use_discount_code(code):

    con = get_connection()
    cur = con.cursor()

    row = cur.execute(
        """
        SELECT * FROM discount_codes
        WHERE code = ?
        AND active = 1
        """,
        (code,)
    ).fetchone()

    if not row:
        con.close()
        return None

    if row["max_uses"] > 0 and row["used_count"] >= row["max_uses"]:
        con.close()
        return None

    cur.execute(
        """
        UPDATE discount_codes
        SET used_count = used_count + 1
        WHERE id = ?
        """,
        (row["id"],)
    )

    con.commit()
    con.close()

    return row


def get_setting(key, default=""):

    con = get_connection()
    cur = con.cursor()

    row = cur.execute(
        """
        SELECT value FROM settings
        WHERE key = ?
        """,
        (key,)
    ).fetchone()

    con.close()

    return row["value"] if row else default


def set_setting(key, value):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (key, value)
    )

    con.commit()
    con.close()


def unread_customer_notifications(customer_id):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT *
        FROM notifications
        WHERE customer_id = ?
        AND is_read = 0
        ORDER BY id DESC
        """,
        (customer_id,)
    ).fetchall()

    con.close()

    return rows


def unread_admin_notifications(admin_id):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT *
        FROM notifications
        WHERE admin_id = ?
        AND is_read = 0
        ORDER BY id DESC
        """,
        (admin_id,)
    ).fetchall()

    con.close()

    return rows


def get_customer_notifications(customer_id, limit=50):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT *
        FROM notifications
        WHERE customer_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (customer_id, limit)
    ).fetchall()

    con.close()

    return rows


def get_admin_notifications(admin_id, limit=50):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT *
        FROM notifications
        WHERE admin_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (admin_id, limit)
    ).fetchall()

    con.close()

    return rows


def mark_notification_read(notification_id):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        """,
        (notification_id,)
    )

    con.commit()
    con.close()


def mark_all_customer_notifications_read(customer_id):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE customer_id = ?
        """,
        (customer_id,)
    )

    con.commit()
    con.close()


def mark_all_admin_notifications_read(admin_id):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE admin_id = ?
        """,
        (admin_id,)
    )

    con.commit()
    con.close()


def set_admin_notification_permission(admin_id, enabled):

    con = get_connection()
    cur = con.cursor()

    cur.execute(
        """
        UPDATE admins
        SET notifications_enabled = ?
        WHERE id = ?
        """,
        (
            1 if enabled else 0,
            admin_id
        )
    )

    con.commit()
    con.close()


def get_request_history(request_id):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT
            request_history.*,
            admins.name AS admin_name
        FROM request_history
        LEFT JOIN admins
            ON admins.id = request_history.admin_id
        WHERE request_history.request_id = ?
        ORDER BY request_history.id ASC
        """,
        (request_id,)
    ).fetchall()

    con.close()

    return rows


def get_request_messages(request_id):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT
            messages.*,
            admins.name AS admin_name
        FROM messages
        LEFT JOIN admins
            ON admins.id = messages.sender_admin_id
        WHERE messages.request_id = ?
        ORDER BY messages.id ASC
        """,
        (request_id,)
    ).fetchall()

    con.close()

    return rows


def get_support_messages(customer_id):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT
            messages.*,
            admins.name AS admin_name,
            requests.tracking_code
        FROM messages
        INNER JOIN requests
            ON requests.id = messages.request_id
        LEFT JOIN admins
            ON admins.id = messages.sender_admin_id
        WHERE requests.customer_id = ?
        AND requests.service_id IS NULL
        ORDER BY messages.id ASC
        """,
        (customer_id,)
    ).fetchall()

    con.close()

    return rows


def get_customer_requests(customer_id):

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT
            requests.*,
            services.name AS service_name,
            admins.name AS admin_name
        FROM requests
        LEFT JOIN services
            ON services.id = requests.service_id
        LEFT JOIN admins
            ON admins.id = requests.assigned_admin_id
        WHERE requests.customer_id = ?
        ORDER BY requests.id DESC
        """,
        (customer_id,)
    ).fetchall()

    con.close()

    return rows


def get_financial_transactions():

    con = get_connection()
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT
            financial_transactions.*,
            customers.name AS customer_name,
            admins.name AS admin_name
        FROM financial_transactions
        LEFT JOIN customers
            ON customers.id = financial_transactions.customer_id
        LEFT JOIN admins
            ON admins.id = financial_transactions.admin_id
        ORDER BY financial_transactions.id DESC
        """
    ).fetchall()

    con.close()

    return rows


def get_financial_summary():

    con = get_connection()
    cur = con.cursor()

    income = cur.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM financial_transactions
        WHERE type = 'income'
        """
    ).fetchone()["total"]

    expense = cur.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM financial_transactions
        WHERE type = 'expense'
        """
    ).fetchone()["total"]

    con.close()

    return {
        "income": income,
        "expense": expense,
        "balance": income - expense
    }


if __name__ == "__main__":
    create_tables()
    print("Database initialized successfully.")
