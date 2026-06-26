import random
import re
import asyncio
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ChatMemberHandler
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
TOKEN               = os.environ.get("BOT_TOKEN")
RESULTS_DESTINATION = int(os.environ.get("RESULTS_DESTINATION", "1449739390"))
AU_LINK             = "https://t.me/arab_union3"
DATA_FILE           = "war_data.json"
ALL_CHATS_FILE      = "all_chats.json"

TIME_REMIND_1 = 2 * 24 * 3600
TIME_REMIND_2 = 3 * 24 * 3600
TIME_AUTO_END = 6 * 3600

# ─────────────────────────────────────────────
#  إعدادات يوم العزاء
# ─────────────────────────────────────────────
IRAQ_TZ   = timezone(timedelta(hours=3))
LOCK_DT   = datetime(2026, 6, 26, 0, 0, 0, tzinfo=IRAQ_TZ)
UNLOCK_DT = datetime(2026, 6, 26, 12, 0, 0, tzinfo=IRAQ_TZ)  # وقت في الماضي → العزاء انتهى

MOURNING_LOCK_MSG = (
    "<b>أعظَمَ اللهُ اُجورَنا وأجوركم بِمُصابِنا\n"
    "بِالحُسَينِ عليه السلام</b>\n\n"
    "<blockquote><b>إيقاف المواجهات ل مدة يوم كامل</b></blockquote>\n\n"
    "<b>احتراما ل ابن بنت رسول الله صلى الله عليه واله وسلم و هذا يوم العظيم</b>"
)

LOCKED_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
)

OPEN_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
)

# انتظار تأكيد القفل {user_id: True}
_mourning_pending = {}

# ─────────────────────────────────────────────
#  بيانات الحرب
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
        print("✅ بيانات الحرب محملة")

# ─────────────────────────────────────────────
#  قاعدة جميع الجروبات
# ─────────────────────────────────────────────
all_chats = {}

def save_chats():
    with open(ALL_CHATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_chats, f, ensure_ascii=False, indent=2)

def load_chats():
    global all_chats
    if os.path.exists(ALL_CHATS_FILE):
        with open(ALL_CHATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        all_chats = {int(k): v for k, v in data.items()}
        print(f"✅ {len(all_chats)} جروب محمل في القاعدة")

def is_mourning_active() -> bool:
    now = datetime.now(timezone.utc)
    return LOCK_DT <= now < UNLOCK_DT

# ─────────────────────────────────────────────
#  تسجيل جروب + قفل تلقائي لو في فترة العزاء
# ─────────────────────────────────────────────
async def register_chat(chat_id: int, bot=None):
    is_new = chat_id not in all_chats

    if is_new:
        all_chats[chat_id] = {"mourning_locked": False}

    if is_mourning_active() and not all_chats[chat_id].get("mourning_locked") and bot:
        try:
            await bot.set_chat_permissions(chat_id, LOCKED_PERMS)
            await bot.send_message(chat_id, MOURNING_LOCK_MSG, parse_mode="HTML")
            all_chats[chat_id]["mourning_locked"] = True
            print(f"🔒 قفل تلقائي للجروب الجديد {chat_id}")
        except Exception as e:
            print(f"❌ فشل قفل الجروب الجديد {chat_id}: {e}")

    if is_new or all_chats[chat_id].get("mourning_locked"):
        save_chats()

# ─────────────────────────────────────────────
#  Handler: لما البوت يتضاف/يتطرد
# ─────────────────────────────────────────────
async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return

    chat       = result.chat
    new_status = result.new_chat_member.status

    if chat.type == "private":
        return

    if new_status in ("member", "administrator"):
        print(f"➕ البوت اتضاف لجروب: {chat.title} ({chat.id})")
        await register_chat(chat.id, bot=context.bot)

    elif new_status in ("left", "kicked"):
        if chat.id in all_chats:
            del all_chats[chat.id]
            save_chats()
            print(f"🗑 تم حذف الجروب: {chat.title} ({chat.id})")

# ─────────────────────────────────────────────
#  دوال مساعدة
# ─────────────────────────────────────────────
def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()

def emoji(n):
    d = {'0':'0️⃣','1':'1️⃣','2':'2️⃣','3':'3️⃣','4':'4️⃣',
         '5':'5️⃣','6':'6️⃣','7':'7️⃣','8':'8️⃣','9':'9️⃣'}
    return "".join(d.get(c, c) for c in str(n))

def clean(text):
    if not text: return ""
    t = text.lower()
    t = t.replace('ة','ه').replace('أ','ا').replace('إ','ا').replace('آ','ا')
    return t

async def get_owner_mention(bot, chat_id: int) -> str:
    try:
        admins = await bot.get_chat_administrators(chat_id)
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
#  جلب رابط الجروب الفعلي
# ─────────────────────────────────────────────
async def get_group_link(bot, chat_id: int) -> str:
    try:
        chat = await bot.get_chat(chat_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
        if chat.invite_link:
            return chat.invite_link
        # توليد رابط دعوة جديد
        return await bot.export_chat_invite_link(chat_id)
    except Exception as e:
        print(f"⚠️ تعذّر جلب رابط الجروب {chat_id}: {e}")
        return f"https://t.me/c/{str(chat_id).replace('-100', '')}"

# ─────────────────────────────────────────────
#  إرسال رابط المواجهة
# ─────────────────────────────────────────────
async def send_war_link(context, chat_id: int, reason: str):
    w = wars.get(chat_id)
    if not w or w.get("link_sent"):
        return
    c1, c2 = w["c1"]["n"], w["c2"]["n"]
    s1, s2 = w["c1"]["s"], w["c2"]["s"]

    # رابط الجروب الفعلي وليس رابط رسالة
    group_link = await get_group_link(context.bot, chat_id)

    text = (
        f"📋 {reason}\n\n"
        f"⚔️ المواجهة: {c1} {s1} - {s2} {c2}\n"
        f"🔗 رابط الجروب: {group_link}\n"
        f"🆔 ID الجروب: {chat_id}"
    )
    try:
        await context.bot.send_message(RESULTS_DESTINATION, text, disable_web_page_preview=True)
        w["link_sent"] = True
        save()
        print(f"✅ تم إرسال الرابط إلى {RESULTS_DESTINATION}")
    except Exception as e:
        print(f"❌ فشل إرسال الرابط: {e}")

# ─────────────────────────────────────────────
#  مهام خلفية — تنبيهات المواجهات
# ─────────────────────────────────────────────
async def task_remind_1(chat_id: int, bot, delay: float):
    if delay > 0:
        await asyncio.sleep(delay)
    w = wars.get(chat_id)
    if not w or not w.get("active"):
        return
    owner_mention = await get_owner_mention(bot, chat_id)
    try:
        await bot.send_message(
            chat_id,
            f"⏰ مرت يومان على القرعة.\n"
            f"📢 تنبيه لمالك الجروب: {owner_mention}\n"
            f"❓ هل انتهت المواجهة؟ يرجى إنهاؤها.\n\n"
            f"(اكتب: انهاء مواجهه)",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ خطأ في task_remind_1: {e}")
    asyncio.create_task(task_remind_2(chat_id, bot, 24 * 3600))

async def task_remind_2(chat_id: int, bot, delay: float):
    if delay > 0:
        await asyncio.sleep(delay)
    w = wars.get(chat_id)
    if not w or not w.get("active"):
        return
    owner_mention = await get_owner_mention(bot, chat_id)
    try:
        await bot.send_message(
            chat_id,
            f"⚠️ {owner_mention} مرت 3 أيام ولم تنتهِ المواجهة.\n"
            f"اكتب: انهاء مواجهه لإنهائها وإرسال الرابط.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ خطأ في task_remind_2: {e}")

async def task_auto_send_after_6h(chat_id: int, context, delay: float = TIME_AUTO_END):
    if delay > 0:
        await asyncio.sleep(delay)
    await send_war_link(context, chat_id, "✅ أُرسل تلقائياً بعد 6 ساعات من انتهاء المواجهة.")

# ─────────────────────────────────────────────
#  وظائف يوم العزاء
# ─────────────────────────────────────────────
async def do_lock_all(bot):
    locked = 0
    failed = 0
    for chat_id, info in all_chats.items():
        try:
            await bot.set_chat_permissions(chat_id, LOCKED_PERMS)
            await bot.send_message(chat_id, MOURNING_LOCK_MSG, parse_mode="HTML")
            info["mourning_locked"] = True
            locked += 1
            print(f"🔒 تم قفل الجروب {chat_id}")
        except Exception as e:
            failed += 1
            print(f"❌ فشل قفل {chat_id}: {e}")
    save_chats()
    print(f"✅ تم قفل {locked} جروب | فشل {failed}")
    return locked, failed

async def do_unlock_all(bot):
    """فتح جميع الجروبات المقفولة فوراً بدون انتظار"""
    unlocked = 0
    for chat_id, info in all_chats.items():
        if info.get("mourning_locked"):
            try:
                await bot.set_chat_permissions(chat_id, OPEN_PERMS)
                await bot.send_message(
                    chat_id,
                    "<b>سيتم استئناف المواجهات الان بعد انتهاء المده المحدده</b>",
                    parse_mode="HTML"
                )
                info["mourning_locked"] = False
                unlocked += 1
                print(f"🔓 تم فتح الجروب {chat_id}")
            except Exception as e:
                print(f"❌ فشل فتح {chat_id}: {e}")
    if unlocked:
        save_chats()
    print(f"✅ تم فتح {unlocked} جروب")

async def task_unlock_mourning(bot):
    """فتح فوري بدون انتظار منتصف الليل"""
    await do_unlock_all(bot)

# ─────────────────────────────────────────────
#  استعادة المهام عند إعادة التشغيل
# ─────────────────────────────────────────────
async def restore_tasks(application):
    now = now_ts()

    # ─── استعادة تنبيهات المواجهات ───
    for chat_id, w in wars.items():
        if w.get("active") and w.get("draw_ts") and w.get("mid"):
            elapsed = now - float(w["draw_ts"])
            delay_1 = max(0.0, TIME_REMIND_1 - elapsed)
            delay_2 = max(0.0, TIME_REMIND_2 - elapsed)
            if not w.get("reminded_1"):
                asyncio.create_task(task_remind_1(chat_id, application.bot, delay_1))
                print(f"🔁 [{chat_id}] تنبيه 1 بعد {int(delay_1//3600)}س")
            elif not w.get("reminded_2"):
                asyncio.create_task(task_remind_2(chat_id, application.bot, delay_2))
                print(f"🔁 [{chat_id}] تنبيه 2 بعد {int(delay_2//3600)}س")

        elif not w.get("active") and not w.get("link_sent") and w.get("end_ts"):
            elapsed = now - float(w["end_ts"])
            delay   = max(0.0, TIME_AUTO_END - elapsed)
            print(f"🔁 [{chat_id}] إرسال رابط بعد {int(delay//3600)}س {int((delay%3600)//60)}د")

    print("✅ استعادة المهام اكتملت")

# ─────────────────────────────────────────────
#  /start — صامت (لا يرد)
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # تسجيل الجروب فقط إن كان من جروب، بدون أي رد
    if update.effective_chat.type != "private":
        await register_chat(update.effective_chat.id, bot=context.bot)
    return

# ─────────────────────────────────────────────
#  المعالج الرئيسي
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

    # ─── تسجيل الجروب تلقائياً ───
    if update.effective_chat.type != "private":
        await register_chat(cid, bot=context.bot)

    # ─── صلاحيات ───
    try:
        cm         = await context.bot.get_chat_member(cid, user.id)
        is_creator = (cm.status == 'creator')
        is_ref     = is_creator
    except:
        is_creator = False
        is_ref     = False

    w = wars.get(cid)

    # ══════════════════════════════════════════
    # 0.5 أمر حالة — للتشخيص
    # ══════════════════════════════════════════
    if msg_cl.strip() == "حاله" or msg_cl.strip() == "حالة":
        locked_count = sum(1 for v in all_chats.values() if v.get("mourning_locked"))
        await update.message.reply_text(
            f"🤖 <b>البوت شغال</b>\n"
            f"📊 جروبات مسجلة: <b>{len(all_chats)}</b>\n"
            f"🔒 جروبات مقفولة: <b>{locked_count}</b>\n"
            f"⚔️ مواجهات نشطة: <b>{sum(1 for w in wars.values() if w.get('active'))}</b>\n"
            f"🆔 ID الجروب ده: <code>{cid}</code>",
            parse_mode="HTML"
        )
        return

    # ══════════════════════════════════════════
    # 0. يوم العزاء — تيست / تمم / الغاء
    # ══════════════════════════════════════════
    if msg_cl.strip() == "تيست":
        if not is_creator:
            await update.message.reply_text("🚫 هذا الأمر لمالك الجروب فقط.")
            return
        _mourning_pending[user.id] = True
        total = len(all_chats)
        preview = (
            f"👁 <b>معاينة رسالة الإيقاف:</b>\n"
            f"━━━━━━━━━━━━━━\n\n"
            + MOURNING_LOCK_MSG +
            f"\n\n━━━━━━━━━━━━━━\n"
            f"📊 عدد الجروبات التي ستُقفل: <b>{total}</b>\n\n"
            f"✅ أرسل <b>تمم</b> لتطبيق القفل على جميع الجروبات\n"
            f"❌ أرسل <b>الغاء</b> للإلغاء"
        )
        await update.message.reply_text(preview, parse_mode="HTML")
        return

    if _mourning_pending.get(user.id):
        if "تمم" in msg_cl:
            _mourning_pending.pop(user.id, None)
            total = len(all_chats)
            await update.message.reply_text(
                f"⏳ <b>جاري قفل {total} جروب...</b>",
                parse_mode="HTML"
            )
            locked, failed = await do_lock_all(context.bot)
            # فتح فوري بعد القفل مباشرة (للتيست)
            asyncio.create_task(do_unlock_all(context.bot))
            await update.message.reply_text(
                f"✅ <b>تم قفل {locked} جروب بنجاح</b>"
                + (f"\n⚠️ فشل القفل في {failed} جروب" if failed else "") +
                f"\n⏰ سيُفتح تلقائياً قريباً",
                parse_mode="HTML"
            )
            return
        elif "الغاء" in msg_cl:
            _mourning_pending.pop(user.id, None)
            await update.message.reply_text("❌ تم إلغاء العملية.")
            return

    # ══════════════════════════════════════════
    # 1. بدء المواجهة
    # ══════════════════════════════════════════
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
            "c1": {"n": c1, "s": 0, "p": [], "stats": [], "leader": None},
            "c2": {"n": c2, "s": 0, "p": [], "stats": [], "leader": None},
            "active": True, "mid": None, "matches": [],
            "link_sent": False,
            "waiting_objection": False,
            "draw_ts": None,
            "end_ts": None,
            "reminded_1": False,
            "reminded_2": False,
        }
        save()
        await update.message.reply_text(f"⚔️ بدأت الحرب!\n🔥 {c1}  VS  {c2}")
        try:
            await context.bot.set_chat_title(cid, f"⚔️ {c1} 0 - 0 {c2} ⚔️")
        except:
            pass
        return

    if not w:
        return

    # ══════════════════════════════════════════
    # 2. انهاء مواجهه
    # ══════════════════════════════════════════
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

    # ══════════════════════════════════════════
    # 3. الاعتراض
    # ══════════════════════════════════════════
    if "عندي اعتراض" in msg_cl or msg_cl.strip() == "اعتراض":
        is_leader = u_tag in [w["c1"].get("leader"), w["c2"].get("leader")]
        if not (is_ref or is_leader):
            await update.message.reply_text("❌ الاعتراض متاح للمالك والقادة فقط.")
            return
        w["waiting_objection"] = True
        w["objection_by"]      = u_tag
        save()
        await update.message.reply_text(
            "📝 اكتب نص اعتراضك كاملاً في رسالة واحدة.\nأو أرسل: الغاء  للتراجع."
        )
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
            f"⚖️ اعتراض رسمي مسجّل\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 مقدّم الاعتراض: {objector}\n"
            f"📊 النتيجة الحالية: {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
            f"📝 نص الاعتراض:\n{msg}\n"
            f"━━━━━━━━━━━━━━\n"
            f"⏳ سيتم البت فيه من المالك."
        )
        return

    # ══════════════════════════════════════════
    # 4. تسجيل القائمة
    # ══════════════════════════════════════════
    if "قائم" in msg_cl and update.message.reply_to_message:
        target_k = None
        if w["c1"]["n"].upper() in msg_up:
            target_k = "c1"
        elif w["c2"]["n"].upper() in msg_up:
            target_k = "c2"
        if not target_k:
            await update.message.reply_text("❌ اكتب اسم الكلان بشكل صحيح مع كلمة قائمة.")
            return
        players = [
            p.strip() for p in update.message.reply_to_message.text.split('\n')
            if p.strip().startswith('@')
        ]
        if not players:
            await update.message.reply_text("❌ لا يوجد لاعبون في الرسالة (يجب أن تبدأ بـ @).")
            return
        w[target_k]["leader"] = u_tag
        w[target_k]["p"]      = players
        save()
        await update.message.reply_text(
            f"✅ قائمة {w[target_k]['n']} مقبولة ({len(players)} لاعبين) بواسطة {u_tag}."
        )
        if w["c1"]["p"] and w["c2"]["p"]:
            await _make_draw(update, context, cid, w)
        return

    # ══════════════════════════════════════════
    # 5. إضافة نقطة
    # ══════════════════════════════════════════
    if ("+1" in msg_up or "+ 1" in msg_up) and w.get("active"):
        win_k = (
            "c1" if w["c1"]["n"].upper() in msg_up
            else "c2" if w["c2"]["n"].upper() in msg_up
            else None
        )
        if not win_k:
            return

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
            w[win_k]["stats"].append({
                "name": p_win, "goals": max(sc1, sc2),
                "rec": min(sc1, sc2), "is_free": False
            })
            for m in w["matches"]:
                p1u, p2u = m["p1"].upper(), m["p2"].upper()
                if u1.upper() in (p1u, p2u) and u2.upper() in (p1u, p2u):
                    m["s1"], m["s2"] = (sc1, sc2) if u1.upper() == p1u else (sc2, sc1)
            save()
            await update.message.reply_text(
                f"✅ نقطة لـ {w[win_k]['n']}  |  {u1} {sc1} - {sc2} {u2}"
            )
            await _update_table(context, cid, w)
            if is_creator:
                try:
                    await context.bot.set_chat_title(
                        cid,
                        f"⚔️ {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']} ⚔️"
                    )
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

# ─────────────────────────────────────────────
#  دوال مساعدة للمواجهة
# ─────────────────────────────────────────────
async def _make_draw(update, context, cid, w):
    p1 = list(w["c1"]["p"])
    p2 = list(w["c2"]["p"])
    random.shuffle(p1)
    random.shuffle(p2)
    pairs = list(zip(p1, p2))
    w["matches"]    = [{"p1": a, "p2": b, "s1": 0, "s2": 0} for a, b in pairs]
    w["draw_ts"]    = now_ts()
    w["reminded_1"] = False
    w["reminded_2"] = False
    save()
    rows = [
        f"{i+1} | {m['p1']} {emoji(0)}|🆚|{emoji(0)} {m['p2']}"
        for i, m in enumerate(w["matches"])
    ]
    table = (
        f"🎲 القرعة الرسمية\n"
        f"A- [ {w['c1']['n']} ]  VS  B- [ {w['c2']['n']} ]\n"
        f"{'─'*30}\n"
        + "\n".join(rows) +
        f"\n{'─'*30}\n⌛ يومين وينتهي الوقت\n🔗 {AU_LINK}"
    )
    sent = await update.message.reply_text(table, disable_web_page_preview=True)
    w["mid"] = sent.message_id
    save()
    try:
        await context.bot.pin_chat_message(cid, sent.message_id)
    except Exception as e:
        print(f"تعذّر التثبيت: {e}")
    await update.message.reply_text(
        "✅ تمت القرعة وتم تثبيت الجدول!\n⏰ سيصلك تذكير بعد يومين."
    )
    asyncio.create_task(task_remind_1(cid, context.bot, TIME_REMIND_1))

async def _update_table(context, cid, w):
    if not w.get("mid"):
        return
    rows = [
        f"{i+1} | {m['p1']} {emoji(m['s1'])}|🆚|{emoji(m['s2'])} {m['p2']}"
        for i, m in enumerate(w["matches"])
    ]
    table = (
        f"⚔️ {w['c1']['n']} {w['c1']['s']} - {w['c2']['s']} {w['c2']['n']}\n"
        f"{'─'*30}\n"
        + "\n".join(rows) +
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
        hasm      = real[-1]["name"]
        star_data = max(real, key=lambda x: x["goals"] - x["rec"])
        result_msg = (
            f"🎊 فاز كلان {w[win_k]['n']} 🎊\n\n"
            f"🎯 الحاسم: {hasm}\n"
            f"⭐ النجم: {star_data['name']} (سجّل {star_data['goals']} واستقبل {star_data['rec']})"
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

# ─────────────────────────────────────────────
#  post_init
# ─────────────────────────────────────────────
async def post_init(application):
    bot = application.bot

    # ─── استيراد الجروبات من بيانات الحرب لو all_chats فاضي ───
    synced = 0
    for chat_id in wars:
        if chat_id not in all_chats:
            all_chats[chat_id] = {"mourning_locked": True}
            synced += 1
    if synced:
        save_chats()
        print(f"🔄 تم استيراد {synced} جروب من بيانات الحرب")

    # ─── فتح قسري لجميع الجروبات المعروفة ───
    unlocked = 0
    failed   = 0
    for chat_id, info in all_chats.items():
        try:
            await bot.set_chat_permissions(chat_id, OPEN_PERMS)
            await bot.send_message(
                chat_id,
                "<b>سيتم استئناف المواجهات الان بعد انتهاء المده المحدده</b>",
                parse_mode="HTML"
            )
            info["mourning_locked"] = False
            unlocked += 1
            print(f"🔓 فُتح {chat_id}")
        except Exception as e:
            failed += 1
            print(f"❌ فشل فتح {chat_id}: {e}")
    if unlocked:
        save_chats()

    # ─── إشعار تشغيل ───
    try:
        await bot.send_message(
            RESULTS_DESTINATION,
            f"✅ <b>البوت اشتغل</b>\n"
            f"📊 جروبات مسجلة: <b>{len(all_chats)}</b>\n"
            f"🔓 جروبات فُتحت: <b>{unlocked}</b>"
            + (f"\n⚠️ فشل فتح: <b>{failed}</b>" if failed else ""),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ فشل إشعار التشغيل: {e}")

    await restore_tasks(application)

# ─────────────────────────────────────────────
#  تشغيل البوت
# ─────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    load()
    load_chats()

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    print("✅ البوت يعمل...")
    print(f"📊 عدد الجروبات المسجلة: {len(all_chats)}")
    print(f"📤 الرابط سيُرسل إلى: {RESULTS_DESTINATION}")

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
