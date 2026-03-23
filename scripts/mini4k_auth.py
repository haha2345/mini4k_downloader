#!/usr/bin/env python3
"""
模块二：Cloudflare 盾绕过与 Mini4k 登录鉴权 (Auth & Bypass)

功能：
  1. 首次登录：启动有头浏览器(headless=False)，用户手动过 CF 盾 + 登录
  2. 保存凭证：登录成功后保存 auth_state.json，后续任务静默复用
  3. 验证凭证：用 --verify 参数检查已保存的凭证是否仍然有效

用法：
    python3 mini4k_auth.py            # 登录并保存凭证
    python3 mini4k_auth.py --verify   # 验证已保存的凭证
"""

import argparse
import os
import sys
import time
from playwright.sync_api import sync_playwright

# 配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_FILE = os.path.join(SCRIPT_DIR, "auth_state.json")
TARGET_URL = "https://www.mini4k.com/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def do_login(state_file: str):
    """启动有头浏览器，让用户手动过 CF 盾并登录，然后保存凭证。"""
    print("🚀 正在启动浏览器（有头模式）...")
    print("   如果在 Ubuntu 服务器上请确保有桌面或 X11 转发\n")

    with sync_playwright() as p:
        # 使用 chromium，兼容 Ubuntu VM（不依赖本地 Chrome）
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            accept_downloads=True,
        )
        page = context.new_page()

        print(f"🌐 正在访问: {TARGET_URL}")
        page.goto(TARGET_URL, timeout=60000)

        print("\n" + "=" * 55)
        print("⏸️  等待你手动操作：")
        print("   1. 完成 Cloudflare 人机验证（点勾选框）")
        print("   2. 登录你的 mini4k 账号")
        print("   3. 确认页面加载完毕后，回到终端")
        print("=" * 55 + "\n")

        input("👉 操作完成后，按 [回车] 继续...")

        # 保存登录状态
        context.storage_state(path=state_file)
        print(f"\n✅ 凭证已保存至: {state_file}")
        print("   后续下载任务会自动复用此凭证，无需再次登录。\n")

        time.sleep(2)
        browser.close()
        print("🛑 浏览器已关闭。")


def do_verify(state_file: str):
    """用已保存的凭证静默访问 mini4k，验证是否仍然有效。"""
    if not os.path.exists(state_file):
        print(f"❌ 凭证文件不存在: {state_file}")
        print("   请先运行: python3 mini4k_auth.py")
        sys.exit(1)

    print(f"🔍 正在验证凭证: {state_file}")
    print("   使用静默模式 (headless=True) 访问 mini4k...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=state_file,
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        try:
            page.goto(TARGET_URL, timeout=30000)
            time.sleep(3)

            title = page.title()
            url = page.url

            # 检查是否被 CF 拦截（CF 拦截页面的标题通常含 "Just a moment"）
            if "just a moment" in title.lower() or "cloudflare" in title.lower():
                print("⚠️  凭证可能已失效！被 Cloudflare 拦截了。")
                print(f"   页面标题: {title}")
                print("   建议重新运行: python3 mini4k_auth.py")
                browser.close()
                sys.exit(1)

            # 检查页面是否包含登录入口（如果有登录按钮说明未登录）
            content = page.content()
            logged_in = "退出" in content or "个人中心" in content or "我的" in content

            print(f"   页面标题: {title}")
            print(f"   当前 URL: {url}")

            if logged_in:
                print("\n✅ 凭证有效！已处于登录状态。")
            else:
                print("\n⚠️  已通过 CF 盾，但可能未登录（未检测到登录状态标志）。")
                print("   如果下载时遇到问题，请重新运行: python3 mini4k_auth.py")

        except Exception as e:
            print(f"❌ 验证失败: {e}")
            print("   建议重新运行: python3 mini4k_auth.py")
            sys.exit(1)
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="Mini4k 登录鉴权工具 - 绕过 CF 盾并保存登录凭证"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="验证已保存的凭证是否仍然有效",
    )
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help=f"凭证文件路径 (默认: {DEFAULT_STATE_FILE})",
    )
    args = parser.parse_args()

    if args.verify:
        do_verify(args.state_file)
    else:
        do_login(args.state_file)


if __name__ == "__main__":
    main()
