from __future__ import annotations

import os
import shutil


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
BLUE = "\033[38;5;39m"
CYAN = "\033[38;5;45m"
GREEN = "\033[38;5;41m"
YELLOW = "\033[38;5;220m"
RED = "\033[38;5;203m"


LOGO = rf"""
{CYAN}   _____ __                ____             
  / ___// /_  ____  _  __ / __ )____  _  __
  \__ \/ __ \/ __ \| |/_// __  / __ \| |/_/
 ___/ / /_/ / /_/ />  < / /_/ / /_/ />  <  
/____/_.___/\____/_/|_|/_____/\____/_/|_|  
{RESET}
{DIM}dodo258 deploy tool | sing-box / xray | reality | media dns{RESET}
"""


def _silent_json_mode() -> bool:
    return os.environ.get("SBOXCTL_JSON") == "1"


def print_logo() -> None:
    if _silent_json_mode():
        return
    print(LOGO)


def section(title: str) -> None:
    if _silent_json_mode():
        return
    width = shutil.get_terminal_size((100, 20)).columns
    line = "=" * min(width, 72)
    print(f"{BOLD}{BLUE}{line}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{BLUE}{line}{RESET}")


def info(message: str) -> None:
    if _silent_json_mode():
        return
    print(f"{CYAN}[INFO]{RESET} {message}")


def ok(message: str) -> None:
    if _silent_json_mode():
        return
    print(f"{GREEN}[OK]{RESET} {message}")


def warn(message: str) -> None:
    if _silent_json_mode():
        return
    print(f"{YELLOW}[WARN]{RESET} {message}")


def err(message: str) -> None:
    if _silent_json_mode():
        return
    print(f"{RED}[ERR]{RESET} {message}")
