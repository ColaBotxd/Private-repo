import json

def get_session_credentials():
    with open("config/settings.json", "r") as f:
        data = json.load(f)
        creds = data.get("session_user", {})
        return creds.get("username", ""), creds.get("password", "")
