# =========================
# 📦 IMPORTS
# =========================

import os
import time
import threading
import queue
from contextlib import contextmanager
from collections import defaultdict

import psycopg2
import telebot
from telebot.types import InputMediaPhoto, InputMediaVideo


# =========================
# ⚙ CONFIGURATION
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
FIRST_ADMIN_ID = 8046643349 # replace with your Telegram ID for initial admin access


REQUIRED_MEDIA = 12
INACTIVITY_LIMIT = 6 * 60 * 60  # 6 hours

bot = telebot.TeleBot(BOT_TOKEN)

broadcast_queue = queue.Queue()
media_groups = defaultdict(list)
album_timers = {}
# =========================
# 🗄 DATABASE CONNECTION
# =========================

from contextlib import contextmanager

@contextmanager
def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()
# =========================
# 🧱 DATABASE INITIALIZATION
# =========================

def init_db():

    with get_connection() as conn:
        with conn.cursor() as c:

            # =========================
            # USERS TABLE
            # =========================
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT UNIQUE,
                    banned BOOLEAN DEFAULT FALSE,
                    auto_banned BOOLEAN DEFAULT FALSE,
                    whitelisted BOOLEAN DEFAULT FALSE,
                    activation_media_count INTEGER DEFAULT 0,
                    total_media_sent INTEGER DEFAULT 0,
                    last_activation_time BIGINT
                )
            """)

            # =========================
            # ADMINS TABLE
            # =========================
            c.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id BIGINT PRIMARY KEY
                )
            """)

            # =========================
            # MESSAGE MAP TABLE
            # =========================
            c.execute("""
                CREATE TABLE IF NOT EXISTS message_map (
                    bot_message_id BIGINT,
                    original_user_id BIGINT,
                    receiver_id BIGINT,
                    created_at BIGINT
                )
            """)

            # =========================
            # BANNED WORDS TABLE
            # =========================
            c.execute("""
                CREATE TABLE IF NOT EXISTS banned_words (
                    word TEXT PRIMARY KEY
                )
            """)

            # =========================
            # SETTINGS TABLE
            # =========================
            c.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Default Join Setting
            c.execute("""
                INSERT INTO settings(key, value)
                VALUES('join_open', 'true')
                ON CONFLICT DO NOTHING
            """)
            # =========================
            # FIRST ADMIN INIT
            # =========================

            first_admin = os.getenv("FIRST_ADMIN_ID")

            if first_admin:
                try:
                    first_admin = int(first_admin)

                    c.execute("""
                        INSERT INTO admins(user_id)
                        VALUES(%s)
                        ON CONFLICT DO NOTHING
                    """, (first_admin,))

                    print("First admin ensured.")

                except Exception as e:
                    print("Admin init error:", e)

# =========================
# 👤 USER EXISTENCE
# =========================

def user_exists(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT 1 FROM users WHERE user_id=%s",
                (user_id,)
            )
            return c.fetchone() is not None


def add_user(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO users(user_id)
                VALUES(%s)
                ON CONFLICT DO NOTHING
            """, (user_id,))
# =========================
# 🏷 USERNAME HELPERS
# =========================

def get_username(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT username FROM users WHERE user_id=%s",
                (user_id,)
            )
            row = c.fetchone()
            return row[0] if row else None


def set_username(user_id, username):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                UPDATE users
                SET username=%s
                WHERE user_id=%s
            """, (username.lower(), user_id))


def username_taken(username):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT 1 FROM users WHERE username=%s",
                (username.lower(),)
            )
            return c.fetchone() is not None
# =========================
# 👑 ADMIN HELPERS
# =========================

def is_admin(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT 1 FROM admins WHERE user_id=%s",
                (user_id,)
            )
            return c.fetchone() is not None


def add_admin(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO admins(user_id)
                VALUES(%s)
                ON CONFLICT DO NOTHING
            """, (user_id,))


def remove_admin(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "DELETE FROM admins WHERE user_id=%s",
                (user_id,)
            )
def build_prefix(user_id):

    username = get_username(user_id)

    if username:
        return f"👤 @{username}\n\n"

    return "👤 Unknown\n\n"

# =========================
# 🚫 BAN HELPERS
# =========================

def is_banned(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT banned FROM users WHERE user_id=%s",
                (user_id,)
            )
            row = c.fetchone()
            return row and row[0]


def ban_user(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET banned=TRUE WHERE user_id=%s",
                (user_id,)
            )


def unban_user(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET banned=FALSE WHERE user_id=%s",
                (user_id,)
            )
# =========================
# ⭐ WHITELIST HELPERS
# =========================

def is_whitelisted(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT whitelisted FROM users WHERE user_id=%s",
                (user_id,)
            )
            row = c.fetchone()
            return row and row[0]


def whitelist_user(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET whitelisted=TRUE WHERE user_id=%s",
                (user_id,)
            )


def remove_whitelist(user_id):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE users SET whitelisted=FALSE WHERE user_id=%s",
                (user_id,)
            )
# =========================
# 🚪 JOIN CONTROL
# =========================

def is_join_open():
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT value FROM settings WHERE key='join_open'"
            )
            row = c.fetchone()
            return row and row[0] == "true"


def set_join_status(status: bool):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                UPDATE settings
                SET value=%s
                WHERE key='join_open'
            """, ("true" if status else "false",))
# =========================
# 🧠 USER STATE RESOLVER
# =========================

def get_user_state(user_id):

    if is_admin(user_id):
        return "ADMIN"

    if is_banned(user_id):
        return "BANNED"

    if is_whitelisted(user_id):
        return "ACTIVE"

    username = get_username(user_id)

    if username is None:
        return "NO_USERNAME"

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT auto_banned, last_activation_time
                FROM users
                WHERE user_id=%s
            """, (user_id,))
            row = c.fetchone()

    if not row:
        return "JOINING"

    auto_banned, last_activation_time = row

    if auto_banned:
        return "INACTIVE"

    if last_activation_time is None:
        return "JOINING"

    return "ACTIVE"
# =========================
# 🧠 USER STATE RESOLVER
# =========================

def get_user_state(user_id):

    if is_admin(user_id):
        return "ADMIN"

    if is_banned(user_id):
        return "BANNED"

    if is_whitelisted(user_id):
        return "ACTIVE"

    username = get_username(user_id)

    if username is None:
        return "NO_USERNAME"

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT auto_banned, last_activation_time
                FROM users
                WHERE user_id=%s
            """, (user_id,))
            row = c.fetchone()

    if not row:
        return "JOINING"

    auto_banned, last_activation_time = row

    if auto_banned:
        return "INACTIVE"

    if last_activation_time is None:
        return "JOINING"

    return "ACTIVE"
# =========================
# 📊 GET ACTIVATION DATA
# =========================

def get_activation_data(user_id):
    """
    Returns:
        activation_media_count,
        total_media_sent,
        auto_banned,
        last_activation_time
    """

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT activation_media_count,
                       total_media_sent,
                       auto_banned,
                       last_activation_time
                FROM users
                WHERE user_id=%s
            """, (user_id,))
            return c.fetchone()
# =========================
# 📈 INCREMENT MEDIA
# =========================

def increment_media(user_id, amount=1):

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                UPDATE users
                SET activation_media_count = activation_media_count + %s,
                    total_media_sent = total_media_sent + %s
                WHERE user_id=%s
            """, (amount, amount, user_id))
# =========================
# 🔄 ACTIVATE USER
# =========================

def activate_user(user_id):

    now = int(time.time())

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                UPDATE users
                SET activation_media_count = 0,
                    auto_banned = FALSE,
                    last_activation_time = %s
                WHERE user_id=%s
            """, (now, user_id))
# =========================
# ✅ CHECK ACTIVATION
# =========================

def check_activation(user_id):

    data = get_activation_data(user_id)

    if not data:
        return False

    activation_count, _, _, _ = data

    if activation_count >= REQUIRED_MEDIA:
        activate_user(user_id)
        return True

    return False
# =========================
# ⏳ AUTO INACTIVITY CHECK
# =========================

def auto_ban_inactive_users():

    limit = int(time.time()) - INACTIVITY_LIMIT

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                UPDATE users
                SET auto_banned = TRUE,
                    activation_media_count = 0
                WHERE auto_banned = FALSE
                  AND last_activation_time IS NOT NULL
                  AND last_activation_time < %s
            """, (limit,))
# =========================
# 🚪 START COMMAND
# =========================

@bot.message_handler(commands=['start'])
def start_command(message):

    user_id = message.chat.id

    # 🚫 Manual Ban
    if is_banned(user_id):
        bot.send_message(user_id, "🚫 You are banned.")
        return

    # 👑 Admin Auto Registration
    if is_admin(user_id):
        if not user_exists(user_id):
            add_user(user_id)

        if get_username(user_id) is None:
            set_username(user_id, "admin")

        bot.send_message(user_id, "👑 Admin access granted.")
        return

    # 🆕 New User
    if not user_exists(user_id):

        if not is_join_open():
            bot.send_message(
                user_id,
                "🚪 Joining is currently closed."
            )
            return

        add_user(user_id)

    # 🏷 Ask Username If Not Set
    if get_username(user_id) is None:
        bot.send_message(
            user_id,
            "👋 Welcome!\n\nPlease drop your username:"
        )
        return

    # 🧠 Show Current State
    state = get_user_state(user_id)

    if state == "JOINING":
        bot.send_message(
            user_id,
            f"🔒 Send {REQUIRED_MEDIA} media to join."
        )

    elif state == "INACTIVE":
        bot.send_message(
            user_id,
            f"⏳ You are inactive.\nSend {REQUIRED_MEDIA} media to reactivate."
        )

    else:
        bot.send_message(user_id, "👋 Welcome back!")
# =========================
# 🏷 USERNAME CAPTURE
# =========================

@bot.message_handler(
    func=lambda m: get_username(m.chat.id) is None,
    content_types=['text']
)
def capture_username(message):

    user_id = message.chat.id
    username = message.text.strip().lower()

    # Prevent commands being treated as username
    if username.startswith('/'):
        return

    if len(username) < 3:
        bot.send_message(user_id, "Username too short. Try again.")
        return

    if username_taken(username):
        bot.send_message(user_id, "Username already taken. Try another.")
        return

    set_username(user_id, username)

    bot.send_message(
        user_id,
        f"✅ Username @{username} set.\n\nNow send {REQUIRED_MEDIA} media to join."
    )
# =========================
# 🚫 BANNED WORD CHECK
# =========================

def contains_banned_word(text):

    if not text:
        return False

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT word FROM banned_words")
            words = [row[0] for row in c.fetchall()]

    text = text.lower()

    for word in words:
        if word in text:
            return True

    return False
# =========================
# 🔒 HANDLE RESTRICTIONS
# =========================

def handle_restrictions(message):

    user_id = message.chat.id
    state = get_user_state(user_id)

    # 🚫 Manual Ban
    if state == "BANNED":
        bot.send_message(user_id, "🚫 You are banned.")
        return True

    # 👑 Admin Bypass
    if state == "ADMIN":
        return False

    # ⭐ Whitelisted = Always Active
    if is_whitelisted(user_id):
        return False

    # 🚫 Word Filter (text only)
    if message.content_type == "text":
        if contains_banned_word(message.text):
            bot.send_message(user_id, "🚫 Message contains banned word.")
            return True

    # ❌ No Username Yet
    if state == "NO_USERNAME":
        bot.send_message(
            user_id,
            "⚠️ Please set username first using /start."
        )
        return True

    # =========================
    # 🟡 JOINING STATE
    # =========================
    if state == "JOINING":

        if message.content_type in ['photo', 'video']:

            increment_media(user_id)
            activated = check_activation(user_id)

            if activated:
                bot.send_message(
                    user_id,
                    "🎉 You are now active for 6 hours!"
                )
            else:
                remaining = REQUIRED_MEDIA - get_activation_data(user_id)[0]
                bot.send_message(
                    user_id,
                    f"📸 {remaining} media left to join."
                )

            return False  # allow relay

        bot.send_message(
            user_id,
            f"🔒 Send {REQUIRED_MEDIA} media to join."
        )
        return True

    # =========================
    # 🔴 INACTIVE STATE
    # =========================
    if state == "INACTIVE":

        if message.content_type in ['photo', 'video']:

            increment_media(user_id)
            activated = check_activation(user_id)

            if activated:
                bot.send_message(
                    user_id,
                    "🎉 You are reactivated for 6 hours!"
                )
            else:
                remaining = REQUIRED_MEDIA - get_activation_data(user_id)[0]
                bot.send_message(
                    user_id,
                    f"📸 {remaining} media left to reactivate."
                )

            return False  # allow relay

        bot.send_message(
            user_id,
            f"⏳ You are inactive.\nSend {REQUIRED_MEDIA} media to reactivate."
        )
        return True

    # =========================
    # 🟢 ACTIVE STATE
    # =========================
    if state == "ACTIVE":

        if message.content_type in ['photo', 'video']:

            increment_media(user_id)
            renewed = check_activation(user_id)

            if renewed:
                bot.send_message(
                    user_id,
                    "🔄 6 hour cycle renewed."
                )

        return False

    return False
# =========================
# 📥 GET ACTIVE RECEIVERS
# =========================

def get_active_receivers():

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT user_id
                FROM users
                WHERE banned = FALSE
                  AND username IS NOT NULL
                  AND (
                        (auto_banned = FALSE AND last_activation_time IS NOT NULL)
                        OR whitelisted = TRUE
                      )
            """)
            return [row[0] for row in c.fetchall()]
# =========================
# 📝 SAVE MESSAGE MAP
# =========================

def save_mapping(bot_msg_id, original_user_id, receiver_id):

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO message_map
                (bot_message_id, original_user_id, receiver_id, created_at)
                VALUES (%s, %s, %s, %s)
            """, (
                bot_msg_id,
                original_user_id,
                receiver_id,
                int(time.time())
            ))
# =========================
# 🚀 BROADCAST WORKER
# =========================

def broadcast_worker():

    while True:
        job = broadcast_queue.get()

        try:
            if job["type"] == "single":
                _process_single(job["message"])

            elif job["type"] == "album":
                _process_album(job["messages"])

        except Exception as e:
            print("Broadcast error:", e)

        broadcast_queue.task_done()
# =========================
# 📤 PROCESS SINGLE MESSAGE
# =========================

def _process_single(message):

    sender_id = message.chat.id
    receivers = get_active_receivers()

    for user_id in receivers:

        if user_id == sender_id:
            continue

        try:
            # sent = bot.copy_message(
            #     chat_id=user_id,
            #     from_chat_id=sender_id,
            #     message_id=message.message_id
            # )
            prefix = build_prefix(sender_id)

            if message.content_type == "text":
                sent = bot.send_message(
                    user_id,
                    prefix + message.text
                )

            elif message.content_type == "photo":
                sent = bot.send_photo(
                    user_id,
                    message.photo[-1].file_id,
                    caption=prefix + (message.caption or "")
                )

            elif message.content_type == "video":
                sent = bot.send_video(
                    user_id,
                    message.video.file_id,
                    caption=prefix + (message.caption or "")
                )


            save_mapping(
                sent.message_id,
                sender_id,
                user_id
            )

            time.sleep(0.04)  # rate control

        except Exception as e:
            print("Single send error:", e)
# =========================
# 📸 PROCESS ALBUM MESSAGE
# =========================

def _process_album(messages):
    for index, msg in enumerate(messages):

    caption = msg.caption or ""

    if index == 0:
        caption = build_prefix(sender_id) + caption

    if msg.content_type == "photo":
        media_objects.append(
            InputMediaPhoto(
                media=msg.photo[-1].file_id,
                caption=caption
            )
        )

    elif msg.content_type == "video":
        media_objects.append(
            InputMediaVideo(
                media=msg.video.file_id,
                caption=caption
            )
        )

    sender_id = messages[0].chat.id
    receivers = get_active_receivers()

    media_objects = []

    for msg in messages:

        if msg.content_type == "photo":
            media_objects.append(
                InputMediaPhoto(
                    media=msg.photo[-1].file_id,
                    caption=msg.caption if msg.caption else None
                )
            )

        elif msg.content_type == "video":
            media_objects.append(
                InputMediaVideo(
                    media=msg.video.file_id,
                    caption=msg.caption if msg.caption else None
                )
            )

    # Split into chunks of 10
    chunks = [
        media_objects[i:i+10]
        for i in range(0, len(media_objects), 10)
    ]

    for user_id in receivers:

        if user_id == sender_id:
            continue

        for chunk in chunks:

            try:
                sent_msgs = bot.send_media_group(
                    user_id,
                    chunk
                )

                for sent in sent_msgs:
                    save_mapping(
                        sent.message_id,
                        sender_id,
                        user_id
                    )

                time.sleep(0.04)

            except Exception as e:
                print("Album send error:", e)
# =========================
# 🔁 RELAY HANDLER
# =========================

@bot.message_handler(
    func=lambda m: not m.text or not m.text.startswith('/'),
    content_types=['text', 'photo', 'video']
)
def relay(message):

    # Step 1: Apply restrictions
    if handle_restrictions(message):
        return

    # Step 2: Album Handling
    if message.media_group_id:

        group_id = message.media_group_id
        media_groups[group_id].append(message)

        if group_id in album_timers:
            return

        def finalize():
            time.sleep(0.8)

            album = media_groups.pop(group_id, [])
            album_timers.pop(group_id, None)

            if album:
                broadcast_queue.put({
                    "type": "album",
                    "messages": album
                })

        album_timers[group_id] = True
        threading.Thread(target=finalize).start()

    else:
        # Single message
        broadcast_queue.put({
            "type": "single",
            "message": message
        })
# =========================
# ⏳ INACTIVITY SCHEDULER
# =========================

def inactivity_scheduler():

    while True:
        try:
            auto_ban_inactive_users()
        except Exception as e:
            print("Inactivity scheduler error:", e)

        time.sleep(60)  # check every 60 seconds
# =========================
# 🧹 MESSAGE MAP CLEANUP
# =========================

MAP_RETENTION_DAYS = 7

def message_map_cleanup_scheduler():

    while True:
        try:
            cutoff = int(time.time()) - (MAP_RETENTION_DAYS * 86400)

            with get_connection() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        DELETE FROM message_map
                        WHERE created_at < %s
                    """, (cutoff,))
        except Exception as e:
            print("Cleanup error:", e)

        time.sleep(3600)  # run every hour
# =========================
# 🚀 START BACKGROUND WORKERS
# =========================

def start_background_workers():

    # Broadcast Worker
    threading.Thread(
        target=broadcast_worker,
        daemon=True
    ).start()

    # Inactivity Scheduler
    threading.Thread(
        target=inactivity_scheduler,
        daemon=True
    ).start()

    # Cleanup Scheduler
    threading.Thread(
        target=message_map_cleanup_scheduler,
        daemon=True
    ).start()
    
# =========================
# ADMIN COMMANDS
# ========================
@bot.message_handler(commands=['stats'])
def stats_command(message):

    if not is_admin(message.chat.id):
        return

    with get_connection() as conn:
        with conn.cursor() as c:

            c.execute("SELECT COUNT(*) FROM users")
            total = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM users
                WHERE banned=FALSE
                  AND auto_banned=FALSE
                  AND last_activation_time IS NOT NULL
            """)
            active = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM users WHERE auto_banned=TRUE")
            inactive = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM users WHERE banned=TRUE")
            banned = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM users WHERE whitelisted=TRUE")
            whitelisted = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM message_map")
            map_count = c.fetchone()[0]

    join_status = "OPEN" if is_join_open() else "CLOSED"

    bot.send_message(
        message.chat.id,
        f"""
📊 BOT STATS

👥 Total: {total}
🟢 Active: {active}
🔴 Inactive: {inactive}
🚫 Banned: {banned}
⭐ Whitelisted: {whitelisted}

📦 Message Map Rows: {map_count}
🚪 Join: {join_status}
        """
    )
@bot.message_handler(commands=['info'])
def info_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /info USER_ID")
        return

    try:
        user_id = int(parts[1])
    except:
        bot.send_message(message.chat.id, "Invalid ID.")
        return

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT username,
                       banned,
                       auto_banned,
                       whitelisted,
                       activation_media_count,
                       total_media_sent,
                       last_activation_time
                FROM users
                WHERE user_id=%s
            """, (user_id,))
            row = c.fetchone()

    if not row:
        bot.send_message(message.chat.id, "User not found.")
        return

    username, banned, auto_banned, whitelisted, act_count, total_media, last_time = row

    bot.send_message(
        message.chat.id,
        f"""
👤 USER INFO

🆔 ID: {user_id}
🏷 Username: {username}
📸 Activation Media: {act_count}
📦 Total Media Sent: {total_media}

🚫 Manual Ban: {banned}
⏳ Auto Ban: {auto_banned}
⭐ Whitelisted: {whitelisted}

🕒 Last Activation: {last_time}
        """
    )
@bot.message_handler(commands=['ban'])
def ban_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /ban USER_ID")
        return

    try:
        target_id = int(parts[1])
    except:
        bot.send_message(message.chat.id, "Invalid ID.")
        return

    ban_user(target_id)
    bot.send_message(message.chat.id, "User banned.")
@bot.message_handler(commands=['unban'])
def unban_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /unban USER_ID")
        return

    try:
        target_id = int(parts[1])
    except:
        bot.send_message(message.chat.id, "Invalid ID.")
        return

    unban_user(target_id)
    bot.send_message(message.chat.id, "User unbanned.")
@bot.message_handler(commands=['addadmin'])
def addadmin_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        return

    add_admin(int(parts[1]))
    bot.send_message(message.chat.id, "Admin added.")
@bot.message_handler(commands=['removeadmin'])
def removeadmin_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        return

    remove_admin(int(parts[1]))
    bot.send_message(message.chat.id, "Admin removed.")
@bot.message_handler(commands=['openjoin'])
def openjoin_command(message):

    if not is_admin(message.chat.id):
        return

    set_join_status(True)
    bot.send_message(message.chat.id, "Join opened.")
@bot.message_handler(commands=['closejoin'])
def closejoin_command(message):

    if not is_admin(message.chat.id):
        return

    set_join_status(False)
    bot.send_message(message.chat.id, "Join closed.")
@bot.message_handler(commands=['clearmap'])
def clearmap_command(message):

    if not is_admin(message.chat.id):
        return

    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM message_map")

    bot.send_message(message.chat.id, "Message map cleared.")
@bot.message_handler(commands=['whitelist'])
def whitelist_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /whitelist USER_ID")
        return

    try:
        target_id = int(parts[1])
    except:
        bot.send_message(message.chat.id, "Invalid USER_ID.")
        return

    whitelist_user(target_id)

    bot.send_message(
        message.chat.id,
        f"⭐ User {target_id} added to whitelist."
    )
@bot.message_handler(commands=['whitelist'])
def whitelist_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /whitelist USER_ID")
        return

    try:
        target_id = int(parts[1])
    except:
        bot.send_message(message.chat.id, "Invalid USER_ID.")
        return

    whitelist_user(target_id)

    bot.send_message(
        message.chat.id,
        f"⭐ User {target_id} added to whitelist."
    )
@bot.message_handler(commands=['unwhitelist'])
def unwhitelist_command(message):

    if not is_admin(message.chat.id):
        return

    parts = message.text.split()

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /unwhitelist USER_ID")
        return

    try:
        target_id = int(parts[1])
    except:
        bot.send_message(message.chat.id, "Invalid USER_ID.")
        return

    remove_whitelist(target_id)

    bot.send_message(
        message.chat.id,
        f"❌ User {target_id} removed from whitelist."
    )
@bot.message_handler(commands=['adminmenu'])
def admin_menu(message):

    if not is_admin(message.chat.id):
        return

    bot.send_message(
        message.chat.id,
        """
🛠 ADMIN COMMAND MENU

📊 /stats  
→ Show bot statistics

🔎 /info USER_ID  
→ View user details

🚫 /ban USER_ID  
→ Manually ban user

✅ /unban USER_ID  
→ Remove manual ban

⭐ /whitelist USER_ID  
→ Bypass activation/inactivity

❌ /unwhitelist USER_ID  
→ Remove whitelist access

👑 /addadmin USER_ID  
→ Add new admin

🗑 /removeadmin USER_ID  
→ Remove admin

🚪 /openjoin  
→ Allow new users to join

🔒 /closejoin  
→ Stop new users from joining

🧹 /clearmap  
→ Clear message mapping table

📦 /addword WORD  
→ Add banned word

❌ /removeword WORD  
→ Remove banned word

📃 /words  
→ Show banned words list
        """
    )

# =========================
# 🚀 MAIN BOOT
# =========================

if __name__ == "__main__":

    print("🤖 Starting bot...")

    init_db()
    print("✅ Database ready.")

    start_background_workers()
    print("✅ Background workers running.")

    bot.infinity_polling(skip_pending=True)
