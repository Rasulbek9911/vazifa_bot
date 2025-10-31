from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

# .env fayl ichidan quyidagilarni o'qiymiz
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot toekn
ADMINS = env.list("ADMINS")  # adminlar ro'yxati
IP = env.str("ip")  # Xosting ip manzili
API_BASE_URL = "http://127.0.0.1:8000/api"
GENERAL_GROUP_ID = env.str("GENERAL_GROUP_ID", default="-1003295943458")
# Umumiy kanal uchun doimiy approval link
GENERAL_GROUP_INVITE_LINK = env.str("GENERAL_GROUP_INVITE_LINK", default="https://t.me/+7xo2avflxCczMDBi")