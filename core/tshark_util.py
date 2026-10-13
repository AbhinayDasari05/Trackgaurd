"""
TrackGuard Cross-Platform TShark Resolver & PCAP Analyzer
Locates TShark executable on macOS and Windows 11.
Provides safe, validated PCAP packet extraction.
"""

import os
import shutil
import subprocess
from typing import Optional, List, Dict, Any


COMMON_TSHARK_PATHS = [
    r"C:\Program Files\Wireshark\tshark.exe",
    r"C:\Program Files (x86)\Wireshark\tshark.exe",
    "/usr/local/bin/tshark",
    "/opt/homebrew/bin/tshark",
    "/usr/bin/tshark",
    "/bin/tshark"
]


def find_tshark() -> Optional[str]:
    """Locate tshark binary across Windows and macOS environments."""
    # 1. Check environment variable override
    env_path = os.environ.get("TSHARK_PATH")
    if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
        return env_path

    # 2. Check PATH
    in_path = shutil.which("tshark")
    if in_path:
        return in_path

    # 3. Check known standard filesystem locations
    for candidate in COMMON_TSHARK_PATHS:
        if os.path.isfile(candidate):
            return candidate

    return None


def get_tshark_version() -> Optional[str]:
    """Returns TShark version string or None if not installed."""
    tshark_bin = find_tshark()
    if not tshark_bin:
        return None
    try:
        proc = subprocess.run([tshark_bin, "-v"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            first_line = proc.stdout.splitlines()[0] if proc.stdout else "TShark (unknown version)"
            return first_line
    except Exception:
        pass
    return None
