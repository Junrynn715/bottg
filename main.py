import asyncio
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# Apply nest_asyncio to allow running within existing loop
nest_asyncio.apply()

# Token dari BotFather
TOKEN = 'Token'

# ID Spreadsheet Anda
SPREADSHEET_ID = 'token'

# Kredensial dan akses Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# Data to-do list
todos = {}


def load_data_from_sheet():
    global todos
    todos = {}
    data = sheet.get_all_records()
    for row in data:
        user_id = int(row['user_id'])
        group = row['group']
        task = row['task']
        completed = row.get('completed', 'False') == 'True'
        date = row.get('date', '')  # Gunakan get() untuk menghindari KeyError
        if user_id not in todos:
            todos[user_id] = {}
        if group not in todos[user_id]:
            todos[user_id][group] = []
        todos[user_id][group].append({
            "task": task,
            "completed": completed,
            "date": date
        })


def save_data_to_sheet():
    # Prepare data in the correct format for Google Sheets
    rows = [['user_id', 'group', 'task', 'completed',
             'date']]  # Include header in the rows
    for user_id, groups in todos.items():
        for group, tasks in groups.items():
            for task in tasks:
                rows.append([
                    user_id, group, task['task'], task['completed'],
                    task['date']
                ])

    # Clear existing data in the sheet but keep the header row
    existing_data = sheet.get_all_values()
    if len(existing_data) > 1:
        existing_range = f'A2:E{len(existing_data)}'
        sheet.batch_clear([existing_range])

    # Update sheet with new data (including header)
    sheet.update('A1:E', rows)


# Fungsi untuk memulai bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Halo! Saya adalah bot To-Do List. Gunakan /add <kelompok> <tugas> untuk menambah tugas, /list untuk melihat daftar kelompok, /remove <nama_tugas> untuk menghapus tugas, /status untuk menampilkan status tugas, dan /help untuk bantuan lebih lanjut.'
    )


# Fungsi untuk menambah tugas dalam kelompok
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if len(context.args) < 2:
        await update.message.reply_text(
            'Format salah. Gunakan perintah: /add <kelompok> <tugas>. Contoh: /add Kerja Belajar Python.'
        )
        return

    group = context.args[0].lower(
    )  # Convert to lowercase for case-insensitive comparison
    task = ' '.join(context.args[1:]).lower(
    )  # Convert to lowercase for case-insensitive comparison

    if user_id not in todos:
        todos[user_id] = {}

    if group not in todos[user_id]:
        todos[user_id][group] = []

    # Check if the task already exists in the group (case-insensitive)
    if any(t["task"].lower() == task for t in todos[user_id][group]):
        await update.message.reply_text(
            f'Tugas "{task}" sudah ada di kelompok "{group}".')
        return

    date = datetime.now().strftime('%Y-%m-%d')  # Update the date
    todos[user_id][group].append({
        "task": task,
        "completed": False,
        "date": date
    })
    save_data_to_sheet()  # Save to Google Sheets
    await update.message.reply_text(
        f'Tugas "{task}" telah ditambahkan ke kelompok "{group}".')


# Fungsi untuk menampilkan tombol inline
async def show_groups(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id

    if user_id in todos and todos[user_id]:
        keyboard = [[
            InlineKeyboardButton(group, callback_data=f'group_{group}')
        ] for group in todos[user_id].keys()]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Pilih kelompok untuk melihat tugas:',
                                        reply_markup=reply_markup)
    else:
        await update.message.reply_text('Tidak ada kelompok tugas.')


# Fungsi untuk menangani tombol inline
async def button_handler(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    group = query.data[len('group_'):].lower(
    )  # Convert to lowercase for case-insensitive comparison

    if user_id in todos and group in todos[user_id] and todos[user_id][group]:
        tasks = '\n'.join([
            f'{i + 1}. {task["task"]}'
            for i, task in enumerate(todos[user_id][group])
        ])
        await query.message.edit_text(
            f'Daftar tugas di kelompok "{group}":\n{tasks}')
    else:
        await query.message.edit_text(f'Tidak ada tugas di kelompok "{group}".'
                                      )


# Fungsi untuk menghapus tugas
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if len(context.args) < 1:
        await update.message.reply_text(
            'Format salah. Gunakan perintah: /remove <nama_tugas>. Contoh: /remove Belajar Python.'
        )
        return

    task_name = ' '.join(context.args).lower(
    )  # Convert to lowercase for case-insensitive comparison

    if user_id in todos:
        task_found = False
        for group, tasks in todos[user_id].items():
            for i, task in enumerate(tasks):
                if task["task"].lower() == task_name:
                    tasks.pop(i)
                    if not tasks:  # Hapus kelompok jika kosong
                        del todos[user_id][group]
                    task_found = True
                    save_data_to_sheet()  # Save to Google Sheets
                    await update.message.reply_text(
                        f'Tugas "{task_name}" telah dihapus.')
                    break
            if task_found:
                break

        if not task_found:
            await update.message.reply_text(
                f'Tugas "{task_name}" tidak ditemukan.')
    else:
        await update.message.reply_text(f'Tidak ada tugas yang tersedia.')


# Variabel untuk menyimpan tanggal yang akan ditampilkan di bawah
current_date = datetime.now().strftime('%Y-%m-%d')


# Fungsi untuk menampilkan status tugas
async def show_status(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id

    if user_id in todos and todos[user_id]:
        status_text = []
        for group, tasks in todos[user_id].items():
            status_text.append(f'\nKelompok "{group}":')
            for i, task in enumerate(tasks):
                status_text.append(
                    f'{i + 1}. {"[selesai]" if task["completed"] else "[belum dikerjakan]"} {task["task"]}'
                )
        # Menambahkan tanggal di bagian bawah status tugas
        status_text.append(f'\nTanggal: {current_date}')
        await update.message.reply_text('\n'.join(status_text))
    else:
        await update.message.reply_text('Tidak ada tugas yang tersedia.')


# Fungsi untuk menandai tugas selesai atau belum selesai
async def toggle_status(update: Update,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if len(context.args) < 1:
        await update.message.reply_text(
            'Format salah. Gunakan perintah: /toggle <nama_tugas>. Contoh: /toggle Belajar Python.'
        )
        return

    task_name = ' '.join(context.args).lower(
    )  # Convert to lowercase for case-insensitive comparison

    if user_id in todos:
        task_found = False
        for group, tasks in todos[user_id].items():
            for task in tasks:
                if task["task"].lower() == task_name:
                    task["completed"] = not task["completed"]
                    task["date"] = datetime.now().strftime(
                        '%Y-%m-%d')  # Update the date
                    save_data_to_sheet()  # Save to Google Sheets
                    await update.message.reply_text(
                        f'Status tugas "{task_name}" telah diperbarui.')
                    task_found = True
                    break
            if task_found:
                break

        if not task_found:
            await update.message.reply_text(
                f'Tugas "{task_name}" tidak ditemukan.')
    else:
        await update.message.reply_text(f'Tidak ada tugas yang tersedia.')


# Fungsi untuk menampilkan daftar perintah
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Berikut adalah daftar perintah yang tersedia:\n"
        "/start - Memulai bot dan menampilkan pesan sambutan.\n"
        "/add <kelompok> <tugas> - Menambahkan tugas ke kelompok tertentu.\n"
        "/list - Menampilkan daftar kelompok tugas.\n"
        "/remove <nama_tugas> - Menghapus tugas berdasarkan nama.\n"
        "/status - Menampilkan status semua tugas.\n"
        "/toggle <nama_tugas> - Menandai tugas sebagai selesai atau belum selesai.\n"
        "/help - Menampilkan daftar perintah yang tersedia.")
    await update.message.reply_text(help_text)


# Fungsi untuk mereset status setiap hari
async def daily_reset() -> None:
    while True:
        now = datetime.now()
        # Check if it's 7 AM WIB (07:00 WIB)
        if now.hour == 7 and now.minute == 0:
            for user_id in todos:
                for group in todos[user_id]:
                    for task in todos[user_id][group]:
                        if task["completed"]:
                            task["completed"] = False
                            task["date"] = ''
            save_data_to_sheet()  # Save to Google Sheets
        await asyncio.sleep(60)  # Check every minute


async def schedule_daily_tasks(application: Application) -> None:
    while True:
        now = datetime.now()
        # Calculate the time to wait until the next reset at 7 AM WIB
        if now.hour < 7:
            next_reset = now.replace(hour=7, minute=0, second=0, microsecond=0)
        else:
            next_reset = (now + timedelta(days=1)).replace(hour=7,
                                                           minute=0,
                                                           second=0,
                                                           microsecond=0)

        wait_time = (next_reset - now).total_seconds()
        await asyncio.sleep(wait_time)  # Wait until the next reset time
        await daily_reset()  # Perform the daily reset


async def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("list", show_groups))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("status", show_status))
    application.add_handler(CommandHandler("toggle", toggle_status))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Load data from Google Sheets when starting
    load_data_from_sheet()

    # Schedule daily reset and alert at 7 AM WIB
    asyncio.create_task(schedule_daily_tasks(application))

    # Start polling
    await application.run_polling(
    )  # Changed from start_polling to run_polling
    await application.idle()


if __name__ == '__main__':
    asyncio.run(main())
