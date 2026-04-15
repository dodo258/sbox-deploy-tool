from __future__ import annotations

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
{DIM}dodo258 sing-box deploy tool | reality | media dns | exports{RESET}
"""


def print_logo() -> None:
    print(LOGO)


def section(title: str) -> None:
    width = shutil.get_terminal_size((100, 20)).columns
    line = "=" * min(width, 72)
    print(f"{BOLD}{BLUE}{line}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{BLUE}{line}{RESET}")


def info(message: str) -> None:
    print(f"{CYAN}[INFO]{RESET} {message}")


def ok(message: str) -> None:
    print(f"{GREEN}[OK]{RESET} {message}")


def warn(message: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {message}")


def err(message: str) -> None:
    print(f"{RED}[ERR]{RESET} {message}")
