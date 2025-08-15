import ctypes
import ctypes.wintypes as wintypes

def run_as_user(username: str, password: str, executable: str, domain="."):
    LOGON_WITH_PROFILE = 0x00000001
    CREATE_NEW_CONSOLE = 0x00000010

    # Setup STARTUPINFO structure
    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()

    result = ctypes.windll.advapi32.CreateProcessWithLogonW(
        ctypes.c_wchar_p(username),
        ctypes.c_wchar_p(domain),
        ctypes.c_wchar_p(password),
        LOGON_WITH_PROFILE,
        None,
        ctypes.c_wchar_p(executable),
        CREATE_NEW_CONSOLE,
        None,
        None,
        ctypes.byref(si),
        ctypes.byref(pi)
    )

    if result == 0:
        error = ctypes.GetLastError()
        print(f"❌ Failed to launch process. Error code: {error}")
    else:
        print(f"✅ Launched '{executable}' as {username}")
