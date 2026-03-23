#!/usr/bin/env python3
"""
qBittorrent 推送模块 - 将种子/磁力链接推送到 qBittorrent 下载

支持两种方式：
  1. 推送磁力链接
  2. 推送 .torrent 文件

使用 qBittorrent Web API (v2)，纯 HTTP 请求，无需额外依赖。

用法：
    python3 qbit_push.py magnet "magnet:?xt=urn:btih:..."
    python3 qbit_push.py torrent /path/to/file.torrent
    python3 qbit_push.py magnet "magnet:..." --save-path /mnt/nas/movies
    python3 qbit_push.py magnet "magnet:..." --host 192.168.1.100 --port 8080
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error


# ============================================================
# 配置
# ============================================================
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8080
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "adminadmin"
DEFAULT_SAVE_PATH = ""  # 空 = 使用 qBittorrent 默认下载路径
DEFAULT_CATEGORY = "mini4k"

# 配置文件路径（优先从这里读取）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "qbit_config.json")


def load_config() -> dict:
    """从配置文件加载 qBittorrent 连接信息。"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    """保存配置到文件。"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"💾 配置已保存: {CONFIG_FILE}")


class QBitClient:
    """qBittorrent Web API 客户端（纯 urllib 实现）。"""

    def __init__(self, host: str, port: int, username: str, password: str):
        self.base_url = f"http://{host}:{port}"
        self.username = username
        self.password = password
        self.cookie = None

    def login(self) -> bool:
        """登录 qBittorrent，获取 session cookie。"""
        url = f"{self.base_url}/api/v2/auth/login"
        data = urllib.parse.urlencode({
            "username": self.username,
            "password": self.password,
        }).encode()

        try:
            req = urllib.request.Request(url, data=data, method="POST")
            resp = urllib.request.urlopen(req, timeout=10)
            body = resp.read().decode()

            if body.strip() == "Ok.":
                # 提取 SID cookie
                for header in resp.headers.get_all("Set-Cookie") or []:
                    if "SID=" in header:
                        self.cookie = header.split(";")[0]
                        break
                return True
            else:
                print(f"❌ qBittorrent 登录失败: {body}")
                return False
        except urllib.error.URLError as e:
            print(f"❌ 无法连接 qBittorrent ({self.base_url}): {e}")
            return False

    def _request(self, endpoint: str, data: dict = None, files: dict = None) -> str:
        """发送 API 请求。"""
        url = f"{self.base_url}/api/v2/{endpoint}"

        if files:
            # multipart form 上传（种子文件）
            boundary = "----Mini4kBoundary"
            body_parts = []

            for key, value in (data or {}).items():
                body_parts.append(f"--{boundary}")
                body_parts.append(f'Content-Disposition: form-data; name="{key}"')
                body_parts.append("")
                body_parts.append(str(value))

            for key, (filename, file_data) in files.items():
                body_parts.append(f"--{boundary}")
                body_parts.append(
                    f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'
                )
                body_parts.append("Content-Type: application/x-bittorrent")
                body_parts.append("")
                body_parts.append(None)  # placeholder for binary

            body_parts.append(f"--{boundary}--")
            body_parts.append("")

            # Build binary body
            body_bytes = b""
            for part in body_parts:
                if part is None:
                    # Insert file data
                    for key, (filename, file_data) in files.items():
                        body_bytes += file_data
                else:
                    body_bytes += (part + "\r\n").encode()

            req = urllib.request.Request(url, data=body_bytes, method="POST")
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        else:
            encoded = urllib.parse.urlencode(data or {}).encode()
            req = urllib.request.Request(url, data=encoded, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

        if self.cookie:
            req.add_header("Cookie", self.cookie)

        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return resp.read().decode()
        except urllib.error.URLError as e:
            print(f"❌ API 请求失败 ({endpoint}): {e}")
            return ""

    def add_magnet(self, magnet_url: str, save_path: str = "", category: str = "") -> bool:
        """添加磁力链接到下载队列。"""
        data = {"urls": magnet_url}
        if save_path:
            data["savepath"] = save_path
        if category:
            data["category"] = category

        result = self._request("torrents/add", data)
        # qBittorrent 返回 "Ok." 表示成功
        return True  # API 添加成功无返回体或返回 Ok.

    def add_torrent_file(self, filepath: str, save_path: str = "", category: str = "") -> bool:
        """上传 .torrent 文件到下载队列。"""
        if not os.path.exists(filepath):
            print(f"❌ 种子文件不存在: {filepath}")
            return False

        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            file_data = f.read()

        data = {}
        if save_path:
            data["savepath"] = save_path
        if category:
            data["category"] = category

        files = {"torrents": (filename, file_data)}
        self._request("torrents/add", data, files)
        return True

    def get_version(self) -> str:
        """获取 qBittorrent 版本。"""
        url = f"{self.base_url}/api/v2/app/version"
        req = urllib.request.Request(url)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.read().decode().strip()
        except Exception:
            return "unknown"


def push_to_qbit(
    mode: str,
    target: str,
    host: str,
    port: int,
    username: str,
    password: str,
    save_path: str,
    category: str,
):
    """推送种子或磁力链接到 qBittorrent。"""
    print("=" * 55)
    print(f"📤 qBittorrent 推送")
    print(f"   服务器: {host}:{port}")
    print(f"   模式: {'磁力链接' if mode == 'magnet' else '种子文件'}")
    if save_path:
        print(f"   保存路径: {save_path}")
    if category:
        print(f"   分类: {category}")
    print("=" * 55 + "\n")

    client = QBitClient(host, port, username, password)

    # 登录
    print("🔑 正在登录 qBittorrent...")
    if not client.login():
        print("   请检查:")
        print(f"   1. qBittorrent 是否在 {host}:{port} 运行")
        print(f"   2. Web UI 是否已启用 (设置 → Web UI)")
        print(f"   3. 用户名/密码是否正确")
        sys.exit(1)

    version = client.get_version()
    print(f"✅ 登录成功 (qBittorrent {version})\n")

    # 推送
    if mode == "magnet":
        # 支持直接传磁力链接或包含磁力链接的文件
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8") as f:
                magnet_url = f.read().strip()
            print(f"📂 从文件读取磁力链接: {target}")
        else:
            magnet_url = target

        if not magnet_url.startswith("magnet:"):
            print(f"❌ 无效的磁力链接: {magnet_url[:50]}...")
            sys.exit(1)

        print(f"🧲 推送磁力链接: {magnet_url[:60]}...")
        if client.add_magnet(magnet_url, save_path, category):
            print("🎉 磁力链接已添加到 qBittorrent 下载队列！")
        else:
            print("❌ 添加失败")

    elif mode == "torrent":
        if not os.path.exists(target):
            print(f"❌ 种子文件不存在: {target}")
            sys.exit(1)

        print(f"📦 推送种子文件: {target}")
        if client.add_torrent_file(target, save_path, category):
            print("🎉 种子文件已添加到 qBittorrent 下载队列！")
        else:
            print("❌ 添加失败")


def setup_config():
    """交互式配置 qBittorrent 连接信息。"""
    print("⚙️  配置 qBittorrent 连接信息\n")
    config = load_config()

    host = input(f"  主机地址 [{config.get('host', DEFAULT_HOST)}]: ").strip()
    port = input(f"  端口 [{config.get('port', DEFAULT_PORT)}]: ").strip()
    username = input(f"  用户名 [{config.get('username', DEFAULT_USERNAME)}]: ").strip()
    password = input(f"  密码 [{config.get('password', DEFAULT_PASSWORD)}]: ").strip()
    save_path = input(f"  默认保存路径 [{config.get('save_path', '')}]: ").strip()

    config.update({
        "host": host or config.get("host", DEFAULT_HOST),
        "port": int(port) if port else config.get("port", DEFAULT_PORT),
        "username": username or config.get("username", DEFAULT_USERNAME),
        "password": password or config.get("password", DEFAULT_PASSWORD),
        "save_path": save_path or config.get("save_path", ""),
    })

    save_config(config)

    # 测试连接
    print("\n🔗 测试连接...")
    client = QBitClient(config["host"], config["port"], config["username"], config["password"])
    if client.login():
        version = client.get_version()
        print(f"✅ 连接成功！qBittorrent {version}")
    else:
        print("❌ 连接失败，请检查配置")


def main():
    parser = argparse.ArgumentParser(
        description="推送种子/磁力链接到 qBittorrent"
    )
    subparsers = parser.add_subparsers(dest="command")

    # magnet 子命令
    magnet_parser = subparsers.add_parser("magnet", help="推送磁力链接")
    magnet_parser.add_argument("target", help="磁力链接或包含磁力链接的文件路径")

    # torrent 子命令
    torrent_parser = subparsers.add_parser("torrent", help="推送种子文件")
    torrent_parser.add_argument("target", help=".torrent 文件路径")

    # setup 子命令
    subparsers.add_parser("setup", help="配置 qBittorrent 连接信息")

    # 公共参数
    for sub in [magnet_parser, torrent_parser]:
        sub.add_argument("--host", default=None, help="qBittorrent 主机")
        sub.add_argument("--port", type=int, default=None, help="qBittorrent 端口")
        sub.add_argument("--username", default=None, help="用户名")
        sub.add_argument("--password", default=None, help="密码")
        sub.add_argument("--save-path", default=None, help="下载保存路径 (NAS 路径)")
        sub.add_argument("--category", default=DEFAULT_CATEGORY, help="下载分类")

    args = parser.parse_args()

    if args.command == "setup":
        setup_config()
        return

    if not args.command:
        parser.print_help()
        return

    # 合并配置：命令行参数 > 配置文件 > 默认值
    config = load_config()
    host = args.host or config.get("host", DEFAULT_HOST)
    port = args.port or config.get("port", DEFAULT_PORT)
    username = args.username or config.get("username", DEFAULT_USERNAME)
    password = args.password or config.get("password", DEFAULT_PASSWORD)
    save_path = args.save_path or config.get("save_path", DEFAULT_SAVE_PATH)
    category = args.category

    push_to_qbit(args.command, args.target, host, port, username, password, save_path, category)


if __name__ == "__main__":
    main()
