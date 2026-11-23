import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request


def ensure_packages():
    required = [
        ("flask", "flask==3.0.3"),
        ("flask_cors", "flask-cors==4.0.1"),
        ("dotenv", "python-dotenv==1.0.1"),
    ]
    for mod_name, pip_spec in required:
        try:
            __import__(mod_name)
        except ImportError:
            try:
                subprocess.check_call(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--quiet",
                        "--disable-pip-version-check",
                        pip_spec,
                    ]
                )
            except Exception:
                pass


ensure_packages()

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

BOT_NAME = os.getenv("BOT_NAME", "𝑽𝑰𝑷 𝑻𝑨𝑺𝑲").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "@Vip_TaSk_Pro_BoT").strip().lstrip("@")
BOT_TOKEN = os.getenv("BOT_TOKEN", "9027022496:AAFpf93krbdO5iRzwZU6Tq_Ts_Nm3LybXAM").strip()
ADMIN_CHAT_IDS = {
    x.strip() for x in os.getenv("ADMIN_CHAT_IDS", "7940269685").split(",") if x.strip()
}
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://mini-website-and-mini-bot.blogspot.com").strip()
BACKEND_API_URL = os.getenv(
    "BACKEND_API_URL", "https://vip-task-8p8i.onrender.com"
).strip().rstrip("/")
FIREBASE_DB_URL = (
    os.getenv(
        "FIREBASE_DB_URL",
        "https://telegram-mini-bot-7e19a-default-rtdb.firebaseio.com",
    )
    .strip()
    .rstrip("/")
)
PORT = int(os.getenv("PORT", "10000"))

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


def http_json(url: str, method: str = "GET", payload: dict | None = None):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def tg_api(method: str, params: dict | None = None):
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN missing"}
    query = urllib.parse.urlencode(params or {})
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if query:
        url = f"{url}?{query}"
    return http_json(url, method="GET")


def tg_send(chat_id: str, text: str, reply_markup: dict | None = None):
    if not BOT_TOKEN:
        return
    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        body["reply_markup"] = reply_markup
    try:
        http_json(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            method="POST",
            payload=body,
        )
    except Exception:
        pass


def tg_answer_callback(callback_query_id: str, text: str = "", show_alert: bool = False):
    if not BOT_TOKEN or not callback_query_id:
        return
    try:
        http_json(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            method="POST",
            payload={
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
            },
        )
    except Exception:
        pass


def parse_channel_chat_id(link_or_id: str) -> str:
    raw = (link_or_id or "").strip()
    if not raw:
        return ""
    if raw.startswith("-100") and raw[1:].isdigit():
        return raw
    if raw.startswith("https://t.me/"):
        slug = raw[len("https://t.me/") :].split("?")[0].strip("/")
        if slug and not slug.startswith("+") and not slug.startswith("joinchat"):
            return "@" + slug.split("/")[0]
        return ""
    if raw.startswith("http://t.me/"):
        slug = raw[len("http://t.me/") :].split("?")[0].strip("/")
        if slug and not slug.startswith("+") and not slug.startswith("joinchat"):
            return "@" + slug.split("/")[0]
        return ""
    if raw.startswith("@"):
        return raw
    if raw.replace("_", "").isalnum():
        return "@" + raw
    return ""


def real_verify_channel_member(chat_id: str, user_id: str) -> tuple[bool, str]:
    if not chat_id:
        return False, "এই টাস্কের সঠিক চ্যানেল লিংক বা Chat ID সেট করা নেই।"
    try:
        res = tg_api("getChatMember", {"chat_id": chat_id, "user_id": user_id})
    except Exception as exc:
        return False, f"Telegram সার্ভার চেক করা যাচ্ছে না: {exc}"

    if not res.get("ok"):
        desc = (res.get("description") or "").lower()
        if "chat not found" in desc:
            return False, "চ্যানেল খুঁজে পাওয়া যায়নি (প্রাইভেট চ্যানেল হলে -100 ID দিন)।"
        if "user not found" in desc:
            return False, "ইউজার খুঁজে পাওয়া যায়নি।"
        if (
            "bot is not a member" in desc
            or "forbidden" in desc
            or "need administrator" in desc
            or "member list is inaccessible" in desc
        ):
            return (
                False,
                "প্রথমে বটটিকে ওই চ্যানেলে Admin করুন, তারপর ভেরিফিকেশন করুন।",
            )
        return False, res.get("description") or "ভেরিফাই করা যায়নি।"

    member = res.get("result") or {}
    status = (member.get("status") or "").lower()
    if status in ("creator", "administrator", "member"):
        return True, "verified"
    if status == "restricted" and bool(member.get("is_member", False)):
        return True, "verified"
    return False, "not_joined"


def fb_get(path: str):
    url = f"{FIREBASE_DB_URL}/{path.lstrip('/')}.json"
    return http_json(url, method="GET")


def fb_patch(path: str, data: dict):
    url = f"{FIREBASE_DB_URL}/{path.lstrip('/')}.json"
    return http_json(url, method="PATCH", payload=data)


def fb_push(path: str, data: dict):
    url = f"{FIREBASE_DB_URL}/{path.lstrip('/')}.json"
    return http_json(url, method="POST", payload=data)


def verify_and_credit_user(
    user_id: str,
    first_name: str,
    task_id: str,
    fallback_title: str = "",
    fallback_link: str = "",
    fallback_chat_id: str = "",
) -> tuple[bool, str]:
    task_data = fb_get(f"tasks/{task_id}")
    if not isinstance(task_data, dict):
        task_data = {}

    title = str(task_data.get("title") or fallback_title or task_id)
    channel_link = str(
        task_data.get("link")
        or task_data.get("channel_link")
        or fallback_link
        or ""
    )
    chat_id = (
        str(task_data.get("chat_id") or fallback_chat_id or "").strip()
        or parse_channel_chat_id(channel_link)
    )
    reward = float(task_data.get("reward") or 0)

    if not task_data and not chat_id:
        return False, "❌ এই টাস্কটি খুঁজে পাওয়া যায়নি।"

    user_data = fb_get(f"users/{user_id}") or {}
    completed_tasks = user_data.get("completedTasks") or {}
    if isinstance(completed_tasks, dict) and completed_tasks.get(task_id):
        return True, "✅ আপনি ইতিমধ্যে এই টাস্ক সম্পন্ন করেছেন এবং রিওয়ার্ড পেয়েছেন।"

    joined, reason = real_verify_channel_member(chat_id, user_id)
    if not joined:
        if reason == "not_joined":
            return (
                False,
                "❌ ভেরিফিকেশন ব্যর্থ! আপনি এখনো চ্যানেলে জয়েন করেননি। আগে চ্যানেলে জয়েন করুন, তারপর আবার ভেরিফাই চাপুন।",
            )
        return False, f"❌ {reason}"

    current_balance = float(user_data.get("balance") or 0)
    current_task_count = int(user_data.get("tasksCompletedCount") or 0)
    current_completed_count = int(task_data.get("completedCount") or 0)

    new_balance = current_balance + reward
    new_task_count = current_task_count + 1

    fb_patch(
        f"users/{user_id}",
        {
            "userId": str(user_id),
            "firstName": first_name or str(user_data.get("firstName") or "User"),
            "balance": new_balance,
            "tasksCompletedCount": new_task_count,
            f"completedTasks/{task_id}": True,
        },
    )
    if task_data:
        fb_patch(f"tasks/{task_id}", {"completedCount": current_completed_count + 1})

    fb_push(
        f"users/{user_id}/notifications",
        {
            "title": f"টাস্ক সম্পন্ন: {title}",
            "message": f'আপনি চ্যানেলে জয়েন করে "{title}" টাস্ক ভেরিফাই করেছেন এবং +৳{reward:.2f} পেয়েছেন।',
            "time": time.strftime("%H:%M"),
        },
    )
    return True, f"🎉 আসল ভেরিফিকেশন সফল! আপনার ওয়ালেটে +৳{reward:.2f} যোগ হয়েছে।"


def send_welcome_only(chat_id: str, first_name: str):
    if WEBAPP_URL and (
        WEBAPP_URL.startswith("https://") or WEBAPP_URL.startswith("http://")
    ):
        markup = {
            "inline_keyboard": [
                [{"text": "𝐕𝐈𝐏 𝐓𝐀𝐒𝐊 𝐎𝐏𝐄𝐍", "web_app": {"url": WEBAPP_URL}}]
            ]
        }
    else:
        markup = {
            "keyboard": [[{"text": "𝐕𝐈𝐏 𝐓𝐀𝐒𝐊 𝐎𝐏𝐄𝐍"}]],
            "resize_keyboard": True,
        }

    tg_send(
        chat_id,
        f"স্বাগতম, <b>{first_name}</b>! 🎉\n\nনিচে <b>𝐕𝐈𝐏 𝐓𝐀𝐒𝐊 𝐎𝐏𝐄𝐍</b> বাটনে চেপে Mini App / Mini Bot-এ প্রবেশ করুন।",
        reply_markup=markup,
    )


def send_tasks_menu(chat_id: str, user_id: str):
    tasks_obj = fb_get("tasks")
    if not isinstance(tasks_obj, dict) or not tasks_obj:
        tg_send(chat_id, "বর্তমানে কোনো টাস্ক পাওয়া যায়নি।")
        return

    user_data = fb_get(f"users/{user_id}") or {}
    completed_tasks = user_data.get("completedTasks") or {}

    tg_send(
        chat_id,
        "📋 <b>চ্যানেল টাস্কসমূহ:</b>\nআগে চ্যানেলে জয়েন করুন, তারপর <b>ভেরিফাই ও ক্লেইম</b> বাটনে চাপুন।",
    )
    for task_id, t in tasks_obj.items():
        if not isinstance(t, dict):
            continue
        title = t.get("title", task_id)
        reward = float(t.get("reward", 0))
        link = t.get("link") or t.get("channel_link") or ""
        is_done = bool(
            isinstance(completed_tasks, dict) and completed_tasks.get(task_id)
        )

        rows = []
        if link and (link.startswith("https://") or link.startswith("http://")):
            rows.append([{"text": "📢 চ্যানেলে জয়েন করুন", "url": link}])
        if is_done:
            rows.append(
                [{"text": "✅ সম্পন্ন হয়েছে", "callback_data": f"done:{task_id}"}]
            )
        else:
            rows.append(
                [
                    {
                        "text": "🔍 ভেরিফাই ও ক্লেইম",
                        "callback_data": f"verify:{task_id}",
                    }
                ]
            )

        tg_send(
            chat_id,
            f"• <b>{title}</b>\n💰 রিওয়ার্ড: <b>+৳{reward:.2f}</b>",
            reply_markup={"inline_keyboard": rows},
        )


def run_bot_polling():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN সেট করা নেই।")
        return

    print(f"🚀 {BOT_NAME} (@{BOT_USERNAME}) polling চালু হয়েছে...")
    offset = None

    while True:
        try:
            params = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            res = tg_api("getUpdates", params)
            if not res.get("ok"):
                time.sleep(2)
                continue

            for upd in res.get("result", []):
                offset = upd["update_id"] + 1

                if "message" in upd:
                    msg = upd["message"]
                    text = (msg.get("text") or "").strip()
                    sender = msg.get("from") or {}
                    user_id = str(sender.get("id", ""))
                    first_name = sender.get("first_name", "User")
                    chat_id = str((msg.get("chat") or {}).get("id", ""))

                    if not text or not chat_id or not user_id:
                        continue

                    if text.startswith("/start") or text == "𝐕𝐈𝐏 𝐓𝐀𝐒𝐊 𝐎𝐏𝐄𝐍":
                        send_welcome_only(chat_id, first_name)
                    elif text.startswith("/tasks"):
                        send_tasks_menu(chat_id, user_id)
                    elif text.startswith("/balance") or text.startswith("/wallet"):
                        u = fb_get(f"users/{user_id}") or {}
                        bal = float(u.get("balance") or 0)
                        tg_send(
                            chat_id,
                            f"💼 আপনার বর্তমান ওয়ালেট ব্যালেন্স: <b>৳{bal:.2f}</b>",
                        )
                    elif text.startswith("/addtask"):
                        if ADMIN_CHAT_IDS and user_id not in ADMIN_CHAT_IDS:
                            tg_send(
                                chat_id, "❌ শুধু অ্যাডমিন টাস্ক যোগ করতে পারবেন।"
                            )
                            continue
                        raw = text[len("/addtask") :].strip()
                        parts = [p.strip() for p in raw.split("|")]
                        if len(parts) < 4:
                            tg_send(
                                chat_id,
                                "ব্যবহার: <code>/addtask task_1 | Join VIP Channel | https://t.me/yourchannel | 5</code>",
                            )
                            continue
                        t_id, t_title, t_link, t_reward_str = parts[:4]
                        parsed_chat = parse_channel_chat_id(t_link)
                        if not parsed_chat:
                            tg_send(chat_id, "❌ চ্যানেল লিংক বা Chat ID সঠিক নয়।")
                            continue
                        try:
                            t_reward = float(t_reward_str)
                        except ValueError:
                            tg_send(chat_id, "❌ রিওয়ার্ড অবশ্যই সংখ্যা হতে হবে।")
                            continue

                        fb_patch(
                            f"tasks/{t_id}",
                            {
                                "title": t_title,
                                "link": t_link,
                                "chat_id": parsed_chat,
                                "reward": t_reward,
                                "totalLimit": 1000,
                                "completedCount": 0,
                            },
                        )
                        tg_send(
                            chat_id,
                            f"✅ টাস্ক যুক্ত হয়েছে: <b>{t_title}</b> (ID: <code>{t_id}</code>, রিওয়ার্ড: +৳{t_reward:.2f})",
                        )

                elif "callback_query" in upd:
                    cq = upd["callback_query"]
                    cq_id = cq.get("id", "")
                    data = (cq.get("data") or "").strip()
                    sender = cq.get("from") or {}
                    user_id = str(sender.get("id", ""))
                    first_name = sender.get("first_name", "User")
                    chat_id = str(
                        ((cq.get("message") or {}).get("chat") or {}).get(
                            "id", user_id
                        )
                    )

                    if data.startswith("verify:"):
                        task_id = data.split(":", 1)[1].strip()
                        tg_answer_callback(cq_id, "চ্যানেল জয়েন যাচাই করা হচ্ছে...")
                        _, msg_text = verify_and_credit_user(
                            user_id, first_name, task_id
                        )
                        tg_send(chat_id, msg_text)
                    elif data.startswith("done:"):
                        tg_answer_callback(
                            cq_id,
                            "এই টাস্কটি ইতিমধ্যে সম্পন্ন হয়েছে।",
                            show_alert=True,
                        )

        except Exception as exc:
            print(f"⚠️ Polling error: {exc}")
            time.sleep(3)


@app.route("/", methods=["GET"])
def home():
    return jsonify(
        {
            "ok": True,
            "bot_name": BOT_NAME,
            "bot_username": f"@{BOT_USERNAME}",
            "backend_api_url": BACKEND_API_URL,
            "service": "VIP TASK Bot Server Running",
        }
    )


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify(
        {
            "ok": True,
            "bot_configured": bool(BOT_TOKEN),
            "backend_api_url": BACKEND_API_URL,
        }
    )


@app.route("/api/verify-task", methods=["POST"])
def api_verify_task():
    body = request.get_json(silent=True) or {}
    user_id = str(body.get("user_id") or "").strip()
    first_name = str(body.get("first_name") or "User").strip()
    task_id = str(body.get("task_id") or "").strip()
    fallback_title = str(body.get("task_title") or "").strip()
    fallback_link = str(body.get("channel_link") or "").strip()
    fallback_chat_id = str(body.get("chat_id") or "").strip()

    if not user_id or not task_id:
        return (
            jsonify(
                {
                    "ok": False,
                    "verified": False,
                    "message": "user_id ও task_id প্রয়োজন।",
                }
            ),
            400,
        )

    ok, msg = verify_and_credit_user(
        user_id=user_id,
        first_name=first_name,
        task_id=task_id,
        fallback_title=fallback_title,
        fallback_link=fallback_link,
        fallback_chat_id=fallback_chat_id,
    )
    return jsonify({"ok": ok, "verified": ok, "message": msg})


if __name__ == "__main__":
    threading.Thread(target=run_bot_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
