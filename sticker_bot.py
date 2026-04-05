import logging
import random
import string
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ─── Токен ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Состояния ────────────────────────────────────────────────────────────────
(
    MAIN_MENU,
    CHOOSE_TYPE,
    PACK_NAME,
    PACK_LINK,
    ADDING_STICKER,
    PACK_SELECTED,
    PACK_MANAGEMENT,
    RENAME_PACK,
    ADD_TO_EXISTING,
    DELETE_STICKER,
    CHANGE_ICON,
    CHANGE_EMOJI,
) = range(12)


# ─── Вспомогательные функции ──────────────────────────────────────────────────
def random_link(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def get_packs(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> list:
    return context.bot_data.setdefault(user_id, {}).setdefault("packs", [])


def plural_sticker(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return "стикеров"
    r = n % 10
    if r == 1:
        return "стикер"
    if 2 <= r <= 4:
        return "стикера"
    return "стикеров"


def pack_icon(pack_type: str) -> str:
    return "🖼" if pack_type == "sticker" else "✨"


def _extract_file(msg) -> tuple:
    if msg.sticker:
        return msg.sticker.file_id, "sticker"
    if msg.photo:
        return msg.photo[-1].file_id, "photo"
    if msg.video:
        return msg.video.file_id, "video"
    if msg.animation:
        return msg.animation.file_id, "gif"
    if msg.document:
        return msg.document.file_id, "document"
    return None, None


# ─── Главное меню ─────────────────────────────────────────────────────────────
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🖼 Создать стикер-пак",      callback_data="create_sticker")],
        [InlineKeyboardButton("✨ Создать эмодзи-пак",       callback_data="create_emoji")],
        [InlineKeyboardButton("📋 Список созданных паков",   callback_data="list_packs")],
    ]
    text = "Что ты хочешь создать?"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.effective_message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return CHOOSE_TYPE


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    name = f"@{user.username}" if user.username else user.first_name
    keyboard = [[InlineKeyboardButton("😎 Начать", callback_data="begin")]]
    await update.message.reply_text(
        f"Привет, {name}!\n\nСоздавай свои стикеры и премиум эмодзи!",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in ("new_pack_name", "new_pack_link", "new_pack_stickers",
                "creating_type", "selected_pack_index", "mgmt_action"):
        context.user_data.pop(key, None)
    return await send_main_menu(update, context)


async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_main_menu(update, context)


# ─── Список паков ─────────────────────────────────────────────────────────────
async def list_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    packs = get_packs(context, user_id)

    if not packs:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="begin")]]
        await query.edit_message_text(
            "У тебя пока нет созданных паков.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CHOOSE_TYPE

    keyboard = []
    for i, p in enumerate(packs):
        label = f"{pack_icon(p['type'])} {p['name']} ({len(p['stickers'])} шт.)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"select_pack_{i}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="begin")])

    await query.edit_message_text(
        "📋 Список созданных паков:\n\nВыбери пак, который хочешь изменить",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_SELECTED


# ─── Выбор пака ───────────────────────────────────────────────────────────────
async def select_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.replace("select_pack_", ""))
    context.user_data["selected_pack_index"] = idx
    user_id = update.effective_user.id
    pack = get_packs(context, user_id)[idx]

    keyboard = [
        [InlineKeyboardButton("📂 Открыть пак",         callback_data="open_pack")],
        [InlineKeyboardButton("⚙️ Управление набором",  callback_data="manage_pack")],
        [InlineKeyboardButton("◀️ Назад",               callback_data="list_packs")],
    ]
    await query.edit_message_text(
        f"{pack_icon(pack['type'])} <b>{pack['name']}</b>\n"
        f"Стикеров: {len(pack['stickers'])}\n\nПак выбран",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_SELECTED


async def open_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]

    if not pack["stickers"]:
        await query.answer("В паке пока нет стикеров.", show_alert=True)
        return PACK_SELECTED

    await query.edit_message_text(f"📂 Открываю пак <b>{pack['name']}</b>...", parse_mode="HTML")

    for item in pack["stickers"]:
        try:
            fid, t = item["file_id"], item["type"]
            if t == "sticker":   await context.bot.send_sticker(user_id, fid)
            elif t == "photo":   await context.bot.send_photo(user_id, fid)
            elif t == "video":   await context.bot.send_video(user_id, fid)
            elif t == "gif":     await context.bot.send_animation(user_id, fid)
            else:                await context.bot.send_document(user_id, fid)
        except Exception as e:
            logger.warning(f"open_pack error: {e}")

    keyboard = [[InlineKeyboardButton("◀️ К паку", callback_data=f"select_pack_{idx}")]]
    await context.bot.send_message(
        user_id,
        f"✅ Показаны все {len(pack['stickers'])} {plural_sticker(len(pack['stickers']))}.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_SELECTED


# ─── Управление набором ───────────────────────────────────────────────────────
async def manage_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    is_sticker = pack["type"] == "sticker"

    keyboard = [
        [InlineKeyboardButton("➕ Добавить стикер" if is_sticker else "➕ Добавить эмодзи",
                              callback_data="mgmt_add")],
        [InlineKeyboardButton("🗑 Удалить стикер" if is_sticker else "🗑 Удалить эмодзи",
                              callback_data="mgmt_delete")],
        [InlineKeyboardButton("✏️ Переименовать пак",           callback_data="mgmt_rename")],
        [InlineKeyboardButton("🔗 Изменить ссылку",             callback_data="mgmt_link")],
        [InlineKeyboardButton("😀 Заменить привязанные смайлики", callback_data="mgmt_emoji")],
        [InlineKeyboardButton("🖼 Поменять иконку пака",        callback_data="mgmt_icon")],
        [InlineKeyboardButton("❌ Удалить весь пак",            callback_data="mgmt_delete_all")],
        [InlineKeyboardButton("◀️ Назад",                      callback_data=f"select_pack_{idx}")],
    ]
    await query.edit_message_text(
        "⚙️ <b>Управление набором</b>\n\nВыбери действие ниже:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_MANAGEMENT


# ── Добавить в существующий пак ───────────────────────────────────────────────
async def mgmt_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    word = "стикер" if pack["type"] == "sticker" else "эмодзи"

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="manage_pack")]]
    await query.edit_message_text(
        f"➕ Отправь {word} (фото / видео / стикер / гифку) для пака <b>{pack['name']}</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADD_TO_EXISTING


async def receive_add_to_existing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    file_id, media_type = _extract_file(msg)

    if not file_id:
        await msg.reply_text("Пожалуйста, отправь фото, видео, стикер или гифку.")
        return ADD_TO_EXISTING

    pack["stickers"].append({"file_id": file_id, "type": media_type})
    n = len(pack["stickers"])
    keyboard = [[InlineKeyboardButton("⚙️ К управлению", callback_data="manage_pack")]]
    await msg.reply_text(
        f"✅ Добавлено! Теперь в паке <b>{pack['name']}</b>: {n} {plural_sticker(n)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_MANAGEMENT


# ── Удалить стикер из пака ────────────────────────────────────────────────────
async def mgmt_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]

    if not pack["stickers"]:
        await query.answer("В паке нет стикеров.", show_alert=True)
        return PACK_MANAGEMENT

    keyboard = []
    for i, s in enumerate(pack["stickers"]):
        keyboard.append([InlineKeyboardButton(f"#{i+1} {s['type']}", callback_data=f"del_sticker_{i}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_pack")])
    await query.edit_message_text(
        "🗑 Выбери стикер для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return DELETE_STICKER


async def confirm_delete_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    sticker_idx = int(query.data.replace("del_sticker_", ""))
    pack["stickers"].pop(sticker_idx)

    keyboard = [[InlineKeyboardButton("⚙️ К управлению", callback_data="manage_pack")]]
    await query.edit_message_text(
        f"✅ Стикер #{sticker_idx+1} удалён. Осталось: {len(pack['stickers'])} {plural_sticker(len(pack['stickers']))}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_MANAGEMENT


# ── Переименовать ─────────────────────────────────────────────────────────────
async def mgmt_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["mgmt_action"] = "rename"
    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="manage_pack")]]
    await query.edit_message_text(
        "✏️ <b>Переименовать пак</b>\n\nНапиши новое название пака:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return RENAME_PACK


# ── Изменить ссылку ───────────────────────────────────────────────────────────
async def mgmt_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["mgmt_action"] = "link"
    keyboard = [
        [InlineKeyboardButton("🎲 Сгенерировать случайную", callback_data="mgmt_link_random")],
        [InlineKeyboardButton("◀️ Отмена", callback_data="manage_pack")],
    ]
    await query.edit_message_text(
        "🔗 <b>Изменить ссылку</b>\n\nНапиши новую короткую ссылку (буквы и цифры):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return RENAME_PACK


async def mgmt_link_random(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    pack["link"] = random_link()
    keyboard = [[InlineKeyboardButton("⚙️ К управлению", callback_data="manage_pack")]]
    await query.edit_message_text(
        f"✅ Новая ссылка: <code>{pack['link']}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_MANAGEMENT


async def receive_rename_or_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    action = context.user_data.get("mgmt_action", "rename")
    new_val = update.message.text.strip()

    if action == "link":
        if not new_val.replace("_", "").isalnum():
            await update.message.reply_text("❌ Только буквы, цифры и _. Попробуй ещё раз:")
            return RENAME_PACK
        pack["link"] = new_val
        text = f"✅ Ссылка изменена: <code>{new_val}</code>"
    else:
        old = pack["name"]
        pack["name"] = new_val
        text = f"✅ Переименовано: <b>{old}</b> → <b>{new_val}</b>"

    keyboard = [[InlineKeyboardButton("⚙️ К управлению", callback_data="manage_pack")]]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return PACK_MANAGEMENT


# ── Привязанные смайлики ──────────────────────────────────────────────────────
async def mgmt_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="manage_pack")]]
    await query.edit_message_text(
        "😀 <b>Заменить привязанные смайлики</b>\n\n"
        "Отправь эмодзи через пробел, например: 😎 🔥 ❤️",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHANGE_EMOJI


async def receive_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    pack["emojis"] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("⚙️ К управлению", callback_data="manage_pack")]]
    await update.message.reply_text(
        f"✅ Смайлики обновлены: {pack['emojis']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_MANAGEMENT


# ── Иконка пака ───────────────────────────────────────────────────────────────
async def mgmt_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="manage_pack")]]
    await query.edit_message_text(
        "🖼 <b>Поменять иконку пака</b>\n\n"
        "Отправь стикер из набора, который будет отображаться как иконка:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHANGE_ICON


async def receive_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    user_id = update.effective_user.id
    idx = context.user_data.get("selected_pack_index", 0)
    pack = get_packs(context, user_id)[idx]
    file_id, _ = _extract_file(msg)

    if not file_id:
        await msg.reply_text("Пожалуйста, отправь стикер, фото или гифку.")
        return CHANGE_ICON

    pack["icon_file_id"] = file_id
    keyboard = [[InlineKeyboardButton("⚙️ К управлению", callback_data="manage_pack")]]
    await msg.reply_text("✅ Иконка пака обновлена!", reply_markup=InlineKeyboardMarkup(keyboard))
    return PACK_MANAGEMENT


# ── Удалить весь пак ──────────────────────────────────────────────────────────
async def mgmt_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = context.user_data.get("selected_pack_index", 0)
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить",  callback_data=f"confirm_delete_pack_{idx}")],
        [InlineKeyboardButton("◀️ Отмена",       callback_data="manage_pack")],
    ]
    await query.edit_message_text(
        "⚠️ Ты уверен? Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_MANAGEMENT


async def confirm_delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    idx = int(query.data.replace("confirm_delete_pack_", ""))
    packs = get_packs(context, user_id)
    name = packs[idx]["name"]
    packs.pop(idx)
    context.user_data.pop("selected_pack_index", None)

    keyboard = [[InlineKeyboardButton("📋 К списку паков", callback_data="list_packs")]]
    await query.edit_message_text(
        f"🗑 Пак <b>{name}</b> удалён.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSE_TYPE


# ─── Создание нового пака ─────────────────────────────────────────────────────
async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["creating_type"] = "sticker" if query.data == "create_sticker" else "emoji"
    await query.edit_message_text("Напиши название своего набора:")
    return PACK_NAME


async def receive_pack_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_pack_name"] = update.message.text.strip()
    context.user_data["new_pack_stickers"] = []
    keyboard = [[InlineKeyboardButton("🎲 Пропустить (случайная ссылка)", callback_data="random_link")]]
    await update.message.reply_text(
        "Придумай короткую ссылку на пак (английские буквы, цифры, без пробелов):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PACK_LINK


async def use_random_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    link = random_link()
    context.user_data["new_pack_link"] = link
    await query.edit_message_text(
        f"Ссылка: <code>{link}</code>\n\nТеперь отправь мне фото / видео / стикер / гифку для пака 👇",
        parse_mode="HTML",
    )
    return ADDING_STICKER


async def receive_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    link = update.message.text.strip()
    if not link.replace("_", "").isalnum():
        await update.message.reply_text("❌ Только буквы, цифры и _. Попробуй ещё раз:")
        return PACK_LINK
    context.user_data["new_pack_link"] = link
    await update.message.reply_text(
        f"Ссылка: <code>{link}</code>\n\nТеперь отправь мне фото / видео / стикер / гифку для пака 👇",
        parse_mode="HTML",
    )
    return ADDING_STICKER


async def receive_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    file_id, media_type = _extract_file(msg)

    if not file_id:
        await msg.reply_text("Пожалуйста, отправь фото, видео, стикер или гифку.")
        return ADDING_STICKER

    context.user_data.setdefault("new_pack_stickers", []).append(
        {"file_id": file_id, "type": media_type}
    )
    count = len(context.user_data["new_pack_stickers"])

    keyboard = [
        [InlineKeyboardButton("💾 Сохранить пак",  callback_data="save_pack")],
        [InlineKeyboardButton("👀 Посмотреть пак", callback_data="preview_pack")],
    ]
    await msg.reply_text(
        f"✅ Стикер добавлен в пак!\n"
        f"Всего в паке: {count} {plural_sticker(count)}\n\n"
        f"Продолжай отправлять или сохрани пак 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADDING_STICKER


async def preview_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    stickers = context.user_data.get("new_pack_stickers", [])

    if not stickers:
        await query.answer("В паке пока ничего нет.", show_alert=True)
        return ADDING_STICKER

    await query.edit_message_text("👀 Показываю содержимое пака...")

    for item in stickers:
        try:
            fid, t = item["file_id"], item["type"]
            if t == "sticker":   await context.bot.send_sticker(user_id, fid)
            elif t == "photo":   await context.bot.send_photo(user_id, fid)
            elif t == "video":   await context.bot.send_video(user_id, fid)
            elif t == "gif":     await context.bot.send_animation(user_id, fid)
            else:                await context.bot.send_document(user_id, fid)
        except Exception as e:
            logger.warning(f"preview error: {e}")

    keyboard = [[InlineKeyboardButton("💾 Сохранить пак", callback_data="save_pack")]]
    await context.bot.send_message(
        user_id,
        f"Всего в паке: {len(stickers)} {plural_sticker(len(stickers))}\n\nПродолжай отправлять или сохрани пак 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADDING_STICKER


async def save_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    context.bot_data.setdefault(user_id, {"packs": []})
    pack = {
        "name":         context.user_data.get("new_pack_name", "Без названия"),
        "link":         context.user_data.get("new_pack_link", random_link()),
        "type":         context.user_data.get("creating_type", "sticker"),
        "stickers":     context.user_data.get("new_pack_stickers", []),
        "emojis":       "",
        "icon_file_id": None,
    }
    context.bot_data[user_id]["packs"].append(pack)

    for key in ("new_pack_name", "new_pack_link", "new_pack_stickers", "creating_type"):
        context.user_data.pop(key, None)

    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="begin")]]
    await query.edit_message_text(
        f"🎉 Пак <b>{pack['name']}</b> сохранён!\n"
        f"Стикеров: {len(pack['stickers'])}\n\n"
        f"/menu — вернуться в меню",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


# ─── Сборка ───────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("menu",  menu_command),
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
            PACK_SELECTED: [
                CallbackQueryHandler(begin,       pattern="^begin$"),
                CallbackQueryHandler(list_packs,  pattern="^list_packs$"),
                CallbackQueryHandler(select_pack, pattern="^select_pack_\\d+$"),
                CallbackQueryHandler(open_pack,   pattern="^open_pack$"),
                CallbackQueryHandler(manage_pack, pattern="^manage_pack$"),
            ],
            PACK_MANAGEMENT: [
                CallbackQueryHandler(manage_pack,            pattern="^manage_pack$"),
                CallbackQueryHandler(select_pack,            pattern="^select_pack_\\d+$"),
                CallbackQueryHandler(mgmt_add,               pattern="^mgmt_add$"),
                CallbackQueryHandler(mgmt_delete,            pattern="^mgmt_delete$"),
                CallbackQueryHandler(confirm_delete_sticker, pattern="^del_sticker_\\d+$"),
                CallbackQueryHandler(mgmt_rename,            pattern="^mgmt_rename$"),
                CallbackQueryHandler(mgmt_link,              pattern="^mgmt_link$"),
                CallbackQueryHandler(mgmt_link_random,       pattern="^mgmt_link_random$"),
                CallbackQueryHandler(mgmt_emoji,             pattern="^mgmt_emoji$"),
                CallbackQueryHandler(mgmt_icon,              pattern="^mgmt_icon$"),
                CallbackQueryHandler(mgmt_delete_all,        pattern="^mgmt_delete_all$"),
                CallbackQueryHandler(confirm_delete_pack,    pattern="^confirm_delete_pack_\\d+$"),
            ],
            RENAME_PACK: [
                CallbackQueryHandler(manage_pack,      pattern="^manage_pack$"),
                CallbackQueryHandler(mgmt_link_random, pattern="^mgmt_link_random$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rename_or_link),
            ],
            ADD_TO_EXISTING: [
                CallbackQueryHandler(manage_pack, pattern="^manage_pack$"),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Sticker.ALL |
                    filters.ANIMATION | filters.Document.ALL,
                    receive_add_to_existing,
                ),
            ],
            DELETE_STICKER: [
                CallbackQueryHandler(manage_pack,            pattern="^manage_pack$"),
                CallbackQueryHandler(confirm_delete_sticker, pattern="^del_sticker_\\d+$"),
            ],
            CHANGE_ICON: [
                CallbackQueryHandler(manage_pack, pattern="^manage_pack$"),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Sticker.ALL |
                    filters.ANIMATION | filters.Document.ALL,
                    receive_icon,
                ),
            ],
            CHANGE_EMOJI: [
                CallbackQueryHandler(manage_pack, pattern="^manage_pack$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_emoji),
            ],
            PACK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_name),
            ],
            PACK_LINK: [
                CallbackQueryHandler(use_random_link, pattern="^random_link$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_link),
            ],
            ADDING_STICKER: [
                CallbackQueryHandler(save_pack,    pattern="^save_pack$"),
                CallbackQueryHandler(preview_pack, pattern="^preview_pack$"),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.Sticker.ALL |
                    filters.ANIMATION | filters.Document.ALL,
                    receive_sticker,
                ),
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
    logger.info("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
