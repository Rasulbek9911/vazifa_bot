from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

# .env fayl ichidan quyidagilarni o'qiymiz
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot toekn
ADMINS = env.list("ADMINS")  # adminlar ro'yxati
IP = env.str("ip")  # Xosting ip manzili
API_BASE_URL = "http://127.0.0.1:8000/api"

# Umumiy kanal (birinchi kanal) - approval link
GENERAL_CHANNEL_ID = env.str("GENERAL_CHANNEL_ID", default="-1003295943458")
GENERAL_CHANNEL_INVITE_LINK = env.str("GENERAL_CHANNEL_INVITE_LINK", default="https://t.me/+Pa-WbbL1s0c3NmYy")

# Eski nomlar (backward compatibility)
GENERAL_GROUP_ID = GENERAL_CHANNEL_ID
GENERAL_GROUP_INVITE_LINK = GENERAL_CHANNEL_INVITE_LINK