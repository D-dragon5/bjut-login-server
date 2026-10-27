#!/usr/bin/env python3
"""Headless account manager for the BJUT wired (lgn) portal."""

import argparse
import fcntl
import getpass
import json
import os
import re
import ssl
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib import parse, request

BASE = Path.home() / ".config" / "bjut-login"
CONFIG = BASE / "accounts.json"
LOCK = BASE / "lock"
PORTAL = "https://lgn.bjut.edu.cn/"
LOGOUT = "https://lgn.bjut.edu.cn/F.htm"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def ensure_dir():
    BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(BASE, 0o700)


@contextmanager
def locked():
    ensure_dir()
    with open(LOCK, "a", encoding="utf-8") as stream:
        os.chmod(LOCK, 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def load():
    if not CONFIG.exists():
        return {"accounts": {}, "active": None, "enabled": False}
    if CONFIG.stat().st_mode & 0o077:
        raise RuntimeError(f"凭据文件权限过宽：请执行 chmod 600 {CONFIG}")
    with CONFIG.open(encoding="utf-8") as stream:
        return json.load(stream)


def save(config):
    ensure_dir()
    temp = BASE / f"accounts.json.{os.getpid()}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, CONFIG)
    finally:
        temp.unlink(missing_ok=True)


def fetch(url=PORTAL, data=None):
    payload = parse.urlencode(data).encode() if data is not None else None
    req = request.Request(url, data=payload, headers={"User-Agent": UA})
    with request.urlopen(req, timeout=12, context=ssl.create_default_context()) as response:
        return response.read().decode("gb18030", errors="replace")


def state():
    page = fetch()
    if re.search(r"\btime\s*=\s*['\"]\d+", page) or "DispTFM" in page:
        return "online", page
    if re.search(r"\bv4serip\s*=", page):
        return "offline", page
    return "unknown", page


def log_out():
    before, _ = state()
    if before == "offline":
        print("当前已离线")
        return True
    fetch(LOGOUT)
    for _ in range(4):
        time.sleep(1)
        after, _ = state()
        if after == "offline":
            print("注销成功")
            return True
    print("注销后仍未确认离线；请检查门户状态", file=sys.stderr)
    return False


def log_in(account):
    current, page = state()
    if current == "online":
        print("当前已有在线会话，未重复登录")
        return True
    if current != "offline":
        raise RuntimeError("无法判定门户状态，已停止提交凭据")
    ipv4 = re.search(r"\bv4serip\s*=\s*['\"](\d{1,3}(?:\.\d{1,3}){3})", page)
    if not ipv4:
        raise RuntimeError("未找到门户 IPv4 地址，已停止提交凭据")
    result = fetch(PORTAL, {"DDDDD": account["user"], "upass": account["password"],
                            "0MKKey": "Login", "v6ip": ""})
    if "Msg=01" in result:
        raise RuntimeError("门户提示密码错误")
    if "Msg=04" in result:
        raise RuntimeError("门户提示余额不足")
    for _ in range(4):
        time.sleep(1)
        if state()[0] == "online":
            print("登录成功，已确认在线")
            return True
    raise RuntimeError("提交登录后未确认在线，请检查门户或账号")


def main():
    parser = argparse.ArgumentParser(description="BJUT 有线校园网账号与保活管理")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("add", "use", "remove"):
        sub.add_parser(name).add_argument("name")
    for name in ("list", "status", "logout", "check", "disable"):
        sub.add_parser(name)
    args = parser.parse_args()
    with locked():
        config = load()
        accounts = config["accounts"]
        if args.command == "add":
            user = input("校园网账号: ").strip()
            password = getpass.getpass("校园网密码: ")
            if not user or not password:
                raise RuntimeError("账号和密码不能为空")
            accounts[args.name] = {"user": user, "password": password}
            save(config)
            print(f"已保存账号别名 {args.name}；凭据文件权限为 600")
        elif args.command == "list":
            for name in accounts:
                print(f"{name}{' [当前]' if name == config['active'] else ''}")
            print(f"自动重登：{'开启' if config['enabled'] else '关闭'}")
        elif args.command == "remove":
            if args.name not in accounts:
                raise RuntimeError("账号别名不存在")
            if args.name == config["active"]:
                config["active"] = None
                config["enabled"] = False
            del accounts[args.name]
            save(config)
            print("已移除账号")
        elif args.command == "status":
            print(f"门户状态：{state()[0]}；目标账号：{config['active'] or '未设置'}；自动重登：{'开启' if config['enabled'] else '关闭'}")
        elif args.command == "disable":
            config["enabled"] = False
            save(config)
            print("已关闭自动重登")
        elif args.command == "logout":
            config["enabled"] = False
            save(config)
            if not log_out():
                return 1
        elif args.command == "use":
            account = accounts.get(args.name)
            if not account:
                raise RuntimeError("账号别名不存在；请先运行 add")
            config["enabled"] = False
            save(config)
            if not log_out():
                return 1
            time.sleep(2)
            log_in(account)
            config["active"] = args.name
            config["enabled"] = True
            save(config)
            print(f"当前目标账号：{args.name}；自动重登已开启")
        elif args.command == "check":
            if not config["enabled"] or not config["active"]:
                return 0
            current, _ = state()
            if current == "online":
                return 0
            if current != "offline":
                raise RuntimeError("门户状态未知，未尝试自动登录")
            log_in(accounts[config["active"]])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        sys.exit(1)
