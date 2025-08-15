import subprocess

def delete_windows_user(username: str, force: bool = True):
    try:
        args = ["net", "user", username, "/delete"]
        if force:
            print(f"🧹 Deleting user '{username}'...")
        subprocess.run(args, check=True)
        print(f"✅ User '{username}' deleted successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to delete user '{username}': {e}")
        return False
