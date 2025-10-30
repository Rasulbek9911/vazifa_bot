# Import all handler modules to register them with dispatcher
from . import user_registration
from . import task_handlers
from . import admin_handlers
# join_request_handler o'chirildi (aiogram 2.x qo'llab-quvvatlamaydi)
from . import help
from . import echo

# New modular handlers


# Scheduled tasks are imported separately where needed
# from . import scheduled_tasks