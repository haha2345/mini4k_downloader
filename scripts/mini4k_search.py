#!/usr/bin/env python3
"""
Module 3: Mini4k 智能检索与种子下载 (Torrent Fetcher)

功能：
  1. 接收影片名称，在 mini4k.com 搜索
  2. 进入影视详情页，按分辨率 Tab 解析资源
  3. 筛选规则：排除杜比视界 → 优先4K → 降级1080p → 优先中字 → 优先磁力种子
  4. 进入种子详情页获取磁力链接或种子下载

用法：
    python3 mini4k_search.py "太平年"
    python3 mini4k_search.py "太平年" --download-dir ~/Downloads
    python3 mini4k_search.py "太平年" --no-headless   # 调试模式
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from urllib.parse import quote
from playwright.sync_api import sync_playwright, Page

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_FILE = os.path.join(SCRIPT_DIR, "auth_state.json")
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Downloads")
BASE_URL = "https://www.mini4k.com"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# 杜比视界排除关键词
DV_KEYWORDS = ["杜比视界", "dolby vision", "dovi", ".dv.", "-dv-", " dv "]
# 中文字幕优先关键词
CHS_KEYWORDS = ["简体中文", "中文字幕", "内嵌中字", "特效中字", "简中", "中字", "chs", "cht", "中英"]
# 网盘关键词
CLOUD_KEYWORDS = ["网盘", "阿里", "百度", "夸克", "115", "迅雷云"]
# 用户有会员的网盘（优先这些）
PREFERRED_CLOUDS = ["百度", "夸克"]
# 字幕搜索源
SUBTITLE_SEARCH_URL = "https://assrt.net/sub/?searchword={keyword}"


def is_dolby_vision(text: str) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in DV_KEYWORDS)


def has_chinese_sub(text: str) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in CHS_KEYWORDS)


def is_cloud_drive(text: str) -> bool:
    return any(kw in text for kw in CLOUD_KEYWORDS)


def detect_resolution_from_name(text: str) -> str:
    """从资源名称/文件名中检测分辨率。"""
    lower = text.lower()
    if "4k" in lower or "2160p" in lower or "2160" in lower or "uhd" in lower:
        return "4K"
    if "1080p" in lower or "1080" in lower:
        return "1080p"
    if "720p" in lower or "720" in lower:
        return "720p"
    return "unknown"


def check_cf_block(page: Page):
    """检查是否被 CF 拦截。"""
    title = page.title().lower()
    if "just a moment" in title or "cloudflare" in title:
        print("⚠️  被 Cloudflare 拦截！凭证可能已过期。")
        print("   请重新运行: python3 mini4k_auth.py")
        sys.exit(1)


# ============================================================
# Step 1: 搜索影片
# ============================================================
def search_movie(page: Page, keyword: str) -> str | None:
    """在 mini4k 搜索影片，返回详情页 URL。"""
    search_url = f"{BASE_URL}/search?text={quote(keyword)}"
    print(f"🌐 搜索: {search_url}")
    page.goto(search_url, timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    
    check_cf_block(page)
    
    # 查找搜索结果链接
    result_links = page.query_selector_all("a[href*='/movies/'], a[href*='/shows/']")
    
    seen = set()
    for link in result_links:
        href = link.get_attribute("href") or ""
        text = link.inner_text().strip()
        if href in seen or not text:
            continue
        seen.add(href)
        
        if keyword in text:
            full_url = href if href.startswith("http") else BASE_URL + href
            print(f"  ✅ 匹配: {text}")
            print(f"     URL: {full_url}")
            return full_url
    
    # 备用：不严格匹配关键词，取第一个结果
    seen.clear()
    for link in result_links:
        href = link.get_attribute("href") or ""
        text = link.inner_text().strip()
        if href in seen or not text or len(text) < 2:
            continue
        seen.add(href)
        full_url = href if href.startswith("http") else BASE_URL + href
        print(f"  📌 最接近结果: {text}")
        return full_url
    
    return None


# ============================================================
# Step 2: 解析详情页中的资源表格（JS 方式，不需要点击 Tab）
# ============================================================
def parse_detail_page(page: Page, keyword: str) -> list:
    """
    使用 JavaScript 直接提取所有 Tab 下的资源，无需点击切换。
    Mini4k 使用 Semantic UI tab 系统，所有 tab 内容都在 DOM 中。
    """
    
    # 通过 JS 提取所有资源信息（包括隐藏 Tab 中的）
    raw_resources = page.evaluate("""
    () => {
        const results = [];
        
        // 找到所有 tab 段落（Semantic UI: .ui.tab 或者直接的 section）
        const tabs = document.querySelectorAll('.ui.tab, .ui.segment, [data-tab]');
        
        // 如果没有 tab 系统，就直接解析整页的表格
        const tables = tabs.length > 0 ? [] : document.querySelectorAll('table');
        
        function parseTable(table, resolution) {
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 2) return;
                
                const nameLink = row.querySelector('a[href*="/torrents/"]') || row.querySelector('a');
                if (!nameLink) return;
                
                const name = nameLink.innerText.trim();
                const href = nameLink.getAttribute('href') || '';
                if (!name || !href) return;
                
                // 判断下载类型
                const hasUserLink = row.querySelector('a.link-user, .link-user') !== null;
                const hasNodeLink = row.querySelector('a.link-node, .link-node') !== null;
                
                // 提取文件大小
                const rowText = row.innerText;
                const sizeMatch = rowText.match(/([\d.]+)\s*(GB|MB|TB)/);
                const size = sizeMatch ? sizeMatch[0] : '';
                
                results.push({
                    name: name,
                    href: href,
                    resolution: resolution,
                    rowText: rowText,
                    isTorrent: hasUserLink,
                    isCloud: hasNodeLink && !hasUserLink,
                    size: size
                });
            });
        }
        
        if (tabs.length > 0) {
            // 有 tab 系统
            // 同时检查 tab menu 获取 tab 名称和 data-tab 属性
            const menuItems = document.querySelectorAll('.ui.tabular.menu .item, .ui.menu .item');
            const tabMap = {};
            menuItems.forEach(item => {
                const tabId = item.getAttribute('data-tab') || '';
                const tabText = item.innerText.trim();
                if (tabId) tabMap[tabId] = tabText;
            });
            
            tabs.forEach(tab => {
                const tabId = tab.getAttribute('data-tab') || '';
                const tabName = tabMap[tabId] || tabId || '';
                
                // 判断分辨率
                let resolution = 'unknown';
                const lowerName = tabName.toLowerCase();
                if (lowerName.includes('dolby') || lowerName.includes('vision')) {
                    resolution = 'DV';  // 将在 Python 端被过滤
                } else if (lowerName.includes('4k') || lowerName.includes('2160')) {
                    resolution = '4K';
                } else if (lowerName.includes('1080')) {
                    resolution = '1080p';
                } else if (lowerName.includes('720')) {
                    resolution = '720p';
                }
                
                const table = tab.querySelector('table');
                if (table) {
                    parseTable(table, resolution);
                }
            });
        }
        
        // 备用：直接从所有 table 提取
        if (results.length === 0) {
            // 尝试从页面标题判断分辨率段落
            const allHeaders = document.querySelectorAll('h2, h3, h4, .header');
            let currentRes = 'unknown';
            
            document.querySelectorAll('table').forEach(table => {
                // 查找前面最近的标题来判断分辨率
                let prevEl = table.previousElementSibling;
                while (prevEl) {
                    const text = prevEl.innerText || '';
                    const lower = text.toLowerCase();
                    if (lower.includes('4k') || lower.includes('2160')) {
                        currentRes = '4K';
                        break;
                    } else if (lower.includes('1080')) {
                        currentRes = '1080p';
                        break;
                    } else if (lower.includes('dolby') || lower.includes('vision')) {
                        currentRes = 'DV';
                        break;
                    }
                    prevEl = prevEl.previousElementSibling;
                }
                parseTable(table, currentRes);
            });
        }
        
        return results;
    }
    """)
    
    print(f"  📄 JS 提取到 {len(raw_resources)} 条原始资源")
    
    resources = []
    for raw in raw_resources:
        name = raw.get("name", "")
        row_text = raw.get("rowText", "")
        resolution = raw.get("resolution", "unknown")
        
        # 如果 Tab 未能判断分辨率，从文件名中二次检测
        if resolution == "unknown":
            resolution = detect_resolution_from_name(name)
        
        # 跳过 DV 分组的资源
        if resolution == "DV":
            print(f"    🚫 排除(DV Tab): {name[:60]}")
            continue
        
        # 二次检查具体资源名称中是否含 DV
        if is_dolby_vision(name) or is_dolby_vision(row_text):
            print(f"    🚫 排除(DV 标题): {name[:60]}")
            continue
        
        resources.append({
            "name": name,
            "href": raw.get("href", ""),
            "resolution": resolution,
            "has_chs": has_chinese_sub(name) or has_chinese_sub(row_text),
            "is_torrent": raw.get("isTorrent", False),
            "is_cloud": raw.get("isCloud", False) or is_cloud_drive(name) or is_cloud_drive(row_text),
            "size": raw.get("size", ""),
        })
    
    return resources


# ============================================================
# Step 3: 资源排序
# ============================================================
def rank_resources(resources: list) -> list:
    """
    排序资源，优先级：
    1. 分辨率（4K > 1080p > 720p > unknown）
    2. 下载类型（种子/磁力 > 网盘）
    3. 中文字幕（有 > 无）
    """
    res_order = {"4K": 4, "1080p": 3, "720p": 2, "unknown": 1}
    
    def sort_key(r):
        return (
            res_order.get(r["resolution"], 0),
            1 if r["is_torrent"] and not r["is_cloud"] else 0,
            1 if r["has_chs"] else 0,
        )
    
    return sorted(resources, key=sort_key, reverse=True)


# ============================================================
# Step 4: 下载种子
# ============================================================
def download_torrent(page: Page, resource: dict, download_dir: str, keyword: str):
    """进入种子详情页，获取磁力链接或下载种子文件。"""
    href = resource["href"]
    torrent_url = href if href.startswith("http") else BASE_URL + href
    
    print(f"\n🔗 进入种子详情页: {torrent_url}")
    page.goto(torrent_url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    check_cf_block(page)
    
    # 方法1：寻找磁力链接按钮
    magnet_btn = page.query_selector("a[href*='magnet:']")
    if magnet_btn:
        magnet_href = magnet_btn.get_attribute("href")
        magnet_file = os.path.join(download_dir, f"{keyword}_magnet.txt")
        with open(magnet_file, "w", encoding="utf-8") as f:
            f.write(magnet_href)
        print(f"🧲 磁力链接已保存: {magnet_file}")
        print(f"   链接: {magnet_href[:80]}...")
        return True
    
    # 方法2：寻找 .torrent 下载链接
    torrent_link = page.query_selector("a[href*='.torrent']")
    if torrent_link:
        print("⬇️  找到种子文件，正在下载...")
        try:
            with page.expect_download(timeout=30000) as download_info:
                torrent_link.click()
            download = download_info.value
            save_path = os.path.join(download_dir, download.suggested_filename)
            download.save_as(save_path)
            print(f"🎉 种子已下载: {save_path}")
            return True
        except Exception as e:
            print(f"  ⚠️  种子下载失败: {e}")
    
    # 方法3：寻找"磁力下载"文字按钮
    magnet_text_btn = page.query_selector("a:has-text('磁力下载'), a:has-text('磁力链接')")
    if magnet_text_btn:
        btn_href = magnet_text_btn.get_attribute("href") or ""
        if "magnet:" in btn_href:
            magnet_file = os.path.join(download_dir, f"{keyword}_magnet.txt")
            with open(magnet_file, "w", encoding="utf-8") as f:
                f.write(btn_href)
            print(f"🧲 磁力链接已保存: {magnet_file}")
            return True
        else:
            # 可能需要点击后才能获取
            print(f"  📥 点击磁力按钮...")
            magnet_text_btn.click()
            time.sleep(2)
            # 再次检查页面是否出现了磁力链接
            new_magnet = page.query_selector("a[href*='magnet:']")
            if new_magnet:
                magnet_href = new_magnet.get_attribute("href")
                magnet_file = os.path.join(download_dir, f"{keyword}_magnet.txt")
                with open(magnet_file, "w", encoding="utf-8") as f:
                    f.write(magnet_href)
                print(f"🧲 磁力链接已保存: {magnet_file}")
                return True
    
    # 方法4：从页面文字中提取网盘链接（mini4k经常把链接写在文本描述里）
    cloud_links = page.evaluate("""
    () => {
        const text = document.body.innerText;
        const links = [];
        // 匹配百度网盘链接
        const baiduMatch = text.match(/https?:\/\/pan\.baidu\.com\/s\/[\w-]+(?:\?pwd=[\w]+)?/g);
        if (baiduMatch) baiduMatch.forEach(url => links.push({type: '百度网盘', url: url}));
        // 匹配夸克网盘链接
        const quarkMatch = text.match(/https?:\/\/pan\.quark\.cn\/s\/[\w]+/g);
        if (quarkMatch) quarkMatch.forEach(url => links.push({type: '夸克网盘', url: url}));
        // 匹配阿里云盘链接
        const aliMatch = text.match(/https?:\/\/www\.alipan\.com\/s\/[\w]+/g) || text.match(/https?:\/\/www\.aliyundrive\.com\/s\/[\w]+/g);
        if (aliMatch) aliMatch.forEach(url => links.push({type: '阿里云盘', url: url}));
        // 匹配迅雷网盘链接
        const xunleiMatch = text.match(/https?:\/\/pan\.xunlei\.com\/s\/[\w-]+/g);
        if (xunleiMatch) xunleiMatch.forEach(url => links.push({type: '迅雷网盘', url: url}));
        // 匹配115网盘链接
        const pan115Match = text.match(/https?:\/\/115\.com\/s\/[\w]+/g);
        if (pan115Match) pan115Match.forEach(url => links.push({type: '115网盘', url: url}));
        // 也检查 a 标签的 href
        document.querySelectorAll('a').forEach(a => {
            const href = a.getAttribute('href') || '';
            const label = a.innerText.trim();
            if (href.includes('pan.baidu.com')) links.push({type: '百度网盘', url: href});
            else if (href.includes('pan.quark.cn')) links.push({type: '夸克网盘', url: href});
            else if (href.includes('alipan.com') || href.includes('aliyundrive.com')) links.push({type: '阿里云盘', url: href});
            else if (href.includes('pan.xunlei.com')) links.push({type: '迅雷网盘', url: href});
            else if (href.includes('115.com/s/')) links.push({type: '115网盘', url: href});
        });
        // 去重
        const seen = new Set();
        return links.filter(l => {
            if (seen.has(l.url)) return false;
            seen.add(l.url);
            return true;
        });
    }
    """)
    
    if cloud_links:
        # 按用户会员优先级排序：百度/夸克 > 其他
        preferred = [l for l in cloud_links if any(p in l['type'] for p in PREFERRED_CLOUDS)]
        others = [l for l in cloud_links if not any(p in l['type'] for p in PREFERRED_CLOUDS)]
        sorted_links = preferred + others
        
        print(f"\n📦 找到 {len(sorted_links)} 个网盘链接:")
        for link in sorted_links:
            star = " ⭐" if any(p in link['type'] for p in PREFERRED_CLOUDS) else ""
            print(f"  🔗 [{link['type']}]{star}: {link['url']}")
        
        # 保存到文件
        cloud_file = os.path.join(download_dir, f"{keyword}_cloud_links.txt")
        with open(cloud_file, "w", encoding="utf-8") as f:
            for link in sorted_links:
                f.write(f"[{link['type']}] {link['url']}\n")
        print(f"\n💾 网盘链接已保存: {cloud_file}")
        return True
    
    # 方法5：提取页面中所有下载相关链接
    all_links = page.query_selector_all("a")
    download_links = []
    for link in all_links:
        link_href = link.get_attribute("href") or ""
        link_text = link.inner_text().strip()
        if any(kw in link_href.lower() or kw in link_text for kw in ["download", "下载", "magnet", "torrent"]):
            download_links.append(f"  {link_text}: {link_href}")
    
    if download_links:
        print(f"\n📎 页面中发现的下载相关链接:")
        for dl in download_links[:10]:
            print(dl)
        return True
    
    print("❌ 该种子详情页未找到可用的下载链接。")
    return False


# ============================================================
# 主流程
# ============================================================
def search_and_download(keyword: str, state_file: str, download_dir: str, headless: bool = True):
    if not os.path.exists(state_file):
        print(f"❌ 凭证文件不存在: {state_file}")
        print("   请先运行: python3 mini4k_auth.py")
        sys.exit(1)
    
    # 用剧名创建子文件夹
    download_dir = os.path.join(download_dir, keyword)
    os.makedirs(download_dir, exist_ok=True)
    
    print("=" * 55)
    print(f"🔍 Mini4k 种子搜索 | 关键词: 《{keyword}》")
    print(f"   下载目录: {download_dir}")
    print("=" * 55 + "\n")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=state_file,
            user_agent=USER_AGENT,
            accept_downloads=True,
        )
        page = context.new_page()
        
        try:
            # Step 1: 搜索
            detail_url = search_movie(page, keyword)
            if not detail_url:
                print(f"\n❌ 未找到 \"{keyword}\" 的搜索结果。")
                return
            
            # Step 2: 进入详情页
            print(f"\n📄 进入详情页: {detail_url}")
            page.goto(detail_url, timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(2)
            
            check_cf_block(page)
            
            # Step 3: 解析资源
            print("\n📊 解析资源列表...")
            resources = parse_detail_page(page, keyword)
            
            if not resources:
                print("\n❌ 详情页未找到任何可用资源。")
                return
            
            # Step 4: 排序
            ranked = rank_resources(resources)
            
            # 输出资源清单
            print(f"\n{'─' * 55}")
            print(f"📋 共找到 {len(ranked)} 个可用资源（已排除杜比视界）:")
            print(f"{'─' * 55}")
            for i, res in enumerate(ranked[:20], 1):
                res_tag = f"[{res['resolution']}]"
                sub_tag = "[中字]" if res["has_chs"] else ""
                type_tag = "[磁力]" if res["is_torrent"] else "[网盘]" if res["is_cloud"] else ""
                name_short = res["name"][:55]
                size_tag = f" ({res['size']})" if res["size"] else ""
                print(f"  {i:>2}. {res_tag}{sub_tag}{type_tag} {name_short}{size_tag}")
            
            # Step 5: 选择最佳资源并下载
            best = ranked[0]
            print(f"\n✅ 选中最佳资源:")
            print(f"   名称: {best['name'][:70]}")
            print(f"   分辨率: {best['resolution']} | 字幕: {'有中字' if best['has_chs'] else '无标注'}")
            print(f"   类型: {'磁力/种子' if best['is_torrent'] else '网盘' if best['is_cloud'] else '未知'}")
            
            # 下载
            success = download_torrent(page, best, download_dir, keyword)
            
            if not success and len(ranked) > 1:
                print("\n🔄 尝试下一个资源...")
                for alt in ranked[1:3]:
                    success = download_torrent(page, alt, download_dir, keyword)
                    if success:
                        break
            
            # 检查是否需要字幕建议（外国资源且无中字标注）
            if best and not best.get("has_chs", False):
                encoded_kw = quote(keyword)
                print(f"\n🔤 该资源未标注中文字幕，建议搜索字幕:")
                print(f"   1. 字幕库(Zimuku):    https://zimuku.org/search?q={encoded_kw}")
                print(f"   2. SubHD:             https://subhd.tv/search/{encoded_kw}")
                print(f"   3. 伪射手(Assrt):     https://assrt.net/sub/?searchword={encoded_kw}")
                print(f"   4. A4k字幕网:         https://www.a4k.net/search?term={encoded_kw}")
                print(f"   5. OpenSubtitles:     https://www.opensubtitles.org/zh/search/sublanguageid-chi/moviename-{encoded_kw}")
                print(f"   6. R3字幕网:          https://r3sub.com/search/{encoded_kw}")
                print(f"   7. ChineseSubFinder:  https://github.com/ChineseSubFinder/ChineseSubFinder (自动工具)")
                print(f"\n   💡 推荐优先使用 字幕库 或 SubHD，更新最快")
        
        except Exception as e:
            print(f"\n❌ 出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            browser.close()
            print("\n🛑 浏览器已关闭。")


def main():
    parser = argparse.ArgumentParser(
        description="Mini4k 种子搜索与下载 - 智能筛选纯净资源"
    )
    parser.add_argument("keyword", help="搜索关键词（影片名称）")
    parser.add_argument("--download-dir", default=DEFAULT_DOWNLOAD_DIR,
                        help=f"下载保存目录 (默认: {DEFAULT_DOWNLOAD_DIR})")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE,
                        help=f"auth_state.json 路径 (默认: {DEFAULT_STATE_FILE})")
    parser.add_argument("--no-headless", action="store_true",
                        help="有头模式（调试用）")
    args = parser.parse_args()
    
    search_and_download(
        keyword=args.keyword,
        state_file=args.state_file,
        download_dir=args.download_dir,
        headless=not args.no_headless,
    )


if __name__ == "__main__":
    main()
