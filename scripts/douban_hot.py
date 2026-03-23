#!/usr/bin/env python3
"""
模块一：豆瓣实时热榜聚合 (Douban Hot List)
使用豆瓣 Rexxar API（与 douban.com/explore 页面一致）获取真实热门数据。
包含类型标签、评分等完整信息。

用法：
    python3 douban_hot.py
"""

import urllib.request
import urllib.parse
import json
import sys


# ============================================================
# API 配置
# ============================================================
# 此 API 与 https://movie.douban.com/explore 页面完全一致
REXXAR_BASE = "https://m.douban.com/rexxar/api/v2/subject/recent_hot"
# Rexxar API 需要 Referer 头，否则会 403
REXXAR_REFERER = "https://movie.douban.com/explore"

# 旧 API 仅用于剧集（Rexxar 对 TV 也有效，但旧 API 剧集数据已验证准确）
OLD_API_BASE = "https://movie.douban.com/j/search_subjects"


def fetch_rexxar(media_type: str, category: str, region: str = "全部", limit: int = 10) -> list:
    """
    调用豆瓣 Rexxar API（与 explore 页面一致）。
    
    Args:
        media_type: 'movie' 或 'tv'
        category: '热门', '最新', '豆瓣高分', '冷门佳片'
        region: '全部', '华语', '欧美', '韩国', '日本'
        limit: 返回条目数
    
    Returns:
        列表，每个元素包含 title, rating, card_subtitle, id 等
    """
    params = urllib.parse.urlencode({
        'start': 0,
        'limit': limit,
        'category': category,
        'type': region,
    })
    url = f"{REXXAR_BASE}/{media_type}?{params}"
    
    req = urllib.request.Request(url, headers={
        'User-Agent': (
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        ),
        'Referer': REXXAR_REFERER,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('items', [])
    except Exception as e:
        print(f"  ⚠️  Rexxar API [{category}/{region}] 失败: {e}", file=sys.stderr)
        return []


def fetch_old_api(type_str: str, tag_str: str, limit: int = 10) -> list:
    """旧 API，仅作为剧集数据的备用。"""
    encoded_tag = urllib.parse.quote(tag_str)
    url = (
        f"{OLD_API_BASE}?type={type_str}&tag={encoded_tag}"
        f"&sort=recommend&page_limit={limit}&page_start=0"
    )
    req = urllib.request.Request(url, headers={
        'User-Agent': (
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://movie.douban.com/'
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('subjects', [])
    except Exception as e:
        print(f"  ⚠️  旧 API [{tag_str}] 失败: {e}", file=sys.stderr)
        return []


# ============================================================
# 格式化输出
# ============================================================

def parse_subtitle(subtitle: str) -> dict:
    """
    解析 card_subtitle 字段。
    示例: "2025 / 中国大陆 / 剧情 喜剧 / 鹏飞 / 蒋奇明 李雪琴"
    返回: {"year": "2025", "region": "中国大陆", "genres": "剧情 喜剧", ...}
    """
    parts = [p.strip() for p in subtitle.split('/')]
    result = {}
    if len(parts) >= 1:
        result['year'] = parts[0]
    if len(parts) >= 2:
        result['region'] = parts[1]
    if len(parts) >= 3:
        result['genres'] = parts[2]
    if len(parts) >= 4:
        result['director'] = parts[3]
    if len(parts) >= 5:
        result['actors'] = parts[4]
    return result


def format_rexxar_item(index: int, item: dict) -> str:
    """格式化 Rexxar API 返回的条目。"""
    title = item.get('title', '未知')
    
    # 评分
    rating = item.get('rating', {})
    if rating and rating.get('value'):
        score = rating['value']
        rate_display = f"⭐ {score}"
    else:
        rate_display = "暂无评分"
    
    # 类型标签（从 card_subtitle 提取）
    subtitle = item.get('card_subtitle', '')
    info = parse_subtitle(subtitle)
    genres = info.get('genres', '')
    year = info.get('year', '')
    
    tags = []
    if year:
        tags.append(year)
    if genres:
        tags.append(genres)
    tag_str = f" [{' | '.join(tags)}]" if tags else ""
    
    return f"  {index}. 《{title}》 ｜ {rate_display}{tag_str}"


def format_old_item(index: int, item: dict) -> str:
    """格式化旧 API 返回的条目。"""
    title = item.get('title', '未知')
    rate = item.get('rate', '暂无')
    rate_display = f"⭐ {rate}" if rate and rate != '0' and rate != '' else "暂无评分"
    return f"  {index}. 《{title}》 ｜ {rate_display}"


def print_rexxar_section(emoji: str, title: str, items: list):
    """输出 Rexxar API 数据板块。"""
    print(f"\n{emoji} **{title}**")
    if not items:
        print("  （暂无数据）")
        return
    for i, item in enumerate(items, 1):
        print(format_rexxar_item(i, item))


def print_old_section(emoji: str, title: str, items: list):
    """输出旧 API 数据板块。"""
    print(f"\n{emoji} **{title}**")
    if not items:
        print("  （暂无数据）")
        return
    for i, item in enumerate(items, 1):
        print(format_old_item(i, item))


# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 50)
    print("🎬 豆瓣实时热榜 | Douban Hot List")
    print("   数据源: movie.douban.com/explore")
    print("=" * 50)

    # ==================== 国内篇 ====================
    print("\n" + "─" * 40)
    print("### 🇨🇳 【国内篇】近期最热 Top 10")
    print("─" * 40)

    # 剧集 - 旧 API（用户已验证准确）
    cn_tv = fetch_old_api('tv', '国产剧', 10)
    print_old_section("📺", "热门国产剧集 (Top 10)", cn_tv)

    # 电影 - Rexxar API（与 explore 页面一致）
    cn_movie = fetch_rexxar('movie', '热门', '华语', 10)
    print_rexxar_section("🎬", "热门华语电影 (Top 10)", cn_movie)

    # ==================== 国外篇 ====================
    print("\n" + "─" * 40)
    print("### 🌍 【国外篇】近期最热 Top 10")
    print("─" * 40)

    # 欧美剧集
    us_tv = fetch_old_api('tv', '美剧', 10)
    print_old_section("📺", "热门欧美剧集 (Top 10)", us_tv)

    # 日韩剧集
    kr_tv = fetch_old_api('tv', '日韩剧', 10)
    print_old_section("📺", "热门日韩剧集 (Top 10)", kr_tv)

    # 海外电影 - Rexxar API
    us_movie = fetch_rexxar('movie', '热门', '欧美', 10)
    print_rexxar_section("🎬", "热门欧美电影 (Top 10)", us_movie)

    # ==================== 最新上线 ====================
    print("\n" + "─" * 40)
    print("### 🆕 【尝鲜区】最新上线")
    print("─" * 40)

    # 最新电影 - Rexxar API（含类型数据）
    new_movie = fetch_rexxar('movie', '最新', '全部', 10)
    print_rexxar_section("🍿", "最新上线电影 (Top 10)", new_movie)

    # 最新剧集 - Rexxar API
    new_tv = fetch_rexxar('tv', '最新', '全部', 10)
    print_rexxar_section("📡", "最新上线剧集 (Top 10)", new_tv)

    print("\n" + "=" * 50)
    print("💡 看中哪部？告诉我片名，我去 Mini4k 帮你找种子！")
    print("=" * 50)


if __name__ == "__main__":
    main()
