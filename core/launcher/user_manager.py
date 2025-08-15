import subprocess

def _run_net(args: list[str], accept_yes: bool = False) -> tuple[bool, str]:
    """
    Run net.exe with explicit argv (no shell/pipes). If accept_yes=True,
    feed 'Y\\n' to stdin to auto-confirm prompts (e.g., long password warning).
    """
    try:
        p = subprocess.run(
            ["net"] + args,
            input=("Y\n" if accept_yes else None),
            text=True,
            capture_output=True,
            shell=False,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return (p.returncode == 0), out.strip()
    except Exception as e:
        return False, f"Exception: {e}"

def create_windows_user(username: str, password: str) -> bool:
    """
    Create a local Windows user non‑interactively:
      - /ADD            : create if missing
      - /EXPIRES:NEVER  : never expires
      - /PASSWORDCHG:NO : user cannot change password
      - Auto-confirms 'password longer than 14 chars' prompt by feeding 'Y'
    """
    # 1) Create or update the user
    ok, out = _run_net(
        ["user", username, password, "/ADD", "/EXPIRES:NEVER", "/PASSWORDCHG:NO"],
        accept_yes=True,
    )
    if not ok and "The account already exists" not in out:
        print(f"[create_windows_user] net user failed:\n{out}")
        return False

    # If it already existed, ensure flags are applied (set password & flags)
    if not ok and "The account already exists" in out:
        ok2, out2 = _run_net(
            ["user", username, password, "/EXPIRES:NEVER", "/PASSWORDCHG:NO"],
            accept_yes=True,
        )
        if not ok2:
            print(f"[create_windows_user] net user (set flags) failed:\n{out2}")
            return False

    # 2) Ensure membership in local 'Users' group (idempotent)
    ok3, out3 = _run_net(["localgroup", "Users", username, "/ADD"])
    if not ok3 and "is already a member" not in out3:
        print(f"[create_windows_user] net localgroup add failed:\n{out3}")
        return False

    return True
