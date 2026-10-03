# ─────────────────────────────────────────────
#  القائمة السوداء (أشخاص يتطردوا فورًا عند تفعيل أي "Clan VS Clan")
#  حط آيدي رقمي واحد في كل سطر جوه الأقواس. تقدر تضيف/تشيل في أي وقت،
#  والتعديل هيتفعّل من غير ما تحتاج تلمس أي حتة تانية في الكود.
# ─────────────────────────────────────────────
BANNED_USER_IDS_MANUAL = {}

import random
import re
import asyncio
import json
import os
import threading
import inspect
from io import BytesIO
from datetime import datetime, timezone, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    filters, ContextTypes
)
from flask import Flask

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.messages import ImportChatInviteRequest
    from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
    from telethon.errors import (
        UserAlreadyParticipantError, InviteHashExpiredError,
        InviteHashInvalidError, FloodWaitError,
    )
except ImportError as _telethon_import_error:
    import sys
    TelegramClient = None
    print(f"⚠️ فشل استيراد Telethon: {_telethon_import_error}")
    print(f"⚠️ البايثون اللي البوت شغال بيه دلوقتي: {sys.executable}")
    print("⚠️ لو مثبتها فعلاً وبرضو بتظهر الرسالة دي، غالبًا مثبتها في بايثون/بيئة تانية"
          " غير اللي شغّلت بيها البوت. جرب تشغّل الأمر ده بنفس الطريقة اللي بتشغل بيها البوت:")
    print("     python3 -c \"import sys; print(sys.executable)\"")
    print("   وبعدين ثبّت المكتبة بنفس البايثون ده تحديدًا، مثلاً:")
    print("     /المسار/اللي_ظهر/python -m pip install telethon")

try:
    import httpx
except ImportError:
    httpx = None
    print("⚠️ مكتبة httpx مش متثبتة — الحكم الآلي بالذكاء الاصطناعي مش هيشتغل. ثبّتها بـ: pip install httpx")

# ─────────────────────────────────────────────
#  Flask
# ─────────────────────────────────────────────
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    web_app.run(host='0.0.0.0', port=7860)

# ─────────────────────────────────────────────
#  إعدادات
# ─────────────────────────────────────────────
TOKEN                = os.environ.get("BOT_TOKEN")
RESULTS_DESTINATION  = 8911160665  # آيدي الشخص/الجروب اللي هيوصله رابط المواجهة

# ── إعدادات جلسة Telethon (لحساب التاكات من الهستوري) ──
TELETHON_API_ID         = 26604893  # ← حط الـ API_ID بتاعك هنا (رقم)
TELETHON_API_HASH       = "b4dad6237531036f1a4bb2580e4985b1"
TELETHON_SESSION_STRING = os.environ.get("TELETHON_SESSION_STRING", "")
AU_LINK             = "https://t.me/arab_union3"

# ── مسار التخزين الدائم ──
DATA_DIR = os.environ.get("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

def _dp(filename: str) -> str:
    """يرجع مسار الملف جوه فولدر التخزين الدائم."""
    return os.path.join(DATA_DIR, filename)

def _migrate_if_needed(filename: str):
    new_path = _dp(filename)
    old_path = os.path.join(".", filename)
    if DATA_DIR != "." and not os.path.exists(new_path) and os.path.exists(old_path):
        try:
            import shutil
            shutil.copy2(old_path, new_path)
            print(f"📦 اترحّل {filename} من المسار القديم لـ {new_path}")
        except Exception as e:
            print(f"⚠️ فشل ترحيل {filename}: {e}")

for _f in ("war_data.json", "stage_images.json", "war_rules.txt",
           "maintenance_lock.json", "known_groups.json", "warnings.json"):
    _migrate_if_needed(_f)

DATA_FILE           = _dp("war_data.json")
IMAGES_FILE         = _dp("stage_images.json")
RULES_FILE          = _dp("war_rules.txt")

# ── إعدادات الحكم الآلي بالذكاء الاصطناعي (Gemini — مجاني تماماً وسريع) ──
GEMINI_API_KEYS = [
    os.environ.get("GEMINI_API_KEY_1", ""),
    os.environ.get("GEMINI_API_KEY_2", ""),
    os.environ.get("GEMINI_API_KEY_3", ""),
    os.environ.get("GEMINI_API_KEY_4", ""),
    os.environ.get("GEMINI_API_KEY_5", ""),
    os.environ.get("GEMINI_API_KEY_6", ""),
    os.environ.get("GEMINI_API_KEY_7", ""),
]
# ملحوظة: "gemini-flash-latest" هو alias متحرك بيتغير تبعيته مع كل نسخة جديدة
# من جوجل، وده بيسبب أحيانًا 404/503 وقت التبديل بين النسخ. استخدام اسم نسخة
# ثابت زي اللي تحت أكثر استقرارًا على المدى الطويل.
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# كام مرة يعيد الدورة كاملة على كل المفاتيح لو كلهم فشلوا بـ 429/503
GEMINI_MAX_ROUNDS = 3
# مدة الانتظار (ثواني) قبل إعادة كل دورة (بتزيد تدريجيًا)
GEMINI_RETRY_BASE_DELAY = 2

# ── كليشة بدء المواجهة ──
WAR_START_CLICHE_IMAGE = "referee_cliche.jpg"
WAR_START_CLICHE_TEXT = (
    "بعد تنزيل قائمتك، يرجى الرد على القائمة بكلمة \"قائمة\" ثم كتابة شعار كلانك.\n\n"
    "مثال:\n"
    "قائمة STO\n\n"
    "سيتم بعدها تثبيت القائمة، وإجراء القرعة بشكل تلقائي وبكل سهولة، وذلك لتجنب الإهمال. \n\n"
    "#كادر_التحكيم\n\n"
    "لأي شكوى أو استفسار، يرجى التواصل مع مسؤول الحكام: @z6_i3"
)

TIME_REMIND_1 = 2 * 24 * 3600
TIME_REMIND_2 = 3 * 24 * 3600
TIME_AUTO_END = 6 * 3600

# ── قفل التحديث ──
MAINTENANCE_FILE          = _dp("maintenance_lock.json")
MAINTENANCE_REOPEN_HOUR   = 11
MAINTENANCE_REOPEN_WEEKDAY = 3

MAINTENANCE_CLOSE_TEXT = (
    "<b>📰 تـنـبـيـه إداري\n\n"
    "⚠️ سـيـبـدأ تـحـديـث لـعـبـة بـيـس مـوبـايـل، ولـن يـكـون بـالإمـكـان الـلـعـب أثـنـاء فـتـرة الـتـحـديـث.\n\n"
    "🚫 لـذا سـيـتـم غـلـق جـمـيـع الـمـواجـهـات إلـى حـيـن انـتـهـاء الـتـحـديـث و عـودة الـلـعـبـة لـلـعـمـل.\n\n"
    "🙏 شـاكـريـن لـكـم تـعـاونـكـم وتـفـهـمـكـم.\n\n"
    "مـسـؤول الـحـكـام @z6_i3</b>"
)

MAINTENANCE_REOPEN_TEXT = "✅ انتهت مدة التحديث، وتم فتح اللعبة مرة أخرى."

RESPONSIBLE_USERNAMES = {"leeeeeeeeevvi", "z6_i3"}

# ── قائمة الأشخاص المحظورين ──
# أول ما يتفعل "Clan VS Clan" في أي جروب، البوت بيدوّر على كل عضو من القائمة
# دي جوه الجروب ده ويطرده فورًا. عدّل القائمة من أول سطرين في الملف
# (BANNED_USER_IDS_MANUAL)، مش من هنا.
BANNED_USER_IDS = BANNED_USER_IDS_MANUAL
BANNED_USERNAMES: set = set()  # اتشالت لصالح الآيديهات الرقمية (أدق وأضمن)

# ─────────────────────────────────────────────
#  طرد صامت وفوري لأي حد في القائمة السوداء
#  (مش بس وقت تفعيل Clan VS Clan — دلوقتي بيتفحص مع كل رسالة/دخول عضو،
#  في أي وقت، في أي جروب موجود فيه البوت، من غير أي إعلان في الجروب)
# ─────────────────────────────────────────────
async def _silent_kick_if_banned(context, chat, user_obj, message_id=None) -> bool:
    """لو الشخص ده موجود في BANNED_USER_IDS، بيتطرد فورًا وبصمت تام (من غير
    أي رسالة تعلن الطرد جوه الجروب). بترجع True لو فعلاً اتطرد."""
    if not user_obj or user_obj.id not in BANNED_USER_IDS:
        return False
    if not chat or chat.type not in ("group", "supergroup"):
        return False
    try:
        await context.bot.ban_chat_member(chat.id, user_obj.id)
    except Exception as e:
        print(f"❌ فشل الطرد الصامت للآيدي المحظور {user_obj.id} من الجروب {chat.id}: {e}")
        return False
    if message_id:
        try:
            await context.bot.delete_message(chat.id, message_id)
        except Exception:
            pass
    print(f"🚫 طرد صامت لآيدي محظور ({user_obj.id}) من الجروب {chat.id}.")
    return True

def is_tag_admin(user, is_creator: bool) -> bool:
    if is_creator:
        return True
    if user and user.username and user.username.lower() in RESPONSIBLE_USERNAMES:
        return True
    return False

LOCAL_TZ_OFFSET_HOURS = 2
OFF_HOURS_START = 2
OFF_HOURS_END   = 9

def _is_off_hours(msg_dt) -> bool:
    local_dt = msg_dt + timedelta(hours=LOCAL_TZ_OFFSET_HOURS)
    return OFF_HOURS_START <= local_dt.hour < OFF_HOURS_END

ROSTER_HOURS_16_QUARTER = 14
ROSTER_HOURS_SEMI_FINAL = 18

STAGES = ["دور الـ 16", "ربع النهائي", "نصف النهائي", "النهائي", "دوري"]

STAGE_QUESTION = (
    "❓ ما هو دور المواجهة؟\n\n"
    "1️⃣ دور الـ 16\n"
    "2️⃣ ربع النهائي\n"
    "3️⃣ نصف النهائي\n"
    "4️⃣ النهائي\n"
    "5️⃣ دوري / أدوار أخرى"
)

SETIMAGE_ALIASES = {
    "دور16": "دور الـ 16", "دور 16": "دور الـ 16", "16": "دور الـ 16",
    "ربع": "ربع النهائي", "ربعنهائي": "ربع النهائي",
    "نصف": "نصف النهائي", "نصفنهائي": "نصف النهائي",
    "نهائي": "النهائي", "final": "النهائي",
    "دوري": "دوري", "اخرى": "دوري", "أخرى": "دوري",
}

LINK_TRIGGERS = {"الرابط", "رابط", "لينك", "link", "الينك"}
TAG_COUNT_TRIGGERS = {"احسب تاكات", "احسب التاكات", "احسب تكات", "احسب التكات"}
GROUPS_LIST_TRIGGERS = {"الجروبات", "كل الجروبات", "جروبات"}
GROUPS_FILE = _dp("known_groups.json")

def detect_stage(text: str):
    t = text.strip()
    c = clean(t)
    if t == "1" or "16" in t:                        return "دور الـ 16"
    if t == "2" or "ربع" in c:                        return "ربع النهائي"
    if t == "3" or ("نصف" in c and "نهائ" in c):     return "نصف النهائي"
    if t == "4" or (("نهائ" in c or "نهايي" in c) and "نصف" not in c and "ربع" not in c): return "النهائي"
    if t == "5" or "دوري" in c or "اخر" in c or "ادوار" in c: return "دوري"
    return None

# ─────────────────────────────────────────────
#  صور الأدوار
# ─────────────────────────────────────────────
stage_images: dict = {}

def load_images():
    global stage_images
    if os.path.exists(IMAGES_FILE):
        try:
            with open(IMAGES_FILE, 'r', encoding='utf-8') as f:
                stage_images = json.load(f)
            print(f"✅ صور محملة: {list(stage_images.keys())}")
        except Exception as e:
            print(f"❌ خطأ في تحميل الصور: {e}")
            stage_images = {}

def save_images():
    try:
        with open(IMAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(stage_images, f, ensure_ascii=False, indent=2)
        print("✅ تم حفظ الصور")
    except Exception as e:
        print(f"❌ خطأ في حفظ الصور: {e}")

# ─────────────────────────────────────────────
#  قوانين المواجهات (الدستور)
# ─────────────────────────────────────────────
WAR_CONSTITUTION = """__PLACEHOLDER_CONSTITUTION__"""

war_rules_text: str = WAR_CONSTITUTION

def load_rules():
    global war_rules_text
    war_rules_text = WAR_CONSTITUTION
    print(f"✅ الدستور محمّل من جوه الكود ({len(war_rules_text)} حرف)")

_gemini_key_idx = 0

async def _call_gemini(prompt: str) -> str:
    """
    بتنادي Gemini API وبتتناوب بين المفاتيح (round-robin)، وبتعيد الدورة كاملة
    عدة مرات (GEMINI_MAX_ROUNDS) لو كل المفاتيح فشلت بـ 429 (حد الاستخدام) أو
    503 (السيرفر مشغول مؤقتًا عند جوجل) — مع فاصل زمني متزايد بين كل دورة.
    """
    global _gemini_key_idx
    keys = [k for k in GEMINI_API_KEYS if k and not k.startswith("ضع_")]
    if not keys:
        raise RuntimeError("مفيش مفاتيح Gemini متظبطة في GEMINI_API_KEYS.")

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    last_err = "غير معروف"

    async with httpx.AsyncClient(timeout=30) as client:
        for round_num in range(GEMINI_MAX_ROUNDS):
            for _ in range(len(keys)):
                key_pos = _gemini_key_idx % len(keys)
                key = keys[key_pos]
                _gemini_key_idx += 1
                try:
                    resp = await client.post(
                        GEMINI_URL, headers={"x-goog-api-key": key}, json=payload
                    )
                    if resp.status_code == 429:
                        last_err = f"429 (تخطي حد الاستخدام) على المفتاح رقم {key_pos + 1}"
                        print(f"⚠️ Gemini {last_err}")
                        continue
                    if resp.status_code == 503:
                        last_err = f"503 (سيرفر Gemini مشغول مؤقتًا) على المفتاح رقم {key_pos + 1}"
                        print(f"⚠️ Gemini {last_err}")
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception as e:
                    last_err = f"{type(e).__name__}: {e}"
                    print(f"⚠️ Gemini خطأ على المفتاح رقم {key_pos + 1}: {last_err}")
                    continue

            # كل المفاتيح فشلت في الدورة دي. لو لسه فيه دورات، استنى شوية وحاول تاني.
            if round_num < GEMINI_MAX_ROUNDS - 1:
                delay = GEMINI_RETRY_BASE_DELAY * (round_num + 1)
                print(f"⏳ كل المفاتيح فشلت في الدورة {round_num + 1}، استنى {delay} ثانية وحاول تاني...")
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"كل المفاتيح ({len(keys)}) فشلت بعد {GEMINI_MAX_ROUNDS} محاولة. آخر خطأ: {last_err}"
    )

async def ask_ai_judge(objection_text: str, objector: str, w: dict) -> str:
    if httpx is None:
        return "⚠️ الحكم الآلي مش شغال — مكتبة httpx مش متثبتة على السيرفر (pip install httpx)."

    match_state = "\n".join(
        f"{i+1}. {m['p1']} {m['s1']} - {m['s2']} {m['p2']}"
        for i, m in enumerate(w.get("matches", []))
    ) or "لا يوجد مباريات مسجلة بعد."

    rules_block = war_rules_text or "(مفيش دستور محمّل حاليًا — احكم بمنطق عام وعدل.)"

    prompt = (
        "انت حكم رسمي لمواجهات كلانات. اقرا الدستور/القوانين كاملة تحت، وبعدين اقرا "
        "تفاصيل الاعتراض، واحكم بالعدل طبقًا لبنود القوانين فقط من غير تحيز لأي طرف.\n\n"
        f"══ الدستور/القوانين ══\n{rules_block}\n\n"
        f"══ وضع المواجهة الحالي ══\n"
        f"{w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
        f"{match_state}\n\n"
        f"══ الاعتراض ══\n"
        f"مقدّم الاعتراض: {objector}\n"
        f"نص الاعتراض:\n{objection_text}\n\n"
        "اكتب حكمك بالعربي بالظبط بالشكل ده:\n"
        "القرار: (اعتراض مقبول / اعتراض مرفوض / حكم جزئي)\n"
        "السبب: (اشرح باختصار مستنداً لبند معين في الدستور لو موجود)\n"
        "الإجراء المطلوب: (إيه اللي المفروض يتغير، أو \"لا يوجد\" لو مفيش)"
    )

    try:
        return await _call_gemini(prompt)
    except Exception as e:
        print(f"❌ خطأ في الحكم الآلي: {e}")
        return f"⚠️ حصل خطأ أثناء طلب الحكم الآلي: {e}"

async def ask_ai_general(question: str, asker: str, w: dict | None) -> str:
    if httpx is None:
        return "⚠️ الرد الآلي مش شغال — مكتبة httpx مش متثبتة على السيرفر (pip install httpx)."

    state_block = ""
    if w:
        state_block = (
            f"\n\n══ وضع المواجهة الحالية في هذا الجروب ══\n"
            f"{w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
            f"الدور: {w.get('stage','غير محدد')}"
        )

    rules_block = war_rules_text or "(مفيش دستور محمّل حاليًا.)"

    prompt = (
        "انت مساعد حكم رسمي لمواجهات كلانات، وشغلتك ترد على أي سؤال أو استفسار "
        "بالاعتماد حصريًا على الدستور/القوانين اللي تحت. اقرا الدستور كويس واستنتج "
        "الإجابة الأدق طبقًا لبنوده، ولو السؤال مش له علاقة بالدستور رد بشكل عام ومهذب.\n\n"
        f"══ الدستور/القوانين ══\n{rules_block}\n"
        f"{state_block}\n\n"
        f"══ رسالة الشخص ══\n"
        f"من: {asker}\n"
        f"النص: {question}\n\n"
        "رد بالعربي بشكل مباشر وواضح ومختصر، واذكر البند أو القانون اللي اعتمدت عليه لو موجود."
    )

    try:
        return await _call_gemini(prompt)
    except Exception as e:
        print(f"❌ خطأ في الرد الآلي: {e}")
        return f"⚠️ حصل خطأ أثناء طلب الرد الآلي: {e}"

async def restrict_profane_user(context, chat_id: int, user_id: int) -> bool:
    """يقيّد المستخدم (يمنعه من الكتابة/الإرسال) بدون طرده. يرجع True لو نجح."""
    try:
        await context.bot.restrict_chat_member(
            chat_id, user_id,
            ChatPermissions(
                can_send_messages=False, can_send_audios=False, can_send_documents=False,
                can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
        )
        return True
    except Exception as e:
        print(f"❌ خطأ في تقييد المستخدم {user_id} بسبب السب: {e}")
        return False

async def unrestrict_user(context, chat_id: int, user_id: int) -> bool:
    """يرفع التقييد عن المستخدم ويرجّعله صلاحيات الكتابة العادية."""
    try:
        await context.bot.restrict_chat_member(
            chat_id, user_id,
            ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
        return True
    except Exception as e:
        print(f"❌ خطأ في رفع التقييد عن المستخدم {user_id}: {e}")
        return False



#  فحص المحتوى المرئي (صور / فيديو / ستيكرز) — إباحي / دموي / أسلحة
#  بيستخدم Gemini Vision (نفس مفاتيح النص) لتصنيف الصورة مباشرة، من غير
#  أي قائمة كلمات، لأن التصنيف هنا بصري مش نصي.
# ─────────────────────────────────────────────
GEMINI_VISION_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
GEMINI_VISION_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_VISION_MODEL}:generateContent"

async def _call_gemini_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    """زي _call_gemini لكن بترفق صورة/فريم فيديو كـ base64 مع البرومبت."""
    global _gemini_key_idx
    import base64
    keys = [k for k in GEMINI_API_KEYS if k and not k.startswith("ضع_")]
    if not keys:
        raise RuntimeError("مفيش مفاتيح Gemini متظبطة في GEMINI_API_KEYS.")

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64_data}},
            ]
        }]
    }
    last_err = "غير معروف"
    async with httpx.AsyncClient(timeout=30) as client:
        for round_num in range(GEMINI_MAX_ROUNDS):
            for _ in range(len(keys)):
                key_pos = _gemini_key_idx % len(keys)
                key = keys[key_pos]
                _gemini_key_idx += 1
                try:
                    resp = await client.post(
                        GEMINI_VISION_URL, headers={"x-goog-api-key": key}, json=payload
                    )
                    if resp.status_code in (429, 503):
                        last_err = f"{resp.status_code} على المفتاح رقم {key_pos + 1}"
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception as e:
                    last_err = f"{type(e).__name__}: {e}"
                    continue
            if round_num < GEMINI_MAX_ROUNDS - 1:
                await asyncio.sleep(GEMINI_RETRY_BASE_DELAY * (round_num + 1))
    raise RuntimeError(f"كل المفاتيح فشلوا في فحص الصورة. آخر خطأ: {last_err}")

VISION_UNSAFE_PROMPT = (
    "افحص هذه الصورة وقول لي هل تحتوي على أي من التالي بشكل واضح:\n"
    "- محتوى إباحي أو جنسي صريح أو شبه عاري\n"
    "- محتوى دموي أو عنيف بشكل صادم (دماء، إصابات، قتل، تعذيب)\n"
    "- أسلحة حقيقية (نارية أو بيضاء) بشكل تهديدي أو ترويجي\n\n"
    "الصور الرياضية العادية، الشعارات، الميمز العادية، أو الأسلحة داخل ألعاب "
    "فيديو/رسوم كرتونية بشكل غير واقعي لا تعتبر مخالفة.\n"
    "رد بكلمة واحدة فقط بدون أي شرح: YES لو فيها مخالفة، NO لو سليمة."
)

async def is_unsafe_media(image_bytes: bytes, mime_type: str) -> bool:
    """يرجع True لو الصورة/الفريم فيه إباحي/دموي/سلاح."""
    if httpx is None or not image_bytes:
        return False
    try:
        result = await _call_gemini_vision(image_bytes, mime_type, VISION_UNSAFE_PROMPT)
        return result.strip().upper().startswith("YES")
    except Exception as e:
        print(f"❌ خطأ في فحص المحتوى المرئي: {e}")
        return False

# ─────────────────────────────────────────────
#  البيانات
# ─────────────────────────────────────────────
wars = {}

def save():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(wars, f, ensure_ascii=False, indent=2)

def load():
    global wars
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        wars = {int(k): v for k, v in data.items()}
        print("✅ بيانات محملة")

def now_ts():
    return datetime.now(timezone.utc).timestamp()

def emoji(n):
    d = {'0':'0️⃣','1':'1️⃣','2':'2️⃣','3':'3️⃣','4':'4️⃣',
         '5':'5️⃣','6':'6️⃣','7':'7️⃣','8':'8️⃣','9':'9️⃣'}
    return "".join(d.get(c, c) for c in str(n))

def clean(text):
    if not text: return ""
    t = text.lower().strip()
    t = t.replace('ة','ه').replace('أ','ا').replace('إ','ا').replace('آ','ا')
    return t

def get_stage_from_text(text: str):
    if not text: return None
    text = text.strip()
    key = clean(text)
    if text in SETIMAGE_ALIASES:
        return SETIMAGE_ALIASES[text]
    if key in SETIMAGE_ALIASES:
        return SETIMAGE_ALIASES[key]
    return detect_stage(text)

# ─────────────────────────────────────────────
#  تسجيل كل الجروبات اللي البوت عضو/أدمن فيها
# ─────────────────────────────────────────────
known_groups: dict = {}

def load_groups():
    global known_groups
    if os.path.exists(GROUPS_FILE):
        try:
            with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                known_groups = json.load(f)
            print(f"✅ جروبات مسجلة محملة: {len(known_groups)}")
        except Exception as e:
            print(f"❌ خطأ في تحميل الجروبات: {e}")
            known_groups = {}

def save_groups():
    try:
        with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(known_groups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ خطأ في حفظ الجروبات: {e}")

def remember_chat(chat, is_admin=None, removed=None):
    if chat.type not in ("group", "supergroup"):
        return
    cid_s = str(chat.id)
    entry = known_groups.get(cid_s, {})
    entry["title"] = chat.title or entry.get("title") or "بدون اسم"
    entry["type"] = chat.type
    entry["last_seen"] = now_ts()
    if is_admin is not None:
        entry["is_admin"] = is_admin
    if removed is not None:
        entry["removed"] = removed
    entry.setdefault("removed", False)
    known_groups[cid_s] = entry
    save_groups()

async def track_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.my_chat_member
    if not cmu:
        return
    chat = cmu.chat
    new_status = cmu.new_chat_member.status
    if new_status in ("left", "kicked"):
        remember_chat(chat, removed=True)
    else:
        remember_chat(chat, is_admin=(new_status == "administrator"), removed=False)

async def track_any_member_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بيرصد أي حد بيدخل أي جروب فيه البوت (عبر تحديثات chat_member العامة)،
    ولو كان آيدي محظور يتطرد فورًا وبصمت — حتى لو دخل من غير ما يبعت أي رسالة."""
    cmu = update.chat_member
    if not cmu:
        return
    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status
    if old_status in ("member", "administrator", "creator") or new_status in ("left", "kicked"):
        return
    await _silent_kick_if_banned(context, cmu.chat, cmu.new_chat_member.user)

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طبقة حماية إضافية: رسالة الانضمام الخدمية العادية (لو ظهرت) بتتفحص
    برضو، عشان نضمن الطرد الفوري حتى لو تحديثات chat_member اتأخرت."""
    if not update.message or not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        await _silent_kick_if_banned(context, update.effective_chat, member)

async def send_groups_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = {k: v for k, v in known_groups.items() if not v.get("removed")}
    if not active:
        await update.message.reply_text(
            "📭 لسه مفيش جروبات متسجلة.\n"
            "البوت بيسجل الجروب أول ما حد يبعت فيه رسالة، أو أول ما يتضاف/يترقّى ليه."
        )
        return
    now = now_ts()
    lines = []
    for cid_s, info in sorted(active.items(), key=lambda x: -x[1].get("last_seen", 0)):
        admin_mark = "أدمن" if info.get("is_admin") else "عضو"
        last_h = (now - info.get("last_seen", now)) / 3600
        lines.append(f"{info.get('title','بدون اسم')} | {admin_mark} | {cid_s} | آخر نشاط: {last_h:.1f} ساعة")
    content = f"إجمالي الجروبات المسجلة: {len(active)}\n\n" + "\n".join(lines)
    buf = BytesIO(content.encode('utf-8'))
    buf.name = "groups.txt"
    await update.message.reply_document(
        document=buf, filename="groups.txt",
        caption=f"📋 عدد الجروبات المسجلة: {len(active)}"
    )

# ─────────────────────────────────────────────
#  قفل التحديث
# ─────────────────────────────────────────────
maintenance_state: dict = {}

def load_maintenance():
    global maintenance_state
    if os.path.exists(MAINTENANCE_FILE):
        try:
            with open(MAINTENANCE_FILE, 'r', encoding='utf-8') as f:
                maintenance_state = json.load(f)
        except Exception as e:
            print(f"❌ خطأ في تحميل حالة قفل التحديث: {e}")
            maintenance_state = {}
    else:
        maintenance_state = {}

    groups = maintenance_state.get("groups")
    if isinstance(groups, dict) and groups:
        stale = [cid_s for cid_s, v in groups.items() if not v]
        if stale:
            for cid_s in stale:
                del groups[cid_s]
            print(f"🧹 اتشالت {len(stale)} جروب متسجل غلط 'متقفل' عشان يتحاول يتقفل تاني")
            save_maintenance()

def save_maintenance():
    try:
        with open(MAINTENANCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(maintenance_state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ خطأ في حفظ حالة قفل التحديث: {e}")

def _next_maintenance_reopen_ts() -> float:
    now_utc   = datetime.now(timezone.utc)
    local_now = now_utc + timedelta(hours=LOCAL_TZ_OFFSET_HOURS)
    days_ahead = (MAINTENANCE_REOPEN_WEEKDAY - local_now.weekday()) % 7
    target_local = (local_now + timedelta(days=days_ahead)).replace(
        hour=MAINTENANCE_REOPEN_HOUR, minute=0, second=0, microsecond=0
    )
    if target_local <= local_now:
        target_local += timedelta(days=7)
    target_utc = target_local - timedelta(hours=LOCAL_TZ_OFFSET_HOURS)
    return target_utc.timestamp()

async def run_maintenance_lock_once(bot):
    if maintenance_state.get("triggered"):
        return
    maintenance_state["triggered"] = True
    maintenance_state["active"]    = True
    reopen_ts = _next_maintenance_reopen_ts()
    maintenance_state["reopen_ts"] = reopen_ts
    maintenance_state["groups"]    = {}
    save_maintenance()

    asyncio.create_task(task_reopen_maintenance(bot, max(0.0, reopen_ts - now_ts())))
    print("🔒 قفل التحديث اتفعل — كل جروب هيتقفل لوحده أول ما توصله رسالة، "
          f"والفتح التلقائي هيكون الساعة {datetime.fromtimestamp(reopen_ts, tz=timezone.utc)} (UTC)")

_CP_VALID_KEYS = set(inspect.signature(ChatPermissions.__init__).parameters.keys()) - {"self"}

def _safe_permissions_kwargs(d: dict) -> dict:
    return {k: v for k, v in (d or {}).items() if k in _CP_VALID_KEYS}

def _full_open_permissions() -> ChatPermissions:
    """صلاحيات مفتوحة بالكامل — نفس المعيار اللي بيتفتح بيه أي جروب/مواجهة
    تانية، عشان أي جروب يتفتح بيها يبقى متسق مع باقي الجروبات."""
    return ChatPermissions(**_safe_permissions_kwargs({
        "can_send_messages": True, "can_send_audios": True, "can_send_documents": True,
        "can_send_photos": True, "can_send_videos": True, "can_send_video_notes": True,
        "can_send_voice_notes": True, "can_send_polls": True, "can_send_other_messages": True,
        "can_add_web_page_previews": True, "can_change_info": True,
        "can_invite_users": True, "can_pin_messages": True,
    }))

_unlock_checking_in_progress: set = set()

async def unlock_group_if_locked(bot, chat):
    """بتتفحص مع كل رسالة، في أي جروب (سواء البوت عارفه من قبل أو لأ):
    بتقرا صلاحيات الجروب الفعلية من تليجرام مباشرة، ولو لاقت الجروب مقفول
    (can_send_messages=False) بتفتحه فورًا بنفس الإعدادات المفتوحة للمواجهات
    التانية. لو الجروب أصلاً مفتوح، ميعملش أي حاجة وميلمسش صلاحياته خالص."""
    if not chat or chat.type not in ("group", "supergroup"):
        return
    cid_s = str(chat.id)
    if cid_s in _unlock_checking_in_progress:
        return
    _unlock_checking_in_progress.add(cid_s)
    try:
        full_chat = await bot.get_chat(chat.id)
        perms = full_chat.permissions
        if perms is not None and perms.can_send_messages:
            return  # مفتوح أصلاً — نسيبه ومنلمسش حاجة
        await bot.set_chat_permissions(chat.id, _full_open_permissions())
        print(f"🔓 الجروب {chat.id} كان مقفول ووصلته رسالة، فاتفتح فورًا.")
    except Exception as e:
        print(f"⚠️ تعذّر التأكد من/فتح صلاحيات الجروب {chat.id}: {e}")
    finally:
        _unlock_checking_in_progress.discard(cid_s)

_locking_in_progress: set = set()

async def lock_group_if_needed(bot, chat):
    if not chat or chat.type not in ("group", "supergroup"):
        return
    if not maintenance_state.get("active"):
        return
    cid_s = str(chat.id)
    if cid_s in maintenance_state.get("groups", {}):
        return
    if cid_s in _locking_in_progress:
        return
    _locking_in_progress.add(cid_s)

    cid = chat.id
    try:
        full_chat = await bot.get_chat(cid)
        saved = full_chat.permissions.to_dict() if full_chat.permissions else {}

        if saved:
            locked = ChatPermissions(**{k: False for k in _safe_permissions_kwargs(saved).keys()})
        else:
            locked = ChatPermissions(
                can_send_messages=False, can_send_audios=False, can_send_documents=False,
                can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
                can_add_web_page_previews=False, can_change_info=False,
                can_invite_users=False, can_pin_messages=False,
            )
        await bot.set_chat_permissions(cid, locked)
        await bot.send_message(cid, MAINTENANCE_CLOSE_TEXT, parse_mode="HTML")

        maintenance_state.setdefault("groups", {})[cid_s] = saved
        save_maintenance()
        print(f"🔒 اتقفل الجروب {cid_s} (أول رسالة بعد تفعيل قفل التحديث)")
    except Exception as e:
        print(f"❌ خطأ في قفل الجروب {cid_s} (هيتحاول تاني أول ما توصله رسالة جديدة): {e}")
    finally:
        _locking_in_progress.discard(cid_s)

async def task_reopen_maintenance(bot, delay: float):
    if delay > 0:
        await asyncio.sleep(delay)
    if not maintenance_state.get("active"):
        return
    for cid_s, saved in list(maintenance_state.get("groups", {}).items()):
        cid = int(cid_s)
        try:
            restored = ChatPermissions(**_safe_permissions_kwargs(saved)) if saved else ChatPermissions(can_send_messages=True)
            await bot.set_chat_permissions(cid, restored)
            await bot.send_message(cid, MAINTENANCE_REOPEN_TEXT)
        except Exception as e:
            print(f"❌ خطأ في فتح الجروب {cid_s} بعد التحديث: {e}")
    maintenance_state["active"] = False
    save_maintenance()

async def open_all_groups_now(bot):
    """يفتح كل الجروبات فورًا مع كل تشغيل للبوت — من غير ما تعتمد على إن
    maintenance_lock.json محفوظ فعليًا. لو الاستضافة (زي Railway من غير
    Volume دائم) بتصفّر الملف ده مع كل ريستارت، البوت برضو هيفضل يفتح كل
    جروب معروف ليه بصلاحيات كاملة تلقائيًا — عشان محدش يفضل مقفول للأبد
    من غير ما يكون له طريقة يترجع بيها لوحده.
    """
    groups_snapshot = dict(maintenance_state.get("groups", {}))
    if maintenance_state.get("active"):
        maintenance_state["active"] = False
        maintenance_state["groups"] = {}
        save_maintenance()

    handled_ids = set()
    for cid_s, saved in groups_snapshot.items():
        cid = int(cid_s)
        try:
            restored = ChatPermissions(**_safe_permissions_kwargs(saved)) if saved else ChatPermissions(can_send_messages=True)
            await bot.set_chat_permissions(cid, restored)
            await bot.send_message(cid, MAINTENANCE_REOPEN_TEXT)
            print(f"🔓 اتفتح الجروب {cid_s} فورًا عند بدء تشغيل البوت.")
        except Exception as e:
            print(f"❌ خطأ في فتح الجروب {cid_s} فور بدء التشغيل: {e}")
        handled_ids.add(cid_s)

    # أي جروب تاني معروف للبوت (موجود جوه known_groups) نتأكد إنه مفتوح
    # برضو، بغض النظر عن حالة ملف قفل التحديث — طبقة حماية إضافية.
    for cid_s, info in list(known_groups.items()):
        if info.get("removed") or cid_s in handled_ids:
            continue
        cid = int(cid_s)
        try:
            await bot.set_chat_permissions(cid, _full_open_permissions())
        except Exception as e:
            print(f"⚠️ تعذّر التأكد من فتح الجروب {cid_s}: {e}")

    print("🔓 اتفتحت كل الجروبات فورًا عند بدء تشغيل البوت.")

# ─────────────────────────────────────────────
#  نظام الإنذارات
# ─────────────────────────────────────────────
WARNINGS_FILE = _dp("warnings.json")
warnings_data: dict = {}
admin_warning_flow: dict = {}

def load_warnings():
    global warnings_data
    if os.path.exists(WARNINGS_FILE):
        try:
            with open(WARNINGS_FILE, 'r', encoding='utf-8') as f:
                warnings_data = json.load(f)
            print(f"✅ إنذارات محملة")
        except Exception as e:
            print(f"❌ خطأ في تحميل الإنذارات: {e}")
            warnings_data = {}

def save_warnings():
    try:
        with open(WARNINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(warnings_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ خطأ في حفظ الإنذارات: {e}")

def _get_warn_entry(cid, uid) -> dict:
    cid_s, uid_s = str(cid), str(uid)
    chat_w = warnings_data.setdefault(cid_s, {})
    return chat_w.setdefault(uid_s, {"player": 0, "admin": 0})

async def resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        tag = f"@{u.username}" if u.username else f"ID:{u.id}"
        return u.id, tag

    text = msg.text or ""
    m = re.search(r'@(\w+)', text)
    if m:
        username = m.group(1)
        try:
            chat_obj = await context.bot.get_chat(f"@{username}")
            return chat_obj.id, f"@{username}"
        except Exception:
            return None, f"@{username}"

    m = re.search(r'\b(\d{5,})\b', text)
    if m:
        uid = int(m.group(1))
        tag = f"ID:{uid}"
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            if member.user.username:
                tag = f"@{member.user.username}"
        except Exception:
            pass
        return uid, tag

    return None, None

async def handle_warning_system(update: Update, context: ContextTypes.DEFAULT_TYPE, cid, is_creator: bool) -> bool:
    user = update.effective_user
    msg = update.message.text or ""
    msg_cl = clean(msg)

    flow = admin_warning_flow.get(cid)

    if flow and flow["stage"] == "grace_period" and user and user.id == flow["target_id"]:
        mentioned = re.findall(r'@\w+', msg)
        if mentioned:
            flow["replacement_tag"] = mentioned[0]
            flow["stage"] = "ask_role"
            await update.message.reply_text(
                f"✅ اتحدد {mentioned[0]} كمسؤول بديل عن {flow['target_tag']}.\n\n"
                f"👑 يا مالك الجروب: {flow['target_tag']} مسؤول فقط ولا مسؤول ولاعب؟\n"
                f"اكتب: مسؤول فقط / مسؤول ولاعب"
            )
        else:
            flow["grace_remaining"] -= 1
            if flow["grace_remaining"] <= 0:
                flow["stage"] = "ask_role"
                await update.message.reply_text(
                    f"⌛ انتهت مهلة تحديد المسؤول البديل بدون تحديد.\n\n"
                    f"👑 يا مالك الجروب: {flow['target_tag']} مسؤول فقط ولا مسؤول ولاعب؟\n"
                    f"اكتب: مسؤول فقط / مسؤول ولاعب"
                )
        return True

    if flow and flow["stage"] == "ask_replacement" and is_creator:
        if any(k in msg_cl for k in ("نعم", "ايوه", "ايوة", "اه", "حدد")):
            flow["stage"] = "ask_role"
            await update.message.reply_text(
                f"👑 يا مالك الجروب: {flow['target_tag']} مسؤول فقط ولا مسؤول ولاعب؟\n"
                f"اكتب: مسؤول فقط / مسؤول ولاعب"
            )
        elif any(k in msg_cl for k in ("لا", "لأ", "مفيش", "محددش")):
            flow["stage"] = "grace_period"
            flow["grace_remaining"] = 3
            await update.message.reply_text(
                f"⏳ حصل {flow['target_tag']} على 3 رسايل بس عشان يحدد مسؤول بديل "
                f"(منشن للبديل، مثلاً: \"قائد بدالي @user\")."
            )
        else:
            await update.message.reply_text("❓ اكتب: نعم / لأ")
        return True

    if flow and flow["stage"] == "ask_role" and is_creator:
        is_player_too = "لاعب" in msg_cl
        only_admin = ("فقط" in msg_cl) and not is_player_too
        if only_admin:
            try:
                await context.bot.ban_chat_member(cid, flow["target_id"])
                await update.message.reply_text(f"🚫 تم طرد {flow['target_tag']} من الجروب (كان مسؤول فقط).")
            except Exception as e:
                await update.message.reply_text(f"❌ حصل خطأ أثناء الطرد: {e}")
        elif is_player_too:
            await update.message.reply_text(
                f"⚠️ تم طرد {flow['target_tag']} من صلاحية القيادة، وهيفضل في الجروب كلاعب."
            )
        else:
            await update.message.reply_text("❓ اكتب: مسؤول فقط / مسؤول ولاعب")
            return True
        _get_warn_entry(cid, flow["target_id"])["admin"] = 0
        save_warnings()
        del admin_warning_flow[cid]
        return True

    is_warn_command = msg_cl.startswith("انذار") or msg_cl.startswith("الغاء انذار")
    if not is_warn_command:
        return False

    if not is_creator:
        await update.message.reply_text("🚫 الإنذارات لمالك الجروب فقط.")
        return True

    if msg_cl.startswith("الغاء انذار مسؤول"):
        uid, tag = await resolve_target(update, context)
        if not uid:
            await update.message.reply_text("❌ محدّدتش الشخص صح (رد / منشن / آيدي).")
            return True
        entry = _get_warn_entry(cid, uid)
        entry["admin"] = max(0, entry["admin"] - 1)
        save_warnings()
        await update.message.reply_text(f"↩️ اتلغى إنذار مسؤول واحد لـ {tag} ({entry['admin']}/3).")
        return True

    if msg_cl.startswith("الغاء انذار"):
        uid, tag = await resolve_target(update, context)
        if not uid:
            await update.message.reply_text("❌ محدّدتش الشخص صح (رد / منشن / آيدي).")
            return True
        entry = _get_warn_entry(cid, uid)
        entry["player"] = max(0, entry["player"] - 1)
        save_warnings()
        await update.message.reply_text(f"↩️ اتلغى إنذار واحد لـ {tag} ({entry['player']}/3).")
        return True

    if msg_cl.startswith("انذار مسؤول"):
        uid, tag = await resolve_target(update, context)
        if not uid:
            await update.message.reply_text("❌ محدّدتش الشخص صح (رد / منشن / آيدي).")
            return True
        entry = _get_warn_entry(cid, uid)
        entry["admin"] += 1
        save_warnings()
        if entry["admin"] >= 3:
            admin_warning_flow[cid] = {
                "stage": "ask_replacement", "target_id": uid, "target_tag": tag,
                "grace_remaining": 0, "replacement_tag": None,
            }
            await update.message.reply_text(
                f"🚨 {tag} وصل لـ 3 إنذارات كمسؤول.\n\n"
                f"👑 يا مالك الجروب: هل {tag} حدد مسؤول بديل بالفعل؟\n"
                f"اكتب: نعم / لأ"
            )
        else:
            await update.message.reply_text(f"⚠️ إنذار مسؤول لـ {tag} ({entry['admin']}/3).")
        return True

    if msg_cl.startswith("انذار"):
        uid, tag = await resolve_target(update, context)
        if not uid:
            await update.message.reply_text("❌ محدّدتش الشخص صح (رد / منشن / آيدي).")
            return True
        entry = _get_warn_entry(cid, uid)
        entry["player"] += 1
        if entry["player"] >= 3:
            try:
                await context.bot.ban_chat_member(cid, uid)
                await update.message.reply_text(f"🚫 تم طرد {tag} من الجروب لاستكمال 3 إنذارات.")
                entry["player"] = 0
            except Exception as e:
                await update.message.reply_text(f"❌ حصل خطأ أثناء الطرد: {e}")
        else:
            await update.message.reply_text(f"⚠️ إنذار لـ {tag} ({entry['player']}/3).")
        save_warnings()
        return True

    return False

# ─────────────────────────────────────────────
#  جلب mention المالك
# ─────────────────────────────────────────────
async def ban_blacklisted_members(context, chat_id: int) -> list:
    """
    بتدوّر على كل أعضاء الجروب وتطرد فورًا أي حد موجود في BANNED_USERNAMES
    أو BANNED_USER_IDS. بترجع قائمة بأسماء/آيديهات اللي اتطردوا فعليًا.
    ملحوظة: get_chat_administrators بس بيرجّع الأدمنز؛ عشان نفحص كل الأعضاء
    (مش الأدمنز بس) لازم نستخدم get_chat_member لكل آيدي محدد في BANNED_USER_IDS
    مباشرة، وممكن كمان نتأكد من اليوزرنيمات المعروفة بنفس الطريقة لو حابب.
    """
    if not BANNED_USERNAMES and not BANNED_USER_IDS:
        return []

    banned_now = []

    # 1) لو عندك آيديهات رقمية محددة في القائمة، بنفحصهم مباشرة (أدق وأسرع)
    for uid in BANNED_USER_IDS:
        try:
            member = await context.bot.get_chat_member(chat_id, uid)
            if member.status in ("left", "kicked"):
                continue
            await context.bot.ban_chat_member(chat_id, uid)
            tag = f"@{member.user.username}" if member.user.username else f"ID:{uid}"
            banned_now.append(tag)
            print(f"🚫 اتطرد {tag} من الجروب {chat_id} (موجود في القائمة السوداء).")
        except Exception:
            # الشخص أصلاً مش عضو في الجروب ده، أو حصل خطأ آخر — تجاهل بهدوء
            continue

    # 2) لليوزرنيمات: بما إن تليجرام مش بيديك API لسرد كل الأعضاء (خصوصية)،
    # بنحاول نجيب كل يوزرنيم كـ chat عالمي ونشوف لو عضو في الجروب ده تحديدًا
    for uname in BANNED_USERNAMES:
        uname_clean = uname.lstrip("@")
        try:
            user_chat = await context.bot.get_chat(f"@{uname_clean}")
            member = await context.bot.get_chat_member(chat_id, user_chat.id)
            if member.status in ("left", "kicked"):
                continue
            await context.bot.ban_chat_member(chat_id, user_chat.id)
            tag = f"@{uname_clean}"
            banned_now.append(tag)
            print(f"🚫 اتطرد {tag} من الجروب {chat_id} (موجود في القائمة السوداء).")
        except Exception:
            continue

    return banned_now

async def get_owner_mention(context, chat_id: int) -> str:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for a in admins:
            if a.status == 'creator':
                if a.user.username:
                    return f"@{a.user.username}"
                else:
                    return f'<a href="tg://user?id={a.user.id}">المالك</a>'
    except:
        pass
    return "مالك الجروب"

async def _flag_and_restrict(update, context, cid, w, user, u_tag, reason: str):
    """
    بيقيّد الشخص (منعه من الكتابة) ويبعت رسالة فيها تاك لمالك الجروب تشرح
    السبب وتنتظر قراره (اطرد / الغاء تقييد كـ رد على الرسالة دي). الحالة
    بتتخزن في w["pending_moderation"] لحد ما المالك يرد.
    """
    ok = await restrict_profane_user(context, cid, user.id)
    owner_mention = await get_owner_mention(context, cid)

    if ok:
        status_line = f"🔒 تم تقييد {u_tag} مؤقتًا (منع من الكتابة)."
    else:
        status_line = (
            f"⚠️ رُصدت مخالفة من {u_tag} لكن فشل التقييد "
            "(تأكد إن البوت أدمن وعنده صلاحية تقييد الأعضاء)."
        )

    alert_msg = await update.message.reply_text(
        f"{status_line}\n\n"
        f"📌 السبب: {reason}\n\n"
        f"👑 {owner_mention} برجاء الرد على هذه الرسالة بقرارك:\n"
        f"• اطرد — لطرده نهائيًا\n"
        f"• الغاء تقييد — لو المخالفة غير مقصودة وتريد رفع التقييد",
        parse_mode="HTML"
    )
    w["pending_moderation"] = {
        "target_id": user.id,
        "target_tag": u_tag,
        "alert_mid": alert_msg.message_id,
        "reason": reason,
    }
    save()

# ─────────────────────────────────────────────
#  جلب / إنشاء رابط دعوة للجروب
# ─────────────────────────────────────────────
async def get_group_invite_link(context, chat_id: int) -> str | None:
    try:
        chat = await context.bot.get_chat(chat_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
    except Exception as e:
        print(f"⚠️ get_chat فشل: {e}")

    try:
        link = await context.bot.export_chat_invite_link(chat_id)
        if link:
            return link
    except Exception as e:
        print(f"⚠️ export_chat_invite_link فشل: {e}")

    try:
        invite = await context.bot.create_chat_invite_link(chat_id)
        if invite and invite.invite_link:
            return invite.invite_link
    except Exception as e:
        print(f"❌ create_chat_invite_link فشل: {e}")

    return None

async def get_or_create_war_link(context, cid: int, w: dict) -> str | None:
    if w.get("invite_link"):
        return w["invite_link"]
    link = await get_group_invite_link(context, cid)
    if link:
        w["invite_link"] = link
        save()
    return link

async def cmd_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    w = wars.get(cid)
    if w:
        link = await get_or_create_war_link(context, cid, w)
    else:
        link = await get_group_invite_link(context, cid)
    if link:
        await update.message.reply_text(f"🔗 رابط الجروب:\n{link}")
    else:
        await update.message.reply_text(
            "❌ ما قدرتش أجيب رابط الجروب.\n"
            "تأكد إن البوت أدمن وعنده صلاحية "
            "«دعوة المستخدمين عبر رابط» (Invite Users via Link)."
        )

# ─────────────────────────────────────────────
#  إرسال رابط المواجهة
# ─────────────────────────────────────────────
async def send_war_link(context, chat_id: int, reason: str):
    w = wars.get(chat_id)
    if not w or w.get("link_sent"):
        return
    link = await get_or_create_war_link(context, chat_id, w)
    text = (
        f"📋 {reason}\n\n"
        f"⚔️ المواجهة: {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
        f"🏆 الدور: {w.get('stage','—')}\n"
        f"🔗 رابط المواجهة: {link or '—'}\n"
        f"🆔 ID الجروب: {chat_id}"
    )
    try:
        await context.bot.send_message(
            RESULTS_DESTINATION, text, disable_web_page_preview=True
        )
        w["link_sent"] = True
        save()
    except Exception as e:
        print(f"❌ فشل إرسال الرابط: {e}")

# ─────────────────────────────────────────────
#  مهلة تسليم القوائم
# ─────────────────────────────────────────────
async def auto_win_missing_roster(chat_id: int, context, w: dict, win_k: str):
    lose_k = "c2" if win_k == "c1" else "c1"
    w["active"] = False
    w["end_ts"] = now_ts()
    save()
    try:
        await context.bot.send_message(
            chat_id,
            f"⏰ انتهت مهلة تسليم القوائم ({w.get('roster_deadline_hours')} ساعة).\n"
            f"🎊 فوز إداري لكلان {w[win_k]['n']} لعدم إرسال {w[lose_k]['n']} لقائمته في الوقت."
        )
    except Exception as e:
        print(f"❌ خطأ في auto_win_missing_roster: {e}")
    asyncio.create_task(task_auto_send_after_6h(chat_id, context, TIME_AUTO_END))

async def task_check_roster_deadline(chat_id: int, context, delay: float):
    if delay > 0: await asyncio.sleep(delay)
    w = wars.get(chat_id)
    if not w or w.get("roster_deadline_done"):
        return
    if w.get("mid"):
        return
    if not w.get("active"):
        return
    w["roster_deadline_done"] = True
    save()
    p1_filled = bool(w["c1"]["p"])
    p2_filled = bool(w["c2"]["p"])
    if p1_filled and not p2_filled:
        await auto_win_missing_roster(chat_id, context, w, "c1")
    elif p2_filled and not p1_filled:
        await auto_win_missing_roster(chat_id, context, w, "c2")
    elif not p1_filled and not p2_filled:
        try:
            await context.bot.send_message(
                chat_id,
                f"⚠️ لم يتم إرسال أي قائمة خلال {w.get('roster_deadline_hours')} ساعة.\n"
                f"يحتاج الأمر تدخل الحكم لتحديد القرار يدوياً."
            )
        except Exception as e:
            print(f"❌ خطأ في تنبيه المهلة: {e}")

# ─────────────────────────────────────────────
#  مهام الخلفية
# ─────────────────────────────────────────────
async def task_remind_1(chat_id: int, context, delay: float):
    if delay > 0: await asyncio.sleep(delay)
    w = wars.get(chat_id)
    if not w or not w.get("active"): return
    owner_mention = await get_owner_mention(context, chat_id)
    try:
        await context.bot.send_message(
            chat_id,
            f"⏰ مرت يومان على القرعة.\n📢 تنبيه لمالك الجروب: {owner_mention}\n"
            f"❓ هل انتهت المواجهة؟\n(اكتب: انهاء مواجهه)",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ خطأ في task_remind_1: {e}")
    asyncio.create_task(task_remind_2(chat_id, context, 24 * 3600))

async def task_remind_2(chat_id: int, context, delay: float):
    if delay > 0: await asyncio.sleep(delay)
    w = wars.get(chat_id)
    if not w or not w.get("active"): return
    owner_mention = await get_owner_mention(context, chat_id)
    try:
        await context.bot.send_message(
            chat_id,
            f"⚠️ {owner_mention} مرت 3 أيام ولم تنتهِ المواجهة.\nاكتب: انهاء مواجهه لإنهائها.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ خطأ في task_remind_2: {e}")

async def task_auto_send_after_6h(chat_id: int, context, delay: float = TIME_AUTO_END):
    if delay > 0: await asyncio.sleep(delay)
    await send_war_link(context, chat_id, "✅ أُرسل تلقائياً بعد 6 ساعات من انتهاء المواجهة.")

# ─────────────────────────────────────────────
#  حساب التاكات عن طريق جلسة Telethon
# ─────────────────────────────────────────────
def _extract_mentions(text: str) -> set:
    if not text:
        return set()
    return set(m.lower() for m in re.findall(r'@\w+', text))

def _msg_link(chat, msg_id) -> str:
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    cid = getattr(chat, "id", None)
    if cid:
        return f"https://t.me/c/{cid}/{msg_id}"
    return ""

def _compute_tag_counts(mentions: list) -> dict:
    result = {}
    last_counted = {}
    for m in sorted(mentions, key=lambda x: x["ts"]):
        if m.get("voided"):
            continue
        key = (m["from"], m["to"])
        last = last_counted.get(key)
        if last is not None and (m["ts"] - last) < 1800:
            continue
        last_counted[key] = m["ts"]
        entry = result.setdefault(key, {"count": 0, "links": []})
        entry["count"] += 1
        if m.get("link"):
            entry["links"].append(m["link"])
    return result

def _collect_voided_tags(mentions: list) -> dict:
    result = {}
    for m in sorted(mentions, key=lambda x: x["ts"]):
        if not m.get("voided"):
            continue
        key = (m["from"], m["to"])
        result.setdefault(key, []).append({
            "link": m.get("link") or "",
            "reason": m.get("void_reason") or "غير معروف",
        })
    return result

async def _join_group_via_link(client, invite_link: str):
    invite_link = (invite_link or "").strip()
    if not invite_link:
        raise RuntimeError("مقدرش أجيب رابط دعوة من البوت (لازم يكون أدمن بصلاحية دعوة أعضاء).")
    try:
        if "joinchat/" in invite_link:
            invite_hash = invite_link.split("joinchat/")[-1]
            await client(ImportChatInviteRequest(invite_hash))
        elif "/+" in invite_link:
            invite_hash = invite_link.split("/+")[-1]
            await client(ImportChatInviteRequest(invite_hash))
        else:
            username = invite_link.rstrip("/").split("/")[-1]
            await client(JoinChannelRequest(username))
    except UserAlreadyParticipantError:
        pass
    except FloodWaitError as e:
        raise RuntimeError(f"تليجرام طلب الانتظار {e.seconds} ثانية قبل محاولة الدخول تاني.")
    except (InviteHashExpiredError, InviteHashInvalidError) as e:
        raise RuntimeError(f"رابط الدعوة غير صالح/منتهي: {e}")


async def _count_tags_for_range(client, chat, team1: list, team2: list, start_ts: float, end_ts: float) -> dict:
    all_tracked = set(team1) | set(team2)

    raw_mentions = []
    msg_index = {}
    scanned = 0
    skipped_no_username = 0
    skipped_not_tracked = 0
    tracked_hits = 0

    async for message in client.iter_messages(chat):
        if not message.date:
            continue
        msg_ts = message.date.timestamp()
        if msg_ts > end_ts:
            continue
        if msg_ts < start_ts:
            break

        scanned += 1
        try:
            sender = await message.get_sender()
        except Exception as e:
            print(f"⚠️ مقدرش أجيب مرسل رسالة {message.id}: {e}")
            continue
        sender_username = getattr(sender, "username", None)
        if not sender_username:
            skipped_no_username += 1
            continue
        sender_l = "@" + sender_username.lower()
        if sender_l not in all_tracked:
            skipped_not_tracked += 1
            continue
        tracked_hits += 1
        preview = (message.message or "")[:80].replace("\n", " ")
        print(f"👤 [متابَع] {sender_l} في {message.date} : {preview!r}")

        mention_indices = []
        mentioned = _extract_mentions(message.message or "")
        off_hours = _is_off_hours(message.date)
        for target in mentioned:
            if target == sender_l or target not in all_tracked:
                continue
            same_team = (sender_l in team1 and target in team1) or \
                        (sender_l in team2 and target in team2)
            if same_team:
                continue
            raw_mentions.append({
                "from": sender_l, "to": target, "ts": msg_ts,
                "msg_id": message.id,
                "voided": off_hours,
                "void_reason": "⏰ وقت غير رسمي (من 2 لحد 9 الصبح)" if off_hours else None,
                "link": _msg_link(chat, message.id),
            })
            mention_indices.append(len(raw_mentions) - 1)

        msg_index[message.id] = {
            "sender": sender_l, "ts": msg_ts,
            "reply_to": message.reply_to_msg_id,
            "mention_indices": mention_indices,
        }

    print(
        f"🔎 فحصت {scanned} رسالة | من غير يوزرنيم: {skipped_no_username} | "
        f"مش متابَع: {skipped_not_tracked} | من لاعب متابَع: {tracked_hits} | "
        f"تاكات خام قبل قانون الإلغاء: {len(raw_mentions)}"
    )

    for mid, info in msg_index.items():
        reply_to_id = info["reply_to"]
        if not reply_to_id or reply_to_id not in msg_index:
            continue
        original = msg_index[reply_to_id]
        for idx in original["mention_indices"]:
            m = raw_mentions[idx]
            if m["voided"]:
                continue
            if m["to"] == info["sender"] and (info["ts"] - m["ts"]) <= 600:
                m["voided"] = True
                m["void_reason"] = "↩️ اتلغى بالرد خلال 10 دقايق"

    counts = _compute_tag_counts(raw_mentions)
    voided = _collect_voided_tags(raw_mentions)
    team1_total = sum(e["count"] for (f, t), e in counts.items() if f in team1 and t in team2)
    team2_total = sum(e["count"] for (f, t), e in counts.items() if f in team2 and t in team1)
    return {"counts": counts, "team1_total": team1_total, "team2_total": team2_total, "voided": voided}

async def build_tag_report_text(context, team1: list, team2: list, result: dict, label: str) -> str:
    counts = result["counts"]
    voided = result.get("voided", {})
    detail_lines = []
    for (f, t), entry in counts.items():
        detail_lines.append(f"{f} ⬅️ {t} : {entry['count']}")
        for i, link in enumerate(entry["links"], 1):
            if link:
                detail_lines.append(f"      {i}. {link}")
    bot_username = context.bot.username or ""

    voided_lines = []
    for (f, t), items in voided.items():
        voided_lines.append(f"{f} ⬅️ {t}:")
        for i, it in enumerate(items, 1):
            voided_lines.append(f"      {i}. {it['link']} — سبب: {it['reason']}")
    voided_block = "\n".join(voided_lines) if voided_lines else "لا يوجد تاكات ملغاة خلال الفترة دي."

    return (
        f"📊 تقرير التاكات ({label})\n"
        f"━━━━━━━━━━━━━━\n"
        + ("\n".join(detail_lines) if detail_lines else "لا يوجد تاكات مسجلة خلال الفترة دي.") +
        f"\n━━━━━━━━━━━━━━\n"
        f"👥 {' '.join(team1)} → {' '.join(team2)} : {result['team1_total']}\n"
        f"👥 {' '.join(team2)} → {' '.join(team1)} : {result['team2_total']}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🚫 التاكات الملغاة:\n{voided_block}\n"
        + (f"@{bot_username}" if bot_username else "")
    )

async def run_tag_count_now(chat_id: int, context, team1: list, team2: list, base_ts: float):
    if TelegramClient is None:
        try:
            await context.bot.send_message(chat_id, "❌ مكتبة Telethon مش متثبتة على السيرفر.")
        except:
            pass
        return

    if not TELETHON_SESSION_STRING:
        try:
            await context.bot.send_message(chat_id, "❌ TELETHON_SESSION_STRING مش متحطوط في متغيرات البيئة.")
        except:
            pass
        return

    client = TelegramClient(StringSession(TELETHON_SESSION_STRING), TELETHON_API_ID, TELETHON_API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        try:
            await context.bot.send_message(chat_id, "❌ الـ session string مش صالح/منتهي. لازم تولّد واحد جديد.")
        except:
            pass
        await client.disconnect()
        return
    chat = None
    try:
        w = wars.get(chat_id)
        if w is None:
            raise RuntimeError("المواجهة مش موجودة في البيانات (اتشالت أو اتغيرت).")
        try:
            invite_link = await get_or_create_war_link(context, chat_id, w)
        except Exception as e:
            raise RuntimeError(f"مقدرش أجيب رابط دعوة من البوت: {e}")
        if not invite_link:
            raise RuntimeError("مقدرش أجيب رابط دعوة من البوت (لازم يكون أدمن بصلاحية دعوة أعضاء).")

        await _join_group_via_link(client, invite_link)
        chat = await client.get_entity(chat_id)

        for days in (2, 3):
            end_ts = base_ts + days * 24 * 3600
            label = f"من بداية المواجهة لحد يوم {days}"
            try:
                result = await _count_tags_for_range(client, chat, team1, team2, base_ts, end_ts)
            except Exception as e:
                print(f"❌ خطأ في حساب التاكات (يوم {days}): {e}")
                try:
                    await context.bot.send_message(chat_id, f"❌ حصل خطأ أثناء حساب التاكات (يوم {days}): {e}")
                except:
                    pass
                continue
            text = await build_tag_report_text(context, team1, team2, result, label)
            try:
                await context.bot.send_message(chat_id, text, disable_web_page_preview=True)
            except Exception as e:
                print(f"❌ خطأ في إرسال تقرير التاكات: {e}")

    except Exception as e:
        print(f"❌ خطأ عام في حساب التاكات: {e}")
        try:
            await context.bot.send_message(chat_id, f"❌ حصل خطأ أثناء دخول الجلسة للجروب: {e}")
        except:
            pass

    finally:
        if chat is not None:
            try:
                await client(LeaveChannelRequest(chat))
                print("👋 الجلسة خرجت من الجروب.")
            except Exception as e:
                print(f"⚠️ مقدرش يخرج من الجروب: {e}")
        await client.disconnect()

# ─────────────────────────────────────────────
#  استعادة المهام بعد إعادة التشغيل
# ─────────────────────────────────────────────
async def restore_tasks(application):
    now = now_ts()
    for chat_id, w in wars.items():
        if w.get("active") and w.get("draw_ts") and w.get("mid"):
            draw_ts = float(w["draw_ts"])
            elapsed = now - draw_ts
            if not w.get("reminded_1", False):
                asyncio.create_task(task_remind_1(chat_id, application, max(0.0, TIME_REMIND_1 - elapsed)))
            elif not w.get("reminded_2", False):
                asyncio.create_task(task_remind_2(chat_id, application, max(0.0, TIME_REMIND_2 - elapsed)))
        elif not w.get("active") and not w.get("link_sent") and w.get("end_ts"):
            end_ts  = float(w["end_ts"])
            elapsed = now - end_ts
            asyncio.create_task(task_auto_send_after_6h(chat_id, application, max(0.0, TIME_AUTO_END - elapsed)))

        if w.get("active") and not w.get("mid") and w.get("roster_deadline_ts") and not w.get("roster_deadline_done"):
            remaining = float(w["roster_deadline_ts"]) - now
            asyncio.create_task(task_check_roster_deadline(chat_id, application, max(0.0, remaining)))

    print("✅ استعادة المهام اكتملت")

# ─────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

# ─────────────────────────────────────────────
#  /setimage
# ─────────────────────────────────────────────
async def _process_setimage(update: Update, stage_key: str):
    if not stage_key or not stage_key.strip():
        await update.message.reply_text(
            "❌ اكتب اسم الدور.\n\n"
            "أمثلة:\n"
            "• /setimage دور16\n"
            "• /setimage ربع\n"
            "• /setimage نصف\n"
            "• /setimage نهائي\n"
            "• /setimage دوري\n\n"
            "أو ابعت الصورة وفي الـ caption اكتب الأمر."
        )
        return

    stage = get_stage_from_text(stage_key)
    if not stage:
        await update.message.reply_text(
            f"❌ دور غير معروف: «{stage_key}»\n\n"
            "الأدوار المتاحة:\n"
            "دور16 | ربع | نصف | نهائي | دوري"
        )
        return

    photo = None
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]

    if not photo:
        await update.message.reply_text(
            "❌ ما لقيت صورة!\n\n"
            "الطرق الصحيحة:\n"
            "1️⃣ ابعت الصورة وفي الـ caption اكتب:\n"
            "   /setimage ربع\n\n"
            "2️⃣ ابعت الصورة أولاً، ثم reply عليها واكتب:\n"
            "   /setimage ربع"
        )
        return

    stage_images[stage] = photo.file_id
    save_images()

    status = "\n".join(f"{'✅' if s in stage_images else '❌'} {s}" for s in STAGES)
    await update.message.reply_text(
        f"✅ تم حفظ صورة [{stage}] بنجاح!\n\n"
        f"📸 الصور المحفوظة:\n{status}"
    )


async def cmd_setimage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        stage_key = " ".join(context.args).strip()
        await _process_setimage(update, stage_key)
        return

    caption = ""
    if update.message and update.message.caption:
        caption = update.message.caption.strip()
    elif update.message and update.message.text:
        caption = update.message.text.strip()

    match = re.search(r'/setimage\s+(.*)', caption, re.IGNORECASE)
    if match:
        stage_key = match.group(1).strip()
        await _process_setimage(update, stage_key)
        return

    await _process_setimage(update, "")


async def _moderate_media_before_draw(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str, mime_type: str) -> bool:
    """
    فحص محتوى مرئي (صورة/فيديو/ستيكر) طول فترة المواجهة بالكامل: من لحظة
    "Clan VS Clan" وحتى انتهاء المواجهة فعليًا (فوز/فوز إداري)، مش بس لحد
    القرعة. يرجع True لو تم رصد مخالفة وتقييد الشخص.
    """
    cid  = update.effective_chat.id
    user = update.effective_user
    if not user:
        return False
    w = wars.get(cid)
    if not w:
        w = await try_recover_war(cid, context)
    # مفيش w أصلاً، أو المواجهة خلصت فعليًا (end_ts اتحط)، أو فيه قرار معلّق حاليًا
    if not w or w.get("end_ts") or w.get("pending_moderation"):
        return False

    try:
        tg_file = await context.bot.get_file(file_id)
        media_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        print(f"❌ خطأ في تحميل الميديا للفحص: {e}")
        return False

    if not await is_unsafe_media(media_bytes, mime_type):
        return False

    u_tag = f"@{user.username}" if user.username else f"ID:{user.id}"
    await _flag_and_restrict(update, context, cid, w, user, u_tag, "إرسال محتوى مخالف (إباحي/دموي/سلاح)")
    return True

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    if await _silent_kick_if_banned(context, update.effective_chat, update.effective_user, update.message.message_id):
        return
    await lock_group_if_needed(context.bot, update.effective_chat)
    await unlock_group_if_locked(context.bot, update.effective_chat)

    largest = update.message.photo[-1]
    if await _moderate_media_before_draw(update, context, largest.file_id, "image/jpeg"):
        return

    caption = (update.message.caption or "").strip()
    if re.match(r'^/setimage', caption, re.IGNORECASE):
        await cmd_setimage(update, context)

async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.sticker:
        return
    if await _silent_kick_if_banned(context, update.effective_chat, update.effective_user, update.message.message_id):
        return
    await lock_group_if_needed(context.bot, update.effective_chat)
    await unlock_group_if_locked(context.bot, update.effective_chat)
    sticker = update.message.sticker
    # الستيكرز المتحركة (.tgs) والفيديو (.webm) بصيغ خاصة بتليجرام، فبنستخدم
    # الصورة المصغّرة (thumbnail) بتاعتها للفحص لأنها JPEG عادي وممثّلة للمحتوى.
    thumb = sticker.thumbnail
    if thumb:
        await _moderate_media_before_draw(update, context, thumb.file_id, "image/jpeg")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not (update.message.video or update.message.animation):
        return
    if await _silent_kick_if_banned(context, update.effective_chat, update.effective_user, update.message.message_id):
        return
    await lock_group_if_needed(context.bot, update.effective_chat)
    await unlock_group_if_locked(context.bot, update.effective_chat)
    media = update.message.video or update.message.animation
    thumb = media.thumbnail
    if thumb:
        # بنفحص الصورة المصغّرة (thumbnail) للفيديو بدل الفيديو كامل — أسرع
        # وأخف بكتير، وكافية لرصد المحتوى الصريح في الغالبية العظمى من الحالات.
        await _moderate_media_before_draw(update, context, thumb.file_id, "image/jpeg")

# ─────────────────────────────────────────────
#  /images
# ─────────────────────────────────────────────
async def cmd_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(stage_images)
    status = "\n".join(
        f"{'✅' if s in stage_images else '❌'} {s}"
        for s in STAGES
    )
    await update.message.reply_text(
        f"📸 حالة صور الأدوار ({total}/{len(STAGES)}):\n\n{status}\n\n"
        f"{'✅ جميع الصور محفوظة!' if total == len(STAGES) else '⚠️ بعض الصور ناقصة — استخدم /setimage لإضافتها'}"
    )

# ─────────────────────────────────────────────
#  إنهاء إعداد المواجهة (بعد اختيار الدور / الساعات)
# ─────────────────────────────────────────────
async def _finalize_war(update, context, cid, c1, c2, stage, hours, referee, created_ts):
    wars[cid] = {
        "c1": {"n": c1, "s": 0, "p": [], "stats": [], "leader": None},
        "c2": {"n": c2, "s": 0, "p": [], "stats": [], "leader": None},
        "active": True, "mid": None, "matches": [], "stage": stage,
        "referee": referee, "created_ts": created_ts,
        "invite_link": None,
        "link_sent": False, "waiting_objection": False, "waiting_stage": False,
        "waiting_roster_hours": False,
        "roster_deadline_hours": hours,
        "roster_deadline_ts": now_ts() + hours * 3600,
        "roster_deadline_done": False,
        "draw_ts": None, "end_ts": None, "reminded_1": False, "reminded_2": False,
    }
    save()

    file_id = stage_images.get(stage)
    if file_id:
        try:
            tg_file = await context.bot.get_file(file_id)
            img_bytes = await tg_file.download_as_bytearray()
            await context.bot.set_chat_photo(cid, photo=bytes(img_bytes))
        except Exception as e:
            print(f"❌ خطأ في تغيير صورة الجروب: {e}")

    await update.message.reply_text(
        f"⚔️ بدأت الحرب!\n🔥 {c1}  VS  {c2}\n🏆 الدور: {stage}\n"
        f"⏳ مهلة إرسال القوائم: {hours} ساعة"
    )
    try:
        await context.bot.set_chat_title(cid, f"⚔️ {c1} 0 - 0 {c2} ⚔️")
    except:
        pass

    try:
        bold_caption = f"<b>{WAR_START_CLICHE_TEXT}</b>"
        if os.path.exists(WAR_START_CLICHE_IMAGE):
            with open(WAR_START_CLICHE_IMAGE, "rb") as img_f:
                cliche_msg = await context.bot.send_photo(
                    cid, photo=img_f, caption=bold_caption, parse_mode="HTML"
                )
        else:
            cliche_msg = await context.bot.send_message(
                cid, bold_caption, parse_mode="HTML"
            )
            print(f"⚠️ صورة الكليشة ({WAR_START_CLICHE_IMAGE}) مش موجودة جنب ملف البوت.")
        try:
            await context.bot.pin_chat_message(cid, cliche_msg.message_id)
        except Exception as e:
            print(f"❌ خطأ في تثبيت كليشة القوائم: {e}")
    except Exception as e:
        print(f"❌ خطأ في إرسال كليشة القوائم: {e}")

    asyncio.create_task(task_check_roster_deadline(cid, context, hours * 3600))

# ─────────────────────────────────────────────
#  قائمة المواجهات المفتوحة (خاص المسؤولين)
# ─────────────────────────────────────────────
async def handle_private_war_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    if not user or not user.username or user.username.lower() not in RESPONSIBLE_USERNAMES:
        return
    text = update.message.text.strip()

    if text in GROUPS_LIST_TRIGGERS:
        await send_groups_report(update, context)
        return

    if text not in {"مواجهة", "مواجهه"}:
        return

    open_wars = {
        cid: w for cid, w in wars.items()
        if w.get("active") or w.get("waiting_stage") or w.get("waiting_roster_hours") or w.get("mid")
    }
    if not open_wars:
        await update.message.reply_text("📭 لا يوجد أي مواجهات مفتوحة حالياً.")
        return

    now = now_ts()
    blocks = []
    skipped = 0
    for cid, w in open_wars.items():
        try:
            await context.bot.get_chat(cid)
        except Exception:
            skipped += 1
            continue

        referee = w.get("referee", "—")
        try:
            owner_mention = await get_owner_mention(context, cid)
        except:
            owner_mention = "—"
        start_ts = w.get("draw_ts") or w.get("created_ts")
        if start_ts:
            elapsed_h = (now - float(start_ts)) / 3600
            elapsed_txt = f"{elapsed_h:.1f} ساعة"
        else:
            elapsed_txt = "—"
        try:
            link = await get_or_create_war_link(context, cid, w) or "—"
        except:
            link = "—"
        c1n = w.get("c1", {}).get("n") or w.get("pending_c1", "?")
        c2n = w.get("c2", {}).get("n") or w.get("pending_c2", "?")
        blocks.append(
            f"⚔️ {c1n} VS {c2n}\n"
            f"👨‍⚖️ الحكم: {referee}\n"
            f"👑 مالك الجروب: {owner_mention}\n"
            f"⏱️ متفاعلة من: {elapsed_txt}\n"
            f"🔗 رابط المواجهة: {link}\n"
            f"🆔 {cid}"
        )

    if not blocks:
        msg = "📭 لا يوجد أي مواجهات مفتوحة حالياً (والبوت متاح فيها)."
        if skipped:
            msg += f"\n⚠️ اتجاهلت {skipped} مواجهة قديمة، البوت مش عضو في الجروب بتاعها دلوقتي."
        await update.message.reply_text(msg)
        return

    footer = f"\n\n⚠️ (اتجاهلت {skipped} مواجهة قديمة، البوت مش عضو في جروبها)" if skipped else ""
    await update.message.reply_text(
        "📋 المواجهات المفتوحة حالياً:\n\n" + ("\n" + "─" * 20 + "\n").join(blocks) + footer,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# ─────────────────────────────────────────────
#  استرجاع مواجهة ضايعة من الرسالة المثبتة (بدون تيلثون)
# ─────────────────────────────────────────────
_recovery_checked: set = set()

_EMOJI_TO_DIGIT = {'0️⃣': '0', '1️⃣': '1', '2️⃣': '2', '3️⃣': '3', '4️⃣': '4',
                    '5️⃣': '5', '6️⃣': '6', '7️⃣': '7', '8️⃣': '8', '9️⃣': '9'}

def _de_emoji(s: str) -> str:
    for e, d in _EMOJI_TO_DIGIT.items():
        s = s.replace(e, d)
    return s

async def try_recover_war(cid: int, context):
    """يحاول يعيد بناء حالة المواجهة من الرسالة المثبتة في الجروب. مرة واحدة لكل جروب."""
    if cid in wars:
        return wars[cid]
    if cid in _recovery_checked:
        return None
    _recovery_checked.add(cid)

    try:
        chat = await context.bot.get_chat(cid)
        pinned = chat.pinned_message
    except Exception:
        return None
    if not pinned or not pinned.text:
        return None

    text = pinned.text
    m = re.search(r'⚔️\s*(\S+)\s+(\d+)\s*-\s*(\d+)\s+(\S+)', text)
    if m:
        c1n, c1s, c2s, c2n = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    else:
        m2 = re.search(r'A-\s*\[\s*(\S+)\s*\]\s*VS\s*B-\s*\[\s*(\S+)\s*\]', text)
        if not m2:
            return None
        c1n, c2n, c1s, c2s = m2.group(1), m2.group(2), 0, 0

    matches = []
    for line in text.splitlines():
        line = _de_emoji(line)
        mm = re.match(r'^\s*\d+\s*\|\s*(\S+)\s+(\d)\s*\|🆚\|\s*(\d)\s+(\S+)', line)
        if mm:
            p1, s1, s2, p2 = mm.group(1), int(mm.group(2)), int(mm.group(3)), mm.group(4)
            matches.append({"p1": p1, "p2": p2, "s1": s1, "s2": s2})
    if not matches:
        return None

    stats1, stats2 = [], []
    for mch in matches:
        if mch["s1"] == mch["s2"]:
            continue
        if mch["s1"] > mch["s2"]:
            stats1.append({"name": mch["p1"], "goals": mch["s1"], "rec": mch["s2"], "is_free": False})
        else:
            stats2.append({"name": mch["p2"], "goals": mch["s2"], "rec": mch["s1"], "is_free": False})

    w = {
        "c1": {"n": c1n, "s": c1s, "p": [mch["p1"] for mch in matches], "leader": None, "stats": stats1},
        "c2": {"n": c2n, "s": c2s, "p": [mch["p2"] for mch in matches], "leader": None, "stats": stats2},
        "matches": matches,
        "mid": pinned.message_id,
        "active": True,
        "draw_ts": now_ts(),
        "reminded_1": True,
        "reminded_2": True,
        "link_sent": False,
        "referee": None,
        "recovered": True,
    }
    wars[cid] = w
    save()
    print(f"♻️ اترجعت مواجهة {c1n} vs {c2n} في الجروب {cid} من الرسالة المثبتة")
    return w

# ─────────────────────────────────────────────
#  المعالج الرئيسي (داخل الجروبات)
# ─────────────────────────────────────────────
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    cid    = update.effective_chat.id
    msg    = update.message.text
    msg_up = msg.upper().strip()
    msg_cl = clean(msg)
    user   = update.effective_user
    u_tag  = f"@{user.username}" if user.username else f"ID:{user.id}"

    if await _silent_kick_if_banned(context, update.effective_chat, user, update.message.message_id):
        return

    remember_chat(update.effective_chat)
    await lock_group_if_needed(context.bot, update.effective_chat)
    await unlock_group_if_locked(context.bot, update.effective_chat)

    try:
        cm         = await context.bot.get_chat_member(cid, user.id)
        is_creator = (cm.status == 'creator')
        is_ref     = is_creator
    except:
        is_creator = False
        is_ref     = False

    w = wars.get(cid)
    if not w:
        w = await try_recover_war(cid, context)

    if await handle_warning_system(update, context, cid, is_creator):
        return

    # ── رد مالك الجروب على شخص مقيّد بسبب مخالفة (سب / محتوى غير لائق) ──
    # لازم يكون رد (reply) على رسالة التنبيه، ولازم يكون مالك الجروب هو اللي بيرد.
    if (
        is_creator and w and w.get("pending_moderation")
        and update.message.reply_to_message
        and update.message.reply_to_message.message_id == w["pending_moderation"].get("alert_mid")
    ):
        target_id  = w["pending_moderation"]["target_id"]
        target_tag = w["pending_moderation"]["target_tag"]
        if any(k in msg_cl for k in ("اطرد", "طرد", "افصله", "شيله")):
            try:
                await context.bot.ban_chat_member(cid, target_id)
                await update.message.reply_text(f"🚫 تم طرد {target_tag} بقرار مالك الجروب.")
            except Exception as e:
                await update.message.reply_text(f"❌ فشل الطرد: {e}")
            w["pending_moderation"] = None
            save()
            return
        if any(k in msg_cl for k in ("الغاء تقييد", "الغاء التقييد", "سيبه", "فك تقييد", "فك التقييد")):
            ok = await unrestrict_user(context, cid, target_id)
            if ok:
                await update.message.reply_text(f"✅ تم رفع التقييد عن {target_tag}.")
            else:
                await update.message.reply_text(f"❌ فشل رفع التقييد عن {target_tag}.")
            w["pending_moderation"] = None
            save()
            return
        await update.message.reply_text("❓ اكتب: اطرد / الغاء تقييد (كـ رد على رسالة التنبيه).")
        return

    if msg_cl.strip() in LINK_TRIGGERS:
        await cmd_group_link(update, context)
        return

    bot_uname = (context.bot.username or "").lower()
    mentions_bot = bool(bot_uname) and f"@{bot_uname}" in msg.lower()
    if w and mentions_bot and any(trig in msg_cl for trig in TAG_COUNT_TRIGGERS):
        if not is_tag_admin(user, is_creator):
            await update.message.reply_text("🚫 حساب التاكات لمالك الجروب أو المسؤولين فقط.")
            return
        w["waiting_tag_setup"] = True
        save()
        await update.message.reply_text(
            "📝 ابعت اليوزرات:\n"
            "@user1 ضد @user2\n\n"
            "أو فريق مقابل فريق:\n"
            "@user1 @user2 ضد @user3 @user4"
        )
        return

    if w and w.get("waiting_tag_setup"):
        if not is_tag_admin(user, is_creator):
            return
        parts = re.split(r'\s+ضد\s+|\s+vs\s+', msg, flags=re.IGNORECASE)
        if len(parts) != 2:
            await update.message.reply_text("❌ الصيغة غلط. اكتب: @user1 ضد @user2")
            return
        team1 = [u.lower() for u in re.findall(r'@\w+', parts[0])]
        team2 = [u.lower() for u in re.findall(r'@\w+', parts[1])]
        if not team1 or not team2:
            await update.message.reply_text("❌ محتاج يوزر واحد على الأقل لكل طرف.")
            return
        base_ts = w.get("draw_ts") or w.get("created_ts") or now_ts()
        w["waiting_tag_setup"] = False
        w["tag_tracking"] = {"team1": team1, "team2": team2, "base_ts": base_ts}
        save()
        await update.message.reply_text(
            f"⏳ جاري حساب التاكات بين:\n{' '.join(team1)}  ضد  {' '.join(team2)}\n"
            f"هيوصلك تقريرين (لحد يوم 2، ولحد يوم 3) عشان تختار بينهم..."
        )
        asyncio.create_task(run_tag_count_now(cid, context, team1, team2, base_ts))
        return

    if w and w.get("waiting_stage"):
        if not is_creator: return
        stage = detect_stage(msg)
        if not stage:
            await update.message.reply_text("❌ لم أفهم. اختر بالرقم أو الاسم:\n\n" + STAGE_QUESTION)
            return
        c1, c2 = w["pending_c1"], w["pending_c2"]
        referee = w.get("referee", u_tag)
        created_ts = w.get("created_ts", now_ts())

        if stage == "دوري":
            wars[cid] = {
                "pending_c1": c1, "pending_c2": c2, "pending_stage": stage,
                "referee": referee, "created_ts": created_ts,
                "waiting_stage": False, "waiting_roster_hours": True,
                "active": False, "link_sent": False,
            }
            save()
            await update.message.reply_text("⏳ اكتب عدد الساعات المسموحة لإرسال القوائم (رقم فقط):")
            return

        hours = ROSTER_HOURS_16_QUARTER if stage in ("دور الـ 16", "ربع النهائي") else ROSTER_HOURS_SEMI_FINAL
        await _finalize_war(update, context, cid, c1, c2, stage, hours, referee, created_ts)
        return

    if w and w.get("waiting_roster_hours"):
        if not is_creator: return
        if not msg.strip().isdigit():
            await update.message.reply_text("❌ اكتب رقم صحيح للساعات، مثال: 24")
            return
        hours = int(msg.strip())
        c1, c2, stage = w["pending_c1"], w["pending_c2"], w["pending_stage"]
        referee = w.get("referee", u_tag)
        created_ts = w.get("created_ts", now_ts())
        await _finalize_war(update, context, cid, c1, c2, stage, hours, referee, created_ts)
        return

    war_match = re.match(
        r'^([A-Za-z0-9]{2,4})\s+VS\s+([A-Za-z0-9]{2,4})$',
        msg.strip(), re.IGNORECASE
    )
    if war_match and "+1" not in msg_up:
        if not is_creator:
            await update.message.reply_text("🚫 هذا الأمر لمالك الجروب (Owner) فقط.")
            return
        c1 = war_match.group(1).upper()
        c2 = war_match.group(2).upper()
        wars[cid] = {
            "pending_c1": c1, "pending_c2": c2, "waiting_stage": True,
            "active": False, "link_sent": False,
            "referee": u_tag, "created_ts": now_ts(),
        }
        save()
        await update.message.reply_text(f"⚔️ {c1}  VS  {c2}\n\n" + STAGE_QUESTION)

        # فحص فوري للقائمة السوداء وطرد أي حد موجود منها في الجروب ده
        try:
            banned_now = await ban_blacklisted_members(context, cid)
            if banned_now:
                await update.message.reply_text(
                    "🚫 تم طرد الأعضاء التالية أسماؤهم فورًا (موجودين في القائمة السوداء):\n"
                    + "\n".join(banned_now)
                )
        except Exception as e:
            print(f"❌ خطأ في فحص/طرد القائمة السوداء للجروب {cid}: {e}")
        return

    if not w or w.get("waiting_stage"):
        if mentions_bot:
            question = re.sub(re.escape(f"@{bot_uname}"), "", msg, flags=re.IGNORECASE).strip()
            if question:
                await update.message.reply_text("📖 لحظات، بدور في الدستور...")
                answer = await ask_ai_general(question, u_tag, w)
                await update.message.reply_text(answer)
        return

    if "انهاء مواجهه" in msg_cl or "انهاء مواجهة" in msg_cl:
        if not is_creator:
            await update.message.reply_text("🚫 هذا الأمر لمالك الجروب (Owner) فقط.")
            return
        if w.get("link_sent"):
            await update.message.reply_text("⚠️ تم إرسال الرابط مسبقاً.")
            return
        await send_war_link(context, cid, "📌 أنهى المالك المواجهة يدوياً.")
        await update.message.reply_text("✅ تم إرسال رابط المواجهة للجهة المعنية.")
        return

    if "عندي اعتراض" in msg_cl or msg_cl.strip() == "اعتراض":
        is_leader = u_tag in [w["c1"].get("leader"), w["c2"].get("leader")]
        if not (is_ref or is_leader):
            await update.message.reply_text("❌ الاعتراض متاح للمالك والقادة فقط.")
            return
        w["waiting_objection"] = True
        w["objection_by"]      = u_tag
        save()
        await update.message.reply_text("📝 اكتب نص اعتراضك كاملاً.\nأو أرسل: الغاء للتراجع.")
        return

    if w.get("waiting_objection"):
        if msg_cl.strip() == "الغاء":
            w["waiting_objection"] = False
            save()
            await update.message.reply_text("✅ تم إلغاء الاعتراض.")
            return
        objector = w.get("objection_by", u_tag)
        w["waiting_objection"] = False
        save()

        if mentions_bot:
            await update.message.reply_text("⚖️ جاري دراسة الاعتراض طبقًا للدستور، لحظات...")
            verdict = await ask_ai_judge(msg, objector, w)
            await update.message.reply_text(
                f"⚖️ حكم آلي في الاعتراض\n━━━━━━━━━━━━━━\n"
                f"👤 مقدّم الاعتراض: {objector}\n"
                f"📊 النتيجة وقت الاعتراض: {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
                f"📝 نص الاعتراض:\n{msg}\n"
                f"━━━━━━━━━━━━━━\n{verdict}"
            )
        else:
            await update.message.reply_text(
                f"⚖️ اعتراض رسمي مسجّل\n━━━━━━━━━━━━━━\n"
                f"👤 مقدّم الاعتراض: {objector}\n"
                f"📊 النتيجة الحالية: {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
                f"📝 نص الاعتراض:\n{msg}\n"
                f"━━━━━━━━━━━━━━\n⏳ سيتم البت فيه من المالك.\n"
                f"💡 (اعمل منشن للبوت في نص الاعتراض عشان يحكم آليًا)"
            )
        return

    if "قائم" in msg_cl and update.message.reply_to_message:
        target_k = "c1" if w["c1"]["n"].upper() in msg_up else "c2" if w["c2"]["n"].upper() in msg_up else None
        if not target_k:
            await update.message.reply_text("❌ اكتب اسم الكلان بشكل صحيح مع كلمة قائمة.")
            return
        players = [p.strip() for p in update.message.reply_to_message.text.split('\n') if p.strip().startswith('@')]
        if not players:
            await update.message.reply_text("❌ لا يوجد لاعبون (يجب أن تبدأ بـ @).")
            return
        w[target_k]["leader"] = u_tag
        w[target_k]["p"]      = players
        save()
        await update.message.reply_text(f"✅ قائمة {w[target_k]['n']} مقبولة ({len(players)} لاعبين) بواسطة {u_tag}.")
        if w["c1"]["p"] and w["c2"]["p"]:
            await _make_draw(update, context, cid, w)
        return

    if ("+1" in msg_up or "+ 1" in msg_up) and w.get("active"):
        win_k = "c1" if w["c1"]["n"].upper() in msg_up else "c2" if w["c2"]["n"].upper() in msg_up else None
        if not win_k: return
        players = re.findall(r'@\w+', msg)
        scores  = re.findall(r'\b(\d+)\b', msg)
        if len(players) >= 2 and len(scores) >= 2:
            asst = context.bot_data.get(f"asst_{cid}_{w[win_k]['n'].upper()}")
            if not (is_ref or u_tag == w[win_k]["leader"] or u_tag == asst):
                await update.message.reply_text("❌ التسجيل للمالك والقادة/المساعدين فقط.")
                return
            u1, u2   = players[0], players[1]
            sc1, sc2 = int(scores[0]), int(scores[1])
            p_win    = u1 if sc1 > sc2 else u2
            w[win_k]["s"] += 1
            w[win_k]["stats"].append({"name": p_win, "goals": max(sc1,sc2), "rec": min(sc1,sc2), "is_free": False})
            for m in w["matches"]:
                p1u, p2u = m["p1"].upper(), m["p2"].upper()
                if u1.upper() in (p1u, p2u) and u2.upper() in (p1u, p2u):
                    m["s1"], m["s2"] = (sc1, sc2) if u1.upper() == p1u else (sc2, sc1)
            save()
            await update.message.reply_text(f"✅ نقطة لـ {w[win_k]['n']}  |  {u1} {sc1} - {sc2} {u2}")
            await _update_table(context, cid, w)
            if is_creator:
                try:
                    await context.bot.set_chat_title(cid, f"⚔️ {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']} ⚔️")
                except:
                    pass
            for pl in players:
                try:
                    mem = await context.bot.get_chat_member(cid, pl)
                    await context.bot.ban_chat_member(cid, mem.user.id)
                    await context.bot.unban_chat_member(cid, mem.user.id)
                except:
                    pass
        else:
            if not is_ref:
                await update.message.reply_text("❌ النقطة الفري للمالك فقط.")
                return
            w[win_k]["s"] += 1
            w[win_k]["stats"].append({"name": "Free", "goals": 0, "rec": 0, "is_free": True})
            save()
            await update.message.reply_text(f"⚖️ نقطة فري لكلان {w[win_k]['n']}.")
            await _update_table(context, cid, w)
        if w[win_k]["s"] >= 4:
            await _end_war(update, context, cid, w, win_k)
        return

    if mentions_bot:
        question = re.sub(re.escape(f"@{bot_uname}"), "", msg, flags=re.IGNORECASE).strip()
        if question:
            await update.message.reply_text("📖 لحظات، بدور في الدستور...")
            answer = await ask_ai_general(question, u_tag, w)
            await update.message.reply_text(answer)
        return

# ─────────────────────────────────────────────
#  دوال مساعدة
# ─────────────────────────────────────────────
async def _make_draw(update, context, cid, w):
    p1 = list(w["c1"]["p"]); p2 = list(w["c2"]["p"])
    random.shuffle(p1); random.shuffle(p2)
    w["matches"]    = [{"p1": a, "p2": b, "s1": 0, "s2": 0} for a, b in zip(p1, p2)]
    w["draw_ts"]    = now_ts()
    w["reminded_1"] = False
    w["reminded_2"] = False
    save()
    rows = [f"{i+1} | {m['p1']} {emoji(0)}|🆚|{emoji(0)} {m['p2']}" for i, m in enumerate(w["matches"])]
    table = (
        f"🎲 القرعة الرسمية\n"
        f"A- [ {w['c1']['n']} ]  VS  B- [ {w['c2']['n']} ]\n"
        f"{'─'*30}\n" + "\n".join(rows) +
        f"\n{'─'*30}\n⌛ يومين وينتهي الوقت\n🔗 {AU_LINK}"
    )
    sent = await update.message.reply_text(table, disable_web_page_preview=True)
    w["mid"] = sent.message_id
    save()
    try:
        await context.bot.pin_chat_message(cid, sent.message_id)
    except:
        pass
    await update.message.reply_text("✅ تمت القرعة وتم تثبيت الجدول!\n⏰ سيصلك تذكير بعد يومين.")
    asyncio.create_task(task_remind_1(cid, context, TIME_REMIND_1))

async def _update_table(context, cid, w):
    if not w.get("mid"): return
    rows = [f"{i+1} | {m['p1']} {emoji(m['s1'])}|🆚|{emoji(m['s2'])} {m['p2']}" for i, m in enumerate(w["matches"])]
    table = (
        f"⚔️ {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
        f"{'─'*30}\n" + "\n".join(rows) +
        f"\n{'─'*30}\n🔗 {AU_LINK}"
    )
    try:
        await context.bot.edit_message_text(table, cid, w["mid"], disable_web_page_preview=True)
    except:
        pass

async def _end_war(update, context, cid, w, win_k):
    w["active"] = False
    w["end_ts"] = now_ts()
    save()
    real = [h for h in w[win_k]["stats"] if not h["is_free"]]
    if real:
        hasm = real[-1]["name"]
        star = max(real, key=lambda x: x["goals"] - x["rec"])
        result_msg = (
            f"🎊 فاز كلان {w[win_k]['n']} 🎊\n\n"
            f"🎯 الحاسم: {hasm}\n"
            f"⭐ النجم: {star['name']} (سجّل {star['goals']} واستقبل {star['rec']})"
        )
    else:
        result_msg = f"🎊 فوز إداري لكلان {w[win_k]['n']} 🎊"
    await update.message.reply_text(result_msg)
    detail = "\n".join(
        f"{i+1}. {m['p1']} {emoji(m['s1'])} - {emoji(m['s2'])} {m['p2']}"
        for i, m in enumerate(w["matches"])
    )
    await update.message.reply_text(f"📊 النتائج الكاملة:\n\n{detail}")
    asyncio.create_task(task_auto_send_after_6h(cid, context, TIME_AUTO_END))

async def post_init(application):
    await restore_tasks(application.bot)

    # ── فتح كل الجروبات مع كل تشغيل للبوت (مش مشروط بحالة ملف القفل) ──
    # كان بيحصل إن أي إعادة تشغيل للبوت (ريستارت على Railway) بيلاقي
    # maintenance_lock.json فاضي (لو مفيش Volume دائم متوصّل)، فيعتبر إنها
    # أول مرة (triggered=False) ويبدأ دورة قفل جديدة من الصفر تلقائيًا —
    # وده اللي كان بيقفل كل الجروبات من غير أي سبب حقيقي. اتشال التفعيل
    # التلقائي ده نهائيًا، وبقى فيه بس فتح فوري لكل جروب معروف مع كل
    # تشغيل، بغض النظر عن حالة الملف، عشان محدش يفضل مقفول للأبد.
    asyncio.create_task(open_all_groups_now(application.bot))

# ─────────────────────────────────────────────
#  تشغيل — Flask + env vars (للسيرفر/الاستضافة)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    load()
    load_images()
    load_groups()
    load_rules()
    load_warnings()
    load_maintenance()

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("setimage", cmd_setimage))
    app.add_handler(CommandHandler("images",   cmd_images))
    app.add_handler(CommandHandler("link",     cmd_group_link))
    app.add_handler(ChatMemberHandler(track_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(track_any_member_join, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION, handle_video))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_private_war_list
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_msg
    ))

    print("✅ البوت يعمل...")
    print(f"📤 الرابط سيُرسل إلى: {RESULTS_DESTINATION}")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
