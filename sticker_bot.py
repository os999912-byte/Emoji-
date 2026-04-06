"""
Telegram Sticker & Premium Emoji Pack Bot
Токен берётся из переменной окружения BOT_TOKEN.

Автоматически обрабатывает изображения:
  - Ресайз до 512x512 (стикеры) или 100x100 (эмодзи)
  - Конвертация в PNG с прозрачностью
  - Сжатие если файл слишком большой
"""

import io
import logging
import os
import random
import re
import string

from PIL import Image

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputSticker,
    Update,
)
from telegram.constants import StickerFormat, StickerType
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

(
    MAIN_MENU,
    CHOOSE_TYPE,
    PACK_NAME,
    PACK_LINK,
    ADDING_STICKER,
    WAITING_EMOJI,
    PACK_SELECTED,
    ADD_STICKER_FILE,
    ADD_STICKER_EMOJI,
    DELETE_STICKER,
    CHANGE_ICON,
) = range(12)

# Максимальный размер выходного файла стикера (лимит Telegram)
MAX_STICKER_BYTES = 500 * 1024
# Максимальный размер входного файла от пользователя
MAX_INPUT_BYTES = 10 * 1024 * 1024


# ── Утилиты ───────────────────────────────────────────────────────────────────

def random_suffix(length: int = 10) -> str:
    first = random.choice(string.ascii_lowercase)
    rest  = "".join(random.choices(string.ascii_lowercase + string.digits, k=length - 1))
    return first + rest


def sanitize_suffix(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]", "", raw.lower())
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "s" + cleaned
    cleaned = cleaned[:64]
    if len(cleaned) < 5:
        cleaned = cleaned + random_suffix(5 - len(cleaned))
    return cleaned


def build_pack_name(bot_username: str, suffix: str) -> str:
    return f"{suffix}_by_{bot_username}"


def plural_sticker(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return "стикеров"
    r = n % 10
    if r == 1:      return "стикер"
    if 2 <= r <= 4: return "стикера"
    return "стикеров"


def pack_url(pack_name: str) -> str:
    return f"https://t.me/addstickers/{pack_name}"


def get_packs(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> list:
    return context.bot_data.setdefault(str(user_id), {}).setdefault("packs", [])


def back_btn(label: str = "◀️ Назад", data: str = "begin") -> list:
    return [InlineKeyboardButton(label, callback_data=data)]


def _friendly_tg_error(err: str) -> str:
    if "STICKERSET_INVALID" in err or "invalid" in err.lower():
        return "Недопустимое название пака. Попробуй другое."
    if "PEER_ID_INVALID" in err:
        return "Сначала напиши боту /start в личке Telegram."
    if "file is too big" in err.lower() or "FILE_PARTS" in err:
        return "Файл слишком большой даже после сжатия. Попробуй изображение поменьше."
    if "wrong file type" in err.lower() or "STICKER_PNG" in err:
        return "Неподходящий формат файла. Отправь PNG, WEBP или обычное фото."
    if "STICKERS_TOO_MUCH" in err:
        return "В паке уже максимальное количество стикеров (120)."
    if "bot was blocked" in err.lower():
        return "Бот заблокирован. Разблокируй его и попробуй снова."
    return err


# ── Обработка изображений ─────────────────────────────────────────────────────

def process_image(raw_bytes: bytes, size: int, max_bytes: int = MAX_STICKER_BYTES) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - img.width) // 2, (size - img.height) // 2)
    canvas.paste(img, offset, img)
    for compress in range(1, 10):
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True, compress_level=compress)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data
    scale = 0.9
    while len(data) > max_bytes and scale > 0.3:
        inner = (int(size * scale), int(size * scale))
        resized = canvas.resize(inner, Image.LANCZOS)
        final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        off = ((size - inner[0]) // 2, (size - inner[1]) // 2)
        final.paste(resized, off, resized)
        buf = io.BytesIO()
        final.save(buf, format="PNG", optimize=True, compress_level=9)
        data = buf.getvalue()
        scale -= 0.1
    return data


def process_image_for_sticker(raw_bytes: bytes, pack_type: str = "sticker") -> bytes:
    size = 512 if pack_type == "sticker" else 100
    return process_image(raw_bytes, size)


def process_image_for_thumbnail(raw_bytes: bytes) -> bytes:
    return process_image(raw_bytes, 100, max_bytes=32 * 1024)


# ── Получение и подготовка файла для InputSticker ────────────────────────────

async def get_sticker_data(bot, msg, pack_type: str = "sticker"):
    async def dl(file_id: str) -> bytes:
        f   = await bot.get_file(file_id)
        buf = io.BytesIO()
        await f.download_to_memory(buf)
        return buf.getvalue()

    if msg.sticker:
        s   = msg.sticker
        fmt = s.format if hasattr(s, "format") else StickerFormat.STATIC
        raw = await dl(s.file_id)
        if fmt == StickerFormat.STATIC:
            return process_image_for_sticker(raw, pack_type), fmt
        else:
            return raw, fmt

    if msg.document:
        d    = msg.document
        mime = (d.mime_type or "").lower()
        name = (d.file_name or "").lower()
        if "webm" in mime or name.endswith(".webm"):
            return await dl(d.file_id), StickerFormat.VIDEO
        if "tgs" in mime or name.endswith(".tgs"):
            return await dl(d.file_id), StickerFormat.ANIMATED
        raw = await dl(d.file_id)
        return process_image_for_sticker(raw, pack_type), StickerFormat.STATIC

    if msg.photo:
        raw = await dl(msg.photo[-1].file_id)
        return process_image_for_sticker(raw, pack_type), StickerFormat.STATIC

    if msg.video:
        return await dl(msg.video.file_id), StickerFormat.VIDEO

    if msg.animation:
        return await dl(msg.animation.file_id), StickerFormat.VIDEO

    return None, None


# ── Главное меню ──────────────────────────────────────────────────────────────

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [
        [InlineKeyboardButton("🖼  Создать стикер-пак",  callback_data="create_sticker")],
        [InlineKeyboardButton("✨  Создать эмодзи-пак",   callback_data="create_emoji")],
        [InlineKeyboardButton("📋  Мои паки",             callback_data="list_packs")],
    ]
    text = (
        "👋 <b>Что хочешь создать?</b>\n\n"
        "• <b>Стикер-пак</b> — обычные стикеры\n"
        "• <b>Эмодзи-пак</b> — premium emoji\n\n"
        "<i>Поддерживаются: фото, PNG, WEBP, WEBM, TGS, готовые стикеры TG</i>"
    )
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    return CHOOSE_TYPE


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    name = f"@{user.username}" if user.username else user.first_name
    kb   = [[InlineKeyboardButton("😎 Начать", callback_data="begin")]]
    await update.message.reply_text(
        f"Привет, {name}!\n\nСоздавай стикеры и premium emoji прямо в Telegram 🚀",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in (
        "new_pack_title", "new_pack_suffix", "new_pack_stickers",
        "creating_type", "selected_pack_index", "pending_data", "pending_fmt",
    ):
        context.user_data.pop(key, None)
    return await send_main_menu(update, context)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in (
        "new_pack_title", "new_pack_suffix", "new_pack_stickers",
        "creating_type", "selected_pack_index", "pending_data", "pending_fmt",
    ):
        context.user_data.pop(key, None)
    await update.message.reply_text(
        "❌ Создание пака отменено.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 В меню", callback_data="begin")]]
        ),
    )
    return ConversationHandler.END


async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_main_menu(update, context)


# ── Список паков ──────────────────────────────────────────────────────────────

async def list_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    packs   = get_packs(context, user_id)

    if not packs:
        await query.edit_message_text(
            "У тебя пока нет созданных паков.",
            reply_markup=InlineKeyboardMarkup([back_btn()]),
        )
        return CHOOSE_TYPE

    kb = []
    for i, p in enumerate(packs):
        icon = "🖼" if p["type"] == "sticker" else "✨"
        n    = p.get("count", 0)
        kb.append([InlineKeyboardButton(
            f"{icon} {p['title']} ({n} {plural_sticker(n)})",
            callback_data=f"select_pack_{i}",
        )])
    kb.append(back_btn())
    await query.edit_message_text(
        "📋 <b>Твои паки:</b>\n\nВыбери пак для управления.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


# ── Выбор пака ────────────────────────────────────────────────────────────────

async def select_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx  = int(query.data.replace("select_pack_", ""))
    context.user_data["selected_pack_index"] = idx
    user_id = update.effective_user.id
    pack = get_packs(context, user_id)[idx]
    icon = "🖼" if pack["type"] == "sticker" else "✨"
    n    = pack.get("count", 0)
    url  = pack_url(pack["name"])
    kb   = [
        [InlineKeyboardButton("🔗 Открыть пак",         url=url)],
        [InlineKeyboardButton("➕ Добавить стикер",      callback_data="mgmt_add")],
        [InlineKeyboardButton("🗑 Удалить стикер",       callback_data="mgmt_delete")],
        [InlineKeyboardButton("🖼 Сменить иконку пака",  callback_data="mgmt_icon")],
        [InlineKeyboardButton("❌ Удалить весь пак",     callback_data="mgmt_delete_all")],
        back_btn("◀️ К списку паков", "list_packs"),
    ]
    await query.edit_message_text(
        f"{icon} <b>{pack['title']}</b>\n"
        f"Стикеров: {n}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


# ── Создание пака: шаг 1 — тип ────────────────────────────────────────────────

async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query     = update.callback_query
    await query.answer()
    pack_type = "sticker" if query.data == "create_sticker" else "emoji"
    context.user_data["creating_type"] = pack_type
    word = "стикер-пак" if pack_type == "sticker" else "эмодзи-пак"
    await query.edit_message_text(
        f"📝 <b>Создание {word}</b>\n\nНапиши <b>название</b> набора:\n\n/cancel — отменить",
        parse_mode="HTML",
    )
    return PACK_NAME


# ── Создание пака: шаг 2 — название ──────────────────────────────────────────

async def receive_pack_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Название не может быть пустым:")
        return PACK_NAME
    context.user_data["new_pack_title"]    = title
    context.user_data["new_pack_stickers"] = []
    kb = [[InlineKeyboardButton("🎲 Случайная ссылка", callback_data="random_link")]]
    await update.message.reply_text(
        "🔗 <b>Придумай короткую ссылку</b>\n\n"
        "Только латиница, цифры и <code>_</code>.\n\n/cancel — отменить",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_LINK


# ── Создание пака: шаг 3 — ссылка ────────────────────────────────────────────

async def _prompt_first_sticker(update: Update, suffix: str) -> int:
    text = (
        f"✅ Ссылка: <code>{suffix}</code>\n\n"
        "Отправь первый стикер 👇\n"
        "<i>Поддерживаются: фото, PNG, WEBP, WEBM, TGS, готовые стикеры TG.</i>\n\n/cancel — отменить"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")
    return ADDING_STICKER


async def use_random_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    suffix = random_suffix()
    context.user_data["new_pack_suffix"] = suffix
    return await _prompt_first_sticker(update, suffix)


async def receive_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw    = update.message.text.strip()
    suffix = sanitize_suffix(raw)
    context.user_data["new_pack_suffix"] = suffix
    if suffix != raw.lower():
        await update.message.reply_text(
            f"ℹ️ Ссылка скорректирована: <code>{suffix}</code>",
            parse_mode="HTML",
        )
    return await _prompt_first_sticker(update, suffix)


# ── Создание пака: шаг 4 — файл(ы) ──────────────────────────────────────────

async def _ask_emoji_for_next(update_or_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Спрашивает эмодзи для следующего файла в очереди вручную."""
    queue = context.user_data.get("file_queue", [])
    done  = context.user_data.get("file_queue_done", 0)
    total = len(queue)
    msg   = update_or_msg.message if hasattr(update_or_msg, "message") else update_or_msg

    if done >= total:
        return await _finish_batch(update_or_msg, context)

    idx_label = f" {done + 1}/{total}" if total > 1 else ""
    await msg.reply_text(
        f"😊 <b>Укажи эмодзи</b> для стикера{idx_label}\n"
        "Можно несколько через пробел: <code>😎 🔥</code>\n\n/cancel — отменить",
        parse_mode="HTML",
    )
    return WAITING_EMOJI


async def _finish_batch(update_or_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    stickers_buf = context.user_data.get("new_pack_stickers", [])
    suffix       = context.user_data.get("new_pack_suffix") or random_suffix()
    bot_username = context.user_data.get("_bot_username", "")
    pack_name    = build_pack_name(bot_username, suffix)
    n            = len(stickers_buf)
    url          = pack_url(pack_name)
    title        = context.user_data.get("new_pack_title", "My Pack")

    kb = [
        [InlineKeyboardButton("🔗 Открыть пак",   url=url)],
        [InlineKeyboardButton("➕ Добавить ещё",  callback_data="add_more")],
        [InlineKeyboardButton("💾 Сохранить пак", callback_data="save_pack")],
    ]
    added = context.user_data.pop("file_queue_added", 0)
    text = (
        f"🎉 Пак создан!\n<b>{title}</b>\n\nДобавь ещё или сохрани 👇"
        if n == added
        else f"✅ Добавлено {added} {plural_sticker(added)}!\nВсего: {n} {plural_sticker(n)}\n\nПродолжай или сохрани 👇"
    )
    msg = update_or_msg.message if hasattr(update_or_msg, "message") else update_or_msg
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=True,
                         reply_markup=InlineKeyboardMarkup(kb))
    context.user_data.pop("file_queue", None)
    context.user_data.pop("file_queue_done", None)
    return ADDING_STICKER


async def receive_sticker_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pack_type = context.user_data.get("creating_type", "sticker")
    msg = update.message

    # Проверяем размер входного файла
    file_size = None
    if msg.document:    file_size = msg.document.file_size
    elif msg.photo:     file_size = msg.photo[-1].file_size
    elif msg.video:     file_size = msg.video.file_size
    elif msg.animation: file_size = msg.animation.file_size

    if file_size and file_size > MAX_INPUT_BYTES:
        size_mb = file_size / (1024 * 1024)
        await msg.reply_text(
            f"❌ Файл слишком большой ({size_mb:.1f} МБ).\n"
            "Максимальный размер — 10 МБ.\n\n"
            "Сожми изображение и отправь снова."
        )
        return ADDING_STICKER

    bot_me = await context.bot.get_me()
    context.user_data["_bot_username"] = bot_me.username
    context.user_data["_user_id"] = update.effective_user.id

    data, fmt = await get_sticker_data(context.bot, msg, pack_type)
    if data is None:
        await msg.reply_text(
            "❌ Не получилось распознать файл.\n"
            "Отправь фото или изображение в формате PNG, WEBP, WEBM или TGS."
        )
        return ADDING_STICKER

    queue = context.user_data.setdefault("file_queue", [])
    queue.append({"data": data, "fmt": fmt})

    if len(queue) == 1:
        context.user_data["file_queue_done"] = 0
        context.user_data["file_queue_added"] = 0
        return await _ask_emoji_for_next(update, context)

    await msg.reply_text(f"📥 Файл #{len(queue)} принят, обрабатываю.")
    return ADDING_STICKER


# ── Создание пака: шаг 5 — отправка в Telegram ───────────────────────────────

async def _push_sticker_to_tg(bot, user_id: int, pack_name: str, pack_type: str,
                                title: str, data, fmt, emoji_list: list,
                                stickers_buf: list):
    sticker_type  = StickerType.REGULAR if pack_type == "sticker" else StickerType.CUSTOM_EMOJI
    input_sticker = InputSticker(sticker=data, emoji_list=emoji_list[:20], format=fmt)

    if not stickers_buf:
        try:
            await bot.create_new_sticker_set(
                user_id=user_id, name=pack_name, title=title,
                stickers=[input_sticker], sticker_type=sticker_type,
            )
        except TelegramError as e:
            return _friendly_tg_error(str(e))
    else:
        try:
            await bot.add_sticker_to_set(user_id=user_id, name=pack_name, sticker=input_sticker)
        except TelegramError as e:
            return _friendly_tg_error(str(e))
    return None


async def add_more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Отправь следующий файл — фото, PNG, WEBP, WEBM или TGS 👇\n\n/cancel — отменить"
    )
    return ADDING_STICKER


# ── Сохранение пака ───────────────────────────────────────────────────────────

async def save_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query        = update.callback_query
    await query.answer()
    user_id      = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    title        = context.user_data.get("new_pack_title", "My Pack")
    suffix       = context.user_data.get("new_pack_suffix") or random_suffix()
    pack_type    = context.user_data.get("creating_type", "sticker")
    stickers     = context.user_data.get("new_pack_stickers", [])
    pack_name    = build_pack_name(bot_username, suffix)

    get_packs(context, user_id).append({
        "title": title, "name": pack_name, "suffix": suffix,
        "type": pack_type, "count": len(stickers),
    })
    for key in ("new_pack_title", "new_pack_suffix", "new_pack_stickers", "creating_type"):
        context.user_data.pop(key, None)

    url  = pack_url(pack_name)
    icon = "🖼" if pack_type == "sticker" else "✨"
    kb   = [
        [InlineKeyboardButton("🔗 Открыть пак", url=url)],
        [InlineKeyboardButton("🏠 В меню",      callback_data="begin")],
    ]
    await query.edit_message_text(
        f"{icon} <b>Пак сохранён!</b>\n\n"
        f"Название: <b>{title}</b>\n"
        f"Стикеров: {len(stickers)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ConversationHandler.END


# ── Управление: добавить стикер ───────────────────────────────────────────────

async def mgmt_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]
    word    = "стикер" if pack["type"] == "sticker" else "эмодзи"
    await query.edit_message_text(
        f"➕ Отправь <b>{word}</b> для пака <b>{pack['title']}</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([back_btn("◀️ Отмена", f"select_pack_{idx}")]),
    )
    return ADD_STICKER_FILE


async def receive_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id   = update.effective_user.id
    idx       = context.user_data.get("selected_pack_index", 0)
    pack      = get_packs(context, user_id)[idx]
    pack_type = pack["type"]
    msg       = update.message

    # Проверяем размер входного файла
    file_size = None
    if msg.document:    file_size = msg.document.file_size
    elif msg.photo:     file_size = msg.photo[-1].file_size
    elif msg.video:     file_size = msg.video.file_size
    elif msg.animation: file_size = msg.animation.file_size

    if file_size and file_size > MAX_INPUT_BYTES:
        size_mb = file_size / (1024 * 1024)
        await msg.reply_text(
            f"❌ Файл слишком большой ({size_mb:.1f} МБ).\n"
            "Максимальный размер — 10 МБ. Сожми и отправь снова."
        )
        return ADD_STICKER_FILE

    data, fmt = await get_sticker_data(context.bot, msg, pack_type)
    if data is None:
        await msg.reply_text(
            "❌ Не получилось распознать файл.\n"
            "Отправь фото или изображение в формате PNG, WEBP, WEBM или TGS."
        )
        return ADD_STICKER_FILE

    context.user_data["pending_data"] = data
    context.user_data["pending_fmt"]  = fmt
    await msg.reply_text(
        "😊 <b>Укажи эмодзи</b> для этого стикера.\n"
        "Можно несколько через пробел: <code>😎 🔥</code>",
        parse_mode="HTML",
    )
    return ADD_STICKER_EMOJI


# ── Управление: удалить стикер ────────────────────────────────────────────────

async def mgmt_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]
    try:
        tg_pack = await context.bot.get_sticker_set(pack["name"])
    except TelegramError as e:
        await query.answer(_friendly_tg_error(str(e)), show_alert=True)
        return PACK_SELECTED
    if not tg_pack.stickers:
        await query.answer("В паке нет стикеров.", show_alert=True)
        return PACK_SELECTED
    kb = []
    for i, s in enumerate(tg_pack.stickers[:50]):
        kb.append([InlineKeyboardButton(
            f"#{i+1} {s.emoji or '?'}",
            callback_data=f"del_sticker_{s.file_unique_id}",
        )])
    kb.append(back_btn("◀️ Отмена", f"select_pack_{idx}"))
    await query.edit_message_text("🗑 Выбери стикер для удаления:", reply_markup=InlineKeyboardMarkup(kb))
    return DELETE_STICKER


async def confirm_delete_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query          = update.callback_query
    await query.answer()
    user_id        = update.effective_user.id
    idx            = context.user_data.get("selected_pack_index", 0)
    pack           = get_packs(context, user_id)[idx]
    file_unique_id = query.data.replace("del_sticker_", "")
    try:
        tg_pack = await context.bot.get_sticker_set(pack["name"])
    except TelegramError as e:
        await query.answer(_friendly_tg_error(str(e)), show_alert=True)
        return PACK_SELECTED
    target = next((s for s in tg_pack.stickers if s.file_unique_id == file_unique_id), None)
    if not target:
        await query.answer("Стикер не найден.", show_alert=True)
        return DELETE_STICKER
    try:
        await context.bot.delete_sticker_from_set(target.file_id)
    except TelegramError as e:
        await query.answer(_friendly_tg_error(str(e)), show_alert=True)
        return DELETE_STICKER
    pack["count"] = max(0, pack.get("count", 1) - 1)
    await query.edit_message_text(
        f"✅ Стикер удалён. Осталось: {pack['count']} {plural_sticker(pack['count'])}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


# ── Управление: сменить иконку ────────────────────────────────────────────────

async def mgmt_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx   = context.user_data.get("selected_pack_index", 0)
    await query.edit_message_text(
        "🖼 <b>Сменить иконку пака</b>\n\nОтправь стикер из этого пака:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([back_btn("◀️ Отмена", f"select_pack_{idx}")]),
    )
    return CHANGE_ICON


async def receive_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg     = update.message
    user_id = update.effective_user.id
    idx     = context.user_data.get("selected_pack_index", 0)
    pack    = get_packs(context, user_id)[idx]
    if not msg.sticker:
        await msg.reply_text("Нужен стикер из этого пака. Попробуй ещё раз.")
        return CHANGE_ICON
    try:
        tg_file = await context.bot.get_file(msg.sticker.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        thumb_bytes = process_image_for_thumbnail(buf.getvalue())
    except Exception as e:
        await msg.reply_text(f"❌ Не удалось обработать изображение:\n{e}")
        return CHANGE_ICON
    try:
        await context.bot.set_sticker_set_thumbnail(
            name=pack["name"],
            user_id=user_id,
            thumbnail=thumb_bytes,
            format=msg.sticker.format if hasattr(msg.sticker, "format") else StickerFormat.STATIC,
        )
    except TelegramError as e:
        await msg.reply_text(f"❌ Не удалось обновить иконку:\n{_friendly_tg_error(str(e))}")
        return CHANGE_ICON
    await msg.reply_text(
        "✅ Иконка обновлена!",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]),
    )
    return PACK_SELECTED


# ── Управление: удалить весь пак ─────────────────────────────────────────────

async def mgmt_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx   = context.user_data.get("selected_pack_index", 0)
    await query.edit_message_text(
        "⚠️ <b>Удалить весь пак?</b>\n\nЭто действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_pack_{idx}")],
            back_btn("◀️ Отмена", f"select_pack_{idx}"),
        ]),
    )
    return PACK_SELECTED


async def confirm_delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx     = int(query.data.replace("confirm_delete_pack_", ""))
    packs   = get_packs(context, user_id)
    pack    = packs[idx]
    try:
        await context.bot.delete_sticker_set(pack["name"])
    except TelegramError as e:
        logger.warning("delete_sticker_set: %s", e)
    name = pack["title"]
    packs.pop(idx)
    context.user_data.pop("selected_pack_index", None)
    await query.edit_message_text(
        f"🗑 Пак <b>{name}</b> удалён.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([back_btn("📋 К списку паков", "list_packs")]),
    )
    return CHOOSE_TYPE


# ── Сборка ────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start",  start),
            CommandHandler("menu",   menu_command),
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(begin, pattern="^begin$"),
        ],
        states={
            MAIN_MENU: [CallbackQueryHandler(begin, pattern="^begin$")],
            CHOOSE_TYPE: [
                CallbackQueryHandler(begin,        pattern="^begin$"),
                CallbackQueryHandler(start_create, pattern="^create_(sticker|emoji)$"),
                CallbackQueryHandler(list_packs,   pattern="^list_packs$"),
            ],
            PACK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_name)],
            PACK_LINK: [
                CallbackQueryHandler(use_random_link, pattern="^random_link$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_link),
            ],
            ADDING_STICKER: [
                CallbackQueryHandler(save_pack, pattern="^save_pack$"),
                CallbackQueryHandler(add_more,  pattern="^add_more$"),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Sticker.ALL |
                    filters.ANIMATION | filters.Document.ALL,
                    receive_sticker_file,
                ),
            ],
            PACK_SELECTED: [
                CallbackQueryHandler(begin,                  pattern="^begin$"),
                CallbackQueryHandler(list_packs,             pattern="^list_packs$"),
                CallbackQueryHandler(select_pack,            pattern="^select_pack_\\d+$"),
                CallbackQueryHandler(mgmt_add,               pattern="^mgmt_add$"),
                CallbackQueryHandler(mgmt_delete,            pattern="^mgmt_delete$"),
                CallbackQueryHandler(confirm_delete_sticker, pattern="^del_sticker_.+$"),
                CallbackQueryHandler(mgmt_icon,              pattern="^mgmt_icon$"),
                CallbackQueryHandler(mgmt_delete_all,        pattern="^mgmt_delete_all$"),
                CallbackQueryHandler(confirm_delete_pack,    pattern="^confirm_delete_pack_\\d+$"),
            ],
            ADD_STICKER_FILE: [
                CallbackQueryHandler(select_pack, pattern="^select_pack_\\d+$"),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Sticker.ALL |
                    filters.ANIMATION | filters.Document.ALL,
                    receive_add_file,
                ),
            ],
            ADD_STICKER_EMOJI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_emoji),
            ],
            DELETE_STICKER: [
                CallbackQueryHandler(select_pack,            pattern="^select_pack_\\d+$"),
                CallbackQueryHandler(confirm_delete_sticker, pattern="^del_sticker_.+$"),
            ],
            CHANGE_ICON: [
                CallbackQueryHandler(select_pack, pattern="^select_pack_\\d+$"),
                MessageHandler(filters.Sticker.ALL, receive_icon),
            ],
        },
        fallbacks=[
            CommandHandler("start",  start),
            CommandHandler("menu",   menu_command),
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(begin, pattern="^begin$"),
        ],
        allow_reentry=True,
        per_message=False,
    )

    async def post_init(application):
        await application.bot.set_my_commands([
            ("start",  "👋 Приветствие"),
            ("menu",   "🏠 Главное меню"),
            ("cancel", "❌ Отменить создание пака"),
        ])

    app.post_init = post_init
    app.add_handler(conv)
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("menu",   menu_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(begin, pattern="^begin$"))
    logger.info("Бот запущен ✅")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
