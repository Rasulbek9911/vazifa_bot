from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

# .env fayl ichidan quyidagilarni o'qiymiz
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot token
ADMINS = env.list("ADMINS")  # adminlar ro'yxati
IP = env.str("ip")  # Xosting ip manzili
API_BASE_URL = env.str("API_BASE_URL")  # API bazaviy URL