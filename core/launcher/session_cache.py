current_username = None

def set_username(name: str):
    global current_username
    current_username = name

def get_username():
    return current_username
