from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

# .env fayl ichidan quyidagilarni o'qiymiz
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot token
ADMINS = env.list("ADMINS")  # adminlar ro'yxati
MILLIY_ADMIN = env.str("MILLIY_ADMIN")  # Milliy Sertifikat admin
ATTESTATSIYA_ADMIN = env.str("ATTESTATSIYA_ADMIN")  # Attestatsiya admin
IP = env.str("ip")  # Xosting ip manzili
API_BASE_URL = env.str("API_BASE_URL").rstrip("/")  # API bazaviy URL (oxiridagi / ni olib tashlash)