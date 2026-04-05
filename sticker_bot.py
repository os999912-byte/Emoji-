"""
Telegram Sticker & Premium Emoji Pack Bot
==========================================
Создаёт НАСТОЯЩИЕ стикер-паки и эмодзи-паки через Bot API.

Токен берётся из переменной окружения BOT_TOKEN.
"""

import io
import logging
import os
import random
import string

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
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

# ──────────────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Состояния ConversationHandler
# ──────────────────────────────────────────────────────────────────────────────
(
    MAIN_MENU,
    CHOOSE_TYPE,
    PACK_NAME,
    PACK_LINK,
    ADDING_STICKER,
    WAITING_EMOJI,        # ждём эмодзи для последнего добавленного стикера
    PACK_SELECTED,
    PACK_MANAGEMENT,
    RENAME_PACK,
    ADD_STICKER_FILE,
    ADD_STICKER_EMOJI,
    DELETE_STICKER,
    CHANGE_ICON,
) = range(13)

# ──────────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────────

def random_suffix(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def build_pack_name(bot_username: str, suffix: str) -> str:
    """Имя набора в Telegram: <suffix>_by_<bot_username>"""
    return f"{suffix}_by_{bot_username}"


def plural_sticker(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return "стикеров"
    r = n % 10
    if r == 1:
        return "стикер"
    if 2 <= r <= 4:
        return "стикера"
    return "стикеров"


def pack_url(pack_name: str) -> str:
    return f"https://t.me/addstickers/{pack_name}"


def get_packs(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> list:
    return context.bot_data.setdefault(str(user_id), {}).setdefault("packs", [])


def back_btn(label: str = "◀️ Назад", data: str = "begin") -> list:
    return [InlineKeyboardButton(label, callback_data=data)]


# ──────────────────────────────────────────────────────────────────────────────
# Хелперы: получение файла для InputSticker
# ──────────────────────────────────────────────────────────────────────────────

async def resolve_input_file(bot, msg):
    """
    Возвращает (sticker_input, fmt) где sticker_input — file_id (для готовых
    стикеров TG) или InputFile (для всего остального, скачанного байтами).

    Telegram НЕ разрешает передавать file_id фото/видео/документов напрямую
    в InputSticker — нужно скачивать байты и загружать как файл.
    """
    # ── Готовый стикер из TG — его file_id принимается напрямую ──────────────
    if msg.sticker:
        s = msg.sticker
        fmt = s.format if hasattr(s, "format") else StickerFormat.STATIC
        return s.file_id, fmt

    # ── Документ (PNG/WEBP/WEBM/TGS отправленный без сжатия) ─────────────────
    if msg.document:
        d = msg.document
        mime = (d.mime_type or "").lower()
        name = (d.file_name or "").lower()
        if "webm" in mime or name.endswith(".webm"):
            fmt = StickerFormat.VIDEO
            ext = "webm"
        elif "tgs" in mime or name.endswith(".tgs"):
            fmt = StickerFormat.ANIMATED
            ext = "tgs"
        else:
            # PNG, WEBP, JPEG и любое другое изображение — пробуем STATIC
            fmt = StickerFormat.STATIC
            ext = "png"
        tg_file = await bot.get_file(d.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        buf.seek(0)
        return InputFile(buf, filename=f"sticker.{ext}"), fmt

    # ── Сжатое фото (msg.photo) ───────────────────────────────────────────────
    if msg.photo:
        tg_file = await bot.get_file(msg.photo[-1].file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        buf.seek(0)
        return InputFile(buf, filename="sticker.png"), StickerFormat.STATIC

    # ── Видео ─────────────────────────────────────────────────────────────────
    if msg.video:
        tg_file = await bot.get_file(msg.video.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        buf.seek(0)
        return InputFile(buf, filename="sticker.webm"), StickerFormat.VIDEO

    # ── GIF / анимация ────────────────────────────────────────────────────────
    if msg.animation:
        tg_file = await bot.get_file(msg.animation.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        buf.seek(0)
        return InputFile(buf, filename="sticker.webm"), StickerFormat.VIDEO

    return None, None


# ──────────────────────────────────────────────────────────────────────────────
# Главное меню
# ──────────────────────────────────────────────────────────────────────────────

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [
        [InlineKeyboardButton("🖼  Создать стикер-пак",     callback_data="create_sticker")],
        [InlineKeyboardButton("✨  Создать эмодзи-пак",      callback_data="create_emoji")],
        [InlineKeyboardButton("📋  Мои паки",               callback_data="list_packs")],
    ]
    text = (
        "👋 <b>Что хочешь создать?</b>\n\n"
        "• <b>Стикер-пак</b> — обычные стикеры\n"
        "• <b>Эмодзи-пак</b> — premium emoji\n\n"
        "<i>Поддерживаются: PNG, WEBP, WEBM (видео), TGS (анимация), фото</i>"
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
    kb = [[InlineKeyboardButton("😎 Начать", callback_data="begin")]]
    await update.message.reply_text(
        f"Привет, {name}!\n\nЯ создаю <b>настоящие</b> стикер-паки и premium emoji прямо в Telegram 🚀",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in (
        "new_pack_name", "new_pack_link", "new_pack_stickers",
        "creating_type", "selected_pack_index", "pending_file",
        "pending_fmt",
    ):
        context.user_data.pop(key, None)
    return await send_main_menu(update, context)


async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_main_menu(update, context)


# ──────────────────────────────────────────────────────────────────────────────
# Список паков
# ──────────────────────────────────────────────────────────────────────────────

async def list_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    packs = get_packs(context, user_id)

    if not packs:
        await query.edit_message_text(
            "У тебя пока нет созданных паков.",
            reply_markup=InlineKeyboardMarkup([back_btn()]),
        )
        return CHOOSE_TYPE

    kb = []
    for i, p in enumerate(packs):
        icon = "🖼" if p["type"] == "sticker" else "✨"
        n = p.get("count", 0)
        label = f"{icon} {p['title']} ({n} {plural_sticker(n)})"
        kb.append([InlineKeyboardButton(label, callback_data=f"select_pack_{i}")])
    kb.append(back_btn())

    await query.edit_message_text(
        "📋 <b>Твои паки:</b>\n\nВыбери пак для управления.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


# ──────────────────────────────────────────────────────────────────────────────
# Выбор / управление паком
# ──────────────────────────────────────────────────────────────────────────────

async def select_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.replace("select_pack_", ""))
    context.user_data["selected_pack_index"] = idx
    user_id = update.effective_user.id
    pack = get_packs(context, user_id)[idx]
    icon = "🖼" if pack["type"] == "sticker" else "✨"
    n = pack.get("count", 0)

    kb = [
        [InlineKeyboardButton("🔗 Открыть в Telegram",   callback_data="open_tg_link")],
        [InlineKeyboardButton("➕ Добавить стикер",       callback_data="mgmt_add")],
        [InlineKeyboardButton("🗑 Удалить стикер",        callback_data="mgmt_delete")],
        [InlineKeyboardButton("🖼 Сменить иконку пака",   callback_data="mgmt_icon")],
        [InlineKeyboardButton("❌ Удалить весь пак",      callback_data="mgmt_delete_all")],
        back_btn("◀️ К списку паков", "list_packs"),
    ]
    await query.edit_message_text(
        f"{icon} <b>{pack['title']}</b>\n"
        f"Стикеров: {n}\n"
        f"Ссылка: <a href='{pack_url(pack['name'])}'>{pack_url(pack['name'])}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


async def open_tg_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    url = pack_url(pack["name"])
    await query.answer(url, show_alert=True)
    return PACK_SELECTED


# ──────────────────────────────────────────────────────────────────────────────
# Создание нового пака — шаг 1: тип
# ──────────────────────────────────────────────────────────────────────────────

async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    pack_type = "sticker" if query.data == "create_sticker" else "emoji"
    context.user_data["creating_type"] = pack_type

    word = "стикер-пак" if pack_type == "sticker" else "эмодзи-пак"
    await query.edit_message_text(
        f"📝 <b>Создание {word}</b>\n\nНапиши <b>название</b> набора (можно на русском):",
        parse_mode="HTML",
    )
    return PACK_NAME

async def receive_pack_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Название не может быть пустым. Попробуй ещё раз:")
        return PACK_NAME

    context.user_data["new_pack_title"] = title
    context.user_data["new_pack_stickers"] = []

    kb = [[InlineKeyboardButton("🎲 Случайная ссылка", callback_data="random_link")]]
    await update.message.reply_text(
        "🔗 <b>Придумай короткую ссылку</b> на пак\n\n"
        "Только латиница, цифры и <code>_</code>, от 5 до 64 символов.\n"
        "Итоговая ссылка: <code>t.me/addstickers/ССЫЛКА_by_botname</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_LINK


# ──────────────────────────────────────────────────────────────────────────────
# Создание нового пака — шаг 3: ссылка
# ──────────────────────────────────────────────────────────────────────────────

async def _prompt_add_first_sticker(
    update: Update, context: ContextTypes.DEFAULT_TYPE, suffix: str
) -> int:
    text = (
        f"✅ Ссылка: <code>{suffix}</code>\n\n"
        "Теперь добавь первый стикер!\n"
        "Отправь <b>фото, PNG, WEBP, WEBM-видео или TGS</b> 👇\n\n"
        "<i>После отправки файла я попрошу указать эмодзи для него.</i>"
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
    return await _prompt_add_first_sticker(update, context, suffix)


async def receive_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    suffix = update.message.text.strip()
    clean = suffix.replace("_", "")
    if not clean.isalnum() or not (5 <= len(suffix) <= 64):
        await update.message.reply_text(
            "❌ Только латиница, цифры и <code>_</code>, от 5 до 64 символов. Попробуй ещё раз:",
            parse_mode="HTML",
        )
        return PACK_LINK
    context.user_data["new_pack_suffix"] = suffix
    return await _prompt_add_first_sticker(update, context, suffix)


# ──────────────────────────────────────────────────────────────────────────────
# Создание нового пака — шаг 4: получаем файл
# ──────────────────────────────────────────────────────────────────────────────

async def receive_sticker_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    sticker_input, fmt = await resolve_input_file(context.bot, msg)

    if not sticker_input:
        await msg.reply_text(
            "❌ Не могу распознать файл. Отправь фото, PNG, WEBP, WEBM или TGS."
        )
        return ADDING_STICKER

    context.user_data["pending_file"] = sticker_input
    context.user_data["pending_fmt"] = fmt

    await msg.reply_text(
        "😊 <b>Укажи эмодзи</b> для этого стикера.\n"
        "Можно несколько через пробел, например: <code>😎 🔥</code>",
        parse_mode="HTML",
    )
    return WAITING_EMOJI


# ──────────────────────────────────────────────────────────────────────────────
# Создание нового пака — шаг 5: получаем эмодзи, создаём / пополняем пак
# ──────────────────────────────────────────────────────────────────────────────

async def receive_sticker_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    emoji_list = update.message.text.strip().split()
    if not emoji_list:
        await update.message.reply_text("Напиши хотя бы один эмодзи:")
        return WAITING_EMOJI

    sticker_input = context.user_data.pop("pending_file", None)
    fmt = context.user_data.pop("pending_fmt", StickerFormat.STATIC)

    if not sticker_input:
        await update.message.reply_text("Что-то пошло не так. Отправь стикер заново.")
        return ADDING_STICKER

    user_id = update.effective_user.id
    bot = context.bot
    bot_me = await bot.get_me()
    bot_username = bot_me.username

    pack_type = context.user_data.get("creating_type", "sticker")
    suffix = context.user_data.get("new_pack_suffix", random_suffix())
    title = context.user_data.get("new_pack_title", "My Pack")
    sticker_type = StickerType.REGULAR if pack_type == "sticker" else StickerType.CUSTOM_EMOJI

    stickers_buf: list = context.user_data.setdefault("new_pack_stickers", [])
    pack_name = build_pack_name(bot_username, suffix)

    input_sticker = InputSticker(
        sticker=sticker_input,
        emoji_list=emoji_list[:20],
        format=fmt,
    )

    # Первый стикер → createNewStickerSet
    if not stickers_buf:
        try:
            await bot.create_new_sticker_set(
                user_id=user_id,
                name=pack_name,
                title=title,
                stickers=[input_sticker],
                sticker_type=sticker_type,
            )
        except TelegramError as e:
            logger.error("create_new_sticker_set: %s", e)
            await update.message.reply_text(
                f"❌ <b>Ошибка создания пака:</b>\n<code>{e}</code>\n\n"
                "Попробуй отправить файл как документ (скрепка → файл), "
                "либо используй PNG/WEBP изображение.",
                parse_mode="HTML",
            )
            return ADDING_STICKER

        stickers_buf.append({"fmt": str(fmt), "emojis": emoji_list})
        n = len(stickers_buf)
        url = pack_url(pack_name)
        kb = [
            [InlineKeyboardButton("➕ Добавить ещё",  callback_data="add_more")],
            [InlineKeyboardButton("💾 Сохранить пак", callback_data="save_pack")],
            [InlineKeyboardButton("🔗 Открыть в TG",  url=url)],
        ]
        await update.message.reply_text(
            f"🎉 Пак создан!\n"
            f"<b>{title}</b> — {n} {plural_sticker(n)}\n\n"
            f"<a href='{url}'>{url}</a>\n\n"
            f"Добавь ещё стикеры или сохрани пак 👇",
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return ADDING_STICKER

    # Последующие стикеры → addStickerToSet
    try:
        await bot.add_sticker_to_set(
            user_id=user_id,
            name=pack_name,
            sticker=input_sticker,
        )
    except TelegramError as e:
        logger.error("add_sticker_to_set: %s", e)
        await update.message.reply_text(
            f"❌ <b>Ошибка добавления:</b>\n<code>{e}</code>",
            parse_mode="HTML",
        )
        return ADDING_STICKER

    stickers_buf.append({"fmt": str(fmt), "emojis": emoji_list})
    n = len(stickers_buf)
    url = pack_url(pack_name)
    kb = [
        [InlineKeyboardButton("➕ Добавить ещё",  callback_data="add_more")],
        [InlineKeyboardButton("💾 Сохранить пак", callback_data="save_pack")],
        [InlineKeyboardButton("🔗 Открыть в TG",  url=url)],
    ]
    await update.message.reply_text(
        f"✅ Стикер #{n} добавлен в <b>{title}</b>.\n"
        f"Всего: {n} {plural_sticker(n)}\n\n"
        f"Продолжай отправлять или сохрани 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ADDING_STICKER


async def add_more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Кнопка «Добавить ещё» во время создания."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Отправь следующий файл — <b>фото, PNG, WEBP, WEBM или TGS</b> 👇",
        parse_mode="HTML",
    )
    return ADDING_STICKER


# ──────────────────────────────────────────────────────────────────────────────
# Сохранение пака в список
# ──────────────────────────────────────────────────────────────────────────────

async def save_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username

    title = context.user_data.get("new_pack_title", "My Pack")
    suffix = context.user_data.get("new_pack_suffix", random_suffix())
    pack_type = context.user_data.get("creating_type", "sticker")
    stickers = context.user_data.get("new_pack_stickers", [])
    pack_name = build_pack_name(bot_username, suffix)

    pack = {
        "title": title,
        "name": pack_name,          # реальное имя в Telegram
        "suffix": suffix,
        "type": pack_type,
        "count": len(stickers),
    }
    get_packs(context, user_id).append(pack)

    for key in ("new_pack_title", "new_pack_suffix", "new_pack_stickers", "creating_type"):
        context.user_data.pop(key, None)

    url = pack_url(pack_name)
    icon = "🖼" if pack_type == "sticker" else "✨"
    kb = [
        [InlineKeyboardButton("🔗 Открыть пак",  url=url)],
        [InlineKeyboardButton("🏠 В меню",        callback_data="begin")],
    ]
    await query.edit_message_text(
        f"{icon} <b>Пак сохранён!</b>\n\n"
        f"Название: <b>{title}</b>\n"
        f"Стикеров: {len(stickers)}\n"
        f"Ссылка: <a href='{url}'>{url}</a>",
        parse_mode="HTML",
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────────────────────────
# Управление существующим паком — добавить стикер
# ──────────────────────────────────────────────────────────────────────────────

async def mgmt_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    word = "стикер" if pack["type"] == "sticker" else "эмодзи"
    kb = [back_btn("◀️ Отмена", f"select_pack_{idx}")]
    await query.edit_message_text(
        f"➕ Отправь <b>{word}</b> для добавления в пак <b>{pack['title']}</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ADD_STICKER_FILE


async def receive_add_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    sticker_input, fmt = await resolve_input_file(context.bot, msg)

    if not sticker_input:
        await msg.reply_text("❌ Не могу распознать файл. Отправь фото, PNG, WEBP, WEBM или TGS.")
        return ADD_STICKER_FILE

    context.user_data["pending_file"] = sticker_input
    context.user_data["pending_fmt"] = fmt
    await msg.reply_text(
        "😊 Укажи <b>эмодзи</b> для этого стикера (через пробел):",
        parse_mode="HTML",
    )
    return ADD_STICKER_EMOJI


async def receive_add_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    emoji_list = update.message.text.strip().split()
    if not emoji_list:
        await update.message.reply_text("Напиши хотя бы один эмодзи:")
        return ADD_STICKER_EMOJI

    sticker_input = context.user_data.pop("pending_file", None)
    fmt = context.user_data.pop("pending_fmt", StickerFormat.STATIC)
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]

    input_sticker = InputSticker(sticker=sticker_input, emoji_list=emoji_list[:20], format=fmt)
    try:
        await context.bot.add_sticker_to_set(
            user_id=user_id,
            name=pack["name"],
            sticker=input_sticker,
        )
    except TelegramError as e:
        logger.error("add_sticker_to_set (mgmt): %s", e)
        await update.message.reply_text(
            f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML"
        )
        return ADD_STICKER_FILE

    pack["count"] = pack.get("count", 0) + 1
    kb = [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]
    await update.message.reply_text(
        f"✅ Стикер добавлен! Теперь в паке: {pack['count']} {plural_sticker(pack['count'])}",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


# ──────────────────────────────────────────────────────────────────────────────
# Управление паком — удалить стикер
# ──────────────────────────────────────────────────────────────────────────────

async def mgmt_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]

    try:
        tg_pack = await context.bot.get_sticker_set(pack["name"])
    except TelegramError as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return PACK_SELECTED

    if not tg_pack.stickers:
        await query.answer("В паке нет стикеров.", show_alert=True)
        return PACK_SELECTED

    kb = []
    for i, s in enumerate(tg_pack.stickers[:50]):  # показываем до 50
        emojis = "".join(s.emoji) if s.emoji else "?"
        kb.append([InlineKeyboardButton(f"#{i+1} {emojis}", callback_data=f"del_sticker_{s.file_unique_id}")])
    kb.append(back_btn("◀️ Отмена", f"select_pack_{idx}"))

    await query.edit_message_text(
        "🗑 Выбери стикер для удаления:",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return DELETE_STICKER


async def confirm_delete_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    file_unique_id = query.data.replace("del_sticker_", "")

    # Нужен file_id — получаем из пака
    try:
        tg_pack = await context.bot.get_sticker_set(pack["name"])
    except TelegramError as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return PACK_SELECTED

    target = next((s for s in tg_pack.stickers if s.file_unique_id == file_unique_id), None)
    if not target:
        await query.answer("Стикер не найден.", show_alert=True)
        return DELETE_STICKER

    try:
        await context.bot.delete_sticker_from_set(target.file_id)
    except TelegramError as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return DELETE_STICKER

    pack["count"] = max(0, pack.get("count", 1) - 1)
    kb = [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]
    await query.edit_message_text(
        f"✅ Стикер удалён. Осталось: {pack['count']} {plural_sticker(pack['count'])}",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


# ──────────────────────────────────────────────────────────────────────────────
# Управление паком — сменить иконку
# ──────────────────────────────────────────────────────────────────────────────

async def mgmt_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = context.user_data.get("selected_pack_index", 0)
    kb = [back_btn("◀️ Отмена", f"select_pack_{idx}")]
    await query.edit_message_text(
        "🖼 <b>Сменить иконку пака</b>\n\n"
        "Отправь <b>стикер из этого пака</b> — он станет иконкой:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return CHANGE_ICON


async def receive_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]

    if not msg.sticker:
        await msg.reply_text("Нужен именно стикер (не фото, не файл). Попробуй ещё раз.")
        return CHANGE_ICON

    try:
        await context.bot.set_sticker_set_thumbnail(
            name=pack["name"],
            user_id=user_id,
            thumbnail=msg.sticker.file_id,
            format=msg.sticker.format if hasattr(msg.sticker, "format") else StickerFormat.STATIC,
        )
    except TelegramError as e:
        await msg.reply_text(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")
        return CHANGE_ICON

    kb = [[InlineKeyboardButton("⚙️ К паку", callback_data=f"select_pack_{idx}")]]
    await msg.reply_text("✅ Иконка пака обновлена!", reply_markup=InlineKeyboardMarkup(kb))
    return PACK_SELECTED


# ──────────────────────────────────────────────────────────────────────────────
# Управление паком — удалить весь пак
# ──────────────────────────────────────────────────────────────────────────────

async def mgmt_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = context.user_data.get("selected_pack_index", 0)
    kb = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_pack_{idx}")],
        back_btn("◀️ Отмена", f"select_pack_{idx}"),
    ]
    await query.edit_message_text(
        "⚠️ <b>Удалить весь пак?</b>\n\nЭто действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return PACK_SELECTED


async def confirm_delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = int(query.data.replace("confirm_delete_pack_", ""))
    packs = get_packs(context, user_id)
    pack = packs[idx]

    try:
        await context.bot.delete_sticker_set(pack["name"])
    except TelegramError as e:
        logger.warning("delete_sticker_set: %s", e)
        # Продолжаем — убираем из нашего списка даже если TG вернул ошибку

    name = pack["title"]
    packs.pop(idx)
    context.user_data.pop("selected_pack_index", None)

    kb = [back_btn("📋 К списку паков", "list_packs")]
    await query.edit_message_text(
        f"🗑 Пак <b>{name}</b> удалён.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return CHOOSE_TYPE


# ──────────────────────────────────────────────────────────────────────────────
# Сборка приложения
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("menu", menu_command),
        ],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(begin, pattern="^begin$"),
            ],
            CHOOSE_TYPE: [
                CallbackQueryHandler(begin,        pattern="^begin$"),
                CallbackQueryHandler(start_create, pattern="^create_(sticker|emoji)$"),
                CallbackQueryHandler(list_packs,   pattern="^list_packs$"),
            ],
            PACK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_name),
            ],
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
            WAITING_EMOJI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_sticker_emoji),
            ],
            PACK_SELECTED: [
                CallbackQueryHandler(begin,               pattern="^begin$"),
                CallbackQueryHandler(list_packs,          pattern="^list_packs$"),
                CallbackQueryHandler(select_pack,         pattern="^select_pack_\\d+$"),
                CallbackQueryHandler(open_tg_link,        pattern="^open_tg_link$"),
                CallbackQueryHandler(mgmt_add,            pattern="^mgmt_add$"),
                CallbackQueryHandler(mgmt_delete,         pattern="^mgmt_delete$"),
                CallbackQueryHandler(confirm_delete_sticker, pattern="^del_sticker_.+$"),
                CallbackQueryHandler(mgmt_icon,           pattern="^mgmt_icon$"),
                CallbackQueryHandler(mgmt_delete_all,     pattern="^mgmt_delete_all$"),
                CallbackQueryHandler(confirm_delete_pack, pattern="^confirm_delete_pack_\\d+$"),
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
            CommandHandler("start", start),
            CommandHandler("menu",  menu_command),
        ],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(conv)
    logger.info("Бот запущен ✅")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
