import random
import re
import asyncio
import json
import os
import threading
from io import BytesIO
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    filters, ContextTypes
)
from flask import Flask

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

AU_LINK             = "https://t.me/arab_union3"
DATA_FILE           = "war_data.json"
IMAGES_FILE         = "stage_images.json"

# ── كليشة بدء المواجهة (تتبعت تلقائي + صورة + تثبيت لما تتحدد Clan vs Clan) ──
# حط صورة "مسؤول الحكام" جنب ملف البوت باسم referee_cliche.jpg (أو غيّر المسار هنا).
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

# تعديل 3: المسؤولان اللي بياخدوا قائمة المواجهات المفتوحة في الخاص
RESPONSIBLE_USERNAMES = {"leeeeeeeeevvi", "z6_i3"}

# تعديل 1: مهل تسليم القوائم بالساعات لكل دور
ROSTER_HOURS_16_QUARTER = 14   # دور الـ16 / ربع النهائي
ROSTER_HOURS_SEMI_FINAL = 18   # نصف النهائي / النهائي
# دور "دوري / أدوار أخرى" بيتسأل فيه الحكم عن عدد الساعات يدوياً

STAGES = ["دور الـ 16", "ربع النهائي", "نصف النهائي", "النهائي", "دوري"]

# مفتاح صورة "مسؤول الحكام" (كليشة بدء المواجهة) — بتتحط زي أي صورة دور بالظبط
# عن طريق /setimage مسؤول (بدل ما تكون ملف ثابت جنب الكود لازم يترفع يدويًا).
REFEREE_IMAGE_KEY = "مسؤول الحكام"
# كل المفاتيح اللي ممكن نضبط لها صورة (الأدوار + صورة مسؤول الحكام) — تستخدم في
# عرض حالة /images وفي التحقق من اكتمال الصور.
IMAGE_KEYS = STAGES + [REFEREE_IMAGE_KEY]

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
    "مسؤول": REFEREE_IMAGE_KEY, "مسؤول الحكام": REFEREE_IMAGE_KEY,
    "الحكام": REFEREE_IMAGE_KEY, "حكام": REFEREE_IMAGE_KEY,
    "كليشة": REFEREE_IMAGE_KEY, "كليشه": REFEREE_IMAGE_KEY,
    "referee": REFEREE_IMAGE_KEY,
}

# كلمات تشغيل أمر الرابط
LINK_TRIGGERS = {"الرابط", "رابط", "لينك", "link", "الينك"}

# كلمات تشغيل أمر عرض كل الجروبات المسجلة (خاص المسؤولين فقط)
GROUPS_LIST_TRIGGERS = {"الجروبات", "كل الجروبات", "جروبات"}
GROUPS_FILE = "known_groups.json"

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
    """استخراج الدور من نص — يدعم الأسماء والأرقام والاختصارات"""
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
    """يسجل/يحدّث بيانات جروب: الاسم، آخر نشاط، وهل البوت أدمن فيه."""
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
    """يسجل لما البوت يتضاف/يتشال/يترقّى أدمن في أي جروب."""
    cmu = update.my_chat_member
    if not cmu:
        return
    chat = cmu.chat
    new_status = cmu.new_chat_member.status
    if new_status in ("left", "kicked"):
        remember_chat(chat, removed=True)
    else:
        remember_chat(chat, is_admin=(new_status == "administrator"), removed=False)

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
#  جلب mention المالك
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
#  جلب / إنشاء رابط دعوة للجروب (يعمل حتى لو Private)
# ─────────────────────────────────────────────
async def get_group_invite_link(context, chat_id: int) -> str | None:
    """
    يحاول جلب رابط الجروب بعدة طرق:
    1) لو الجروب عنده يوزرنيم عام -> يرجع t.me/username مباشرة.
    2) غير كده يحاول export_chat_invite_link.
    3) لو فشلت يحاول ينشئ رابط دعوة جديد create_chat_invite_link.
    ⚠️ الدالة دي ما بتتخزنش الرابط — استخدم get_or_create_war_link عشان
       ما يتعملش رابط جديد كل مرة لنفس المواجهة (تعديل 2).
    """
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
    """
    تعديل 2: رابط واحد ثابت لكل مواجهة — يتم إنشاؤه أول مرة بس ويتخزن
    في بيانات المواجهة، وبعدها أي طلب للرابط بيرجع نفس القيمة المخزنة
    من غير ما ننشئ/نلغي رابط جديد.
    """
    if w.get("invite_link"):
        return w["invite_link"]
    link = await get_group_invite_link(context, cid)
    if link:
        w["invite_link"] = link
        save()
    return link

async def cmd_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يرد برابط الجروب الحالي عند كتابة: الرابط / رابط"""
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
#  تعديل 1: مهلة تسليم القوائم
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
    # لو القرعة اتعملت خلاص (يعني الاتنين بعتوا قوايمهم) مفيش داعي لأي إجراء
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

        # تعديل 1: استعادة مهلة القوائم
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
            "• /setimage دوري\n"
            "• /setimage مسؤول  (صورة مسؤول الحكام اللي بتتبعت مع كليشة القوائم)\n\n"
            "أو ابعت الصورة وفي الـ caption اكتب الأمر."
        )
        return

    stage = get_stage_from_text(stage_key)
    if not stage:
        await update.message.reply_text(
            f"❌ دور غير معروف: «{stage_key}»\n\n"
            "الأدوار المتاحة:\n"
            "دور16 | ربع | نصف | نهائي | دوري | مسؤول"
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

    status = "\n".join(f"{'✅' if s in stage_images else '❌'} {s}" for s in IMAGE_KEYS)
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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    caption = (update.message.caption or "").strip()
    if re.match(r'^/setimage', caption, re.IGNORECASE):
        await cmd_setimage(update, context)

# ─────────────────────────────────────────────
#  /images
# ─────────────────────────────────────────────
async def cmd_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = sum(1 for k in IMAGE_KEYS if k in stage_images)
    status = "\n".join(
        f"{'✅' if s in stage_images else '❌'} {s}"
        for s in IMAGE_KEYS
    )
    await update.message.reply_text(
        f"📸 حالة الصور ({total}/{len(IMAGE_KEYS)}):\n\n{status}\n\n"
        f"{'✅ جميع الصور محفوظة!' if total == len(IMAGE_KEYS) else '⚠️ بعض الصور ناقصة — استخدم /setimage لإضافتها'}"
    )

# ─────────────────────────────────────────────
#  تعديل 1: إنهاء إعداد المواجهة (بعد اختيار الدور / الساعات)
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

    # ── كليشة تعليمات القوائم + التثبيت التلقائي ──
    # الأولوية: صورة اتحطت عن طريق /setimage مسؤول (متخزنة كـ file_id زي باقي
    # صور الأدوار)، وبعدين الملف الثابت القديم لو موجود جنب الكود، وأخيرًا نص بس.
    try:
        bold_caption = f"<b>{WAR_START_CLICHE_TEXT}</b>"
        referee_file_id = stage_images.get(REFEREE_IMAGE_KEY)
        if referee_file_id:
            cliche_msg = await context.bot.send_photo(
                cid, photo=referee_file_id, caption=bold_caption, parse_mode="HTML"
            )
        elif os.path.exists(WAR_START_CLICHE_IMAGE):
            with open(WAR_START_CLICHE_IMAGE, "rb") as img_f:
                cliche_msg = await context.bot.send_photo(
                    cid, photo=img_f, caption=bold_caption, parse_mode="HTML"
                )
        else:
            cliche_msg = await context.bot.send_message(
                cid, bold_caption, parse_mode="HTML"
            )
            print("⚠️ مفيش صورة لمسؤول الحكام — لا متسجلة بـ /setimage مسؤول ولا الملف الثابت موجود.")
        try:
            await context.bot.pin_chat_message(cid, cliche_msg.message_id)
        except Exception as e:
            print(f"❌ خطأ في تثبيت كليشة القوائم: {e}")
    except Exception as e:
        print(f"❌ خطأ في إرسال كليشة القوائم: {e}")

    asyncio.create_task(task_check_roster_deadline(cid, context, hours * 3600))

# ─────────────────────────────────────────────
#  تعديل 3: قائمة المواجهات المفتوحة (خاص المسؤولين)
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
        # تأكد الأول إن البوت لسه عنده وصول للجروب ده (يتجنب أخطاء "Chat not found"
        # بتاعة مواجهات قديمة في war_data.json من جروبات اتشال منها البوت أو اتمسحت)
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
#  المعالج الرئيسي (داخل الجروبات)
# ─────────────────────────────────────────────
async def _handle_msg_core(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    cid    = update.effective_chat.id
    msg    = update.message.text
    msg_up = msg.upper().strip()
    msg_cl = clean(msg)
    user   = update.effective_user
    u_tag  = f"@{user.username}" if user.username else f"ID:{user.id}"

    remember_chat(update.effective_chat)

    try:
        cm         = await context.bot.get_chat_member(cid, user.id)
        is_creator = (cm.status == 'creator')
        is_ref     = is_creator
    except:
        is_creator = False
        is_ref     = False

    w = wars.get(cid)

    # ══════ 0.0 أمر الرابط ══════
    if msg_cl.strip() in LINK_TRIGGERS:
        await cmd_group_link(update, context)
        return

    # ══════ 0. انتظار الدور ══════
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

    # ══════ 0.5 انتظار عدد ساعات القوائم (دوري) ══════
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

    # ══════ 1. بدء المواجهة ══════
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
        return

    if not w or w.get("waiting_stage"):
        # لسه مفيش مواجهة نشطة (أو بننتظر اختيار الدور) — مفيش رد آلي هنا بعد شيل الحكم الآلي.
        return

    # ══════ 2. انهاء مواجهه ══════
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

    # ══════ 3. الاعتراض ══════
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

        await update.message.reply_text(
            f"⚖️ اعتراض رسمي مسجّل\n━━━━━━━━━━━━━━\n"
            f"👤 مقدّم الاعتراض: {objector}\n"
            f"📊 النتيجة الحالية: {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
            f"📝 نص الاعتراض:\n{msg}\n"
            f"━━━━━━━━━━━━━━\n⏳ سيتم البت فيه من المالك."
        )
        return

    # ══════ 4. تسجيل القائمة ══════
    if "قائم" in msg_cl and update.message.reply_to_message:
        c1n, c2n = w["c1"]["n"].upper(), w["c2"]["n"].upper()
        # ⚠️ إصلاح: المطابقة القديمة كانت "in" بسيطة، فلو اسم كلان كان جزء من
        # اسم التاني (مثلاً STO جوه STORM) القائمتين كانوا بيتسجلوا غلط لنفس
        # الكلان، والقرعة كانت بتفضل مستنية الطرف التاني للأبد. دلوقتي بنستخدم
        # حدود كلمة (\b) عشان المطابقة تبقى دقيقة.
        m1 = re.search(rf'\b{re.escape(c1n)}\b', msg_up)
        m2 = re.search(rf'\b{re.escape(c2n)}\b', msg_up)
        target_k = "c1" if (m1 and not m2) else "c2" if (m2 and not m1) else None
        if not target_k:
            await update.message.reply_text("❌ اكتب اسم الكلان بشكل صحيح ومنفرد مع كلمة قائمة.")
            return
        # ⚠️ إصلاح: لو القائمة اتبعتت كصورة وكابشن (مش رسالة نصية)، .text كانت
        # بترجع None وتوقّع الكود بصمت من غير أي رد (وده كان شكله "تعليق" للبوت).
        reply_msg = update.message.reply_to_message
        roster_source = reply_msg.text or reply_msg.caption or ""
        players = [p.strip() for p in roster_source.split('\n') if p.strip().startswith('@')]
        if not players:
            await update.message.reply_text("❌ لا يوجد لاعبون (يجب أن تبدأ بـ @). لو القائمة صورة، لازم يكون فيها كابشن باليوزرات.")
            return
        w[target_k]["leader"] = u_tag
        w[target_k]["p"]      = players
        save()
        await update.message.reply_text(f"✅ قائمة {w[target_k]['n']} مقبولة ({len(players)} لاعبين) بواسطة {u_tag}.")
        if w["c1"]["p"] and w["c2"]["p"]:
            await _make_draw(update, context, cid, w)
        return

    # ══════ 5. إضافة نقطة ══════
    if ("+1" in msg_up or "+ 1" in msg_up) and w.get("active"):
        m1 = re.search(rf'\b{re.escape(w["c1"]["n"].upper())}\b', msg_up)
        m2 = re.search(rf'\b{re.escape(w["c2"]["n"].upper())}\b', msg_up)
        win_k = "c1" if (m1 and not m2) else "c2" if (m2 and not m1) else None
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

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """غلاف حماية حول _handle_msg_core — قبل كده أي استثناء غير متوقع جوه أي
    قسم من الأقسام (تسجيل قائمة، +1، اعتراض...) كان بيتبلع بصمت من غير رد
    ولا حتى لوج واضح (وده كان شكله للمستخدم إن البوت "علّق"). دلوقتي أي
    استثناء بيتسجل في اللوج + المستخدم بياخد رسالة واضحة بدل الصمت."""
    try:
        await _handle_msg_core(update, context)
    except Exception as e:
        print(f"❌ خطأ غير متوقع في handle_msg: {e}")
        try:
            if update.message:
                await update.message.reply_text(
                    "⚠️ حصل خطأ غير متوقع أثناء تنفيذ الأمر ده. جرب تاني، ولو اتكرر كلّم مسؤول الحكام."
                )
        except Exception:
            pass

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

async def global_error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أخطاء عام مسجّل على مستوى الـ Application. قبل كده مفيش أي معالج
    مسجّل، فأي استثناء (زي انقطاعات الشبكة أثناء get_updates على Railway) كان
    بيتسجّل بس في اللوج بتحذير "No error handlers are registered" من غير أي
    إجراء، وده اللي كان بيدي إحساس إن البوت "علّق". دلوقتي على الأقل بيتسجل
    بشكل واضح، ولو فيه رسالة مرتبطة بيه ممكن نبلغ المستخدم."""
    print(f"❌ خطأ عام في الـ Application: {context.error}")
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ حصل خطأ تقني مؤقت (ممكن يكون انقطاع شبكة). لو الأمر متكرر، جرب تاني بعد شوية."
            )
    except Exception:
        pass

# ─────────────────────────────────────────────
#  تشغيل — Flask + env vars (للسيرفر/الاستضافة)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    load()
    load_images()
    load_groups()

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
    # تسجيل الجروبات: لما البوت يتضاف/يتشال/يترقّى أدمن
    app.add_handler(ChatMemberHandler(track_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    # ← مهم: قبل TEXT handler
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    # تعديل 3: أمر "مواجهة/مواجهه" في الخاص للمسؤولين فقط
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_private_war_list
    ))
    # المعالج الرئيسي — الجروبات بس
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_msg
    ))
    app.add_error_handler(global_error_handler)

    print("✅ البوت يعمل...")
    print(f"📤 الرابط سيُرسل إلى: {RESULTS_DESTINATION}")
    app.run_polling(drop_pending_updates=True)
