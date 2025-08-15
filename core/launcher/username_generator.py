import random

def generate_session_username():
    prefix_options = ["WinHelper", "UserSvc", "Updater", "RuntimeSvc", "SysMaint"]
    prefix = random.choice(prefix_options)
    suffix = random.randint(1000, 9999)
    return f"{prefix}_{suffix}"
