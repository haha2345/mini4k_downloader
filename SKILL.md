---
name: mini4k-downloader
description: 从豆瓣热榜获取影视推荐，在 Mini4k 搜索并下载种子/磁力链接，自动推送到 qBittorrent 下载到 NAS
---

# Mini4k 影视下载 Skill

自动化影视资源搜索和下载流程：豆瓣热榜 → Mini4k 搜索 → 种子/磁力下载 → qBittorrent 推送到 NAS。

## 前置依赖

```bash
pip3 install playwright
python3 -m playwright install chromium
```

## 文件结构

```
scripts/
├── douban_hot.py      # 模块一：豆瓣实时热榜聚合
├── mini4k_auth.py     # 模块二：CF 绕过 + Mini4k 登录鉴权
├── mini4k_search.py   # 模块三：Mini4k 搜索 + 筛选 + 下载
├── qbit_push.py       # 模块四：qBittorrent 推送
├── auth_state.json    # 登录凭证（自动生成）
└── qbit_config.json   # qBittorrent 配置（自动生成）
```

## 使用流程

### Step 1: 查看豆瓣热榜（可选）
```bash
python3 scripts/douban_hot.py
```
输出国内篇（国产剧 + 华语电影）、国外篇（欧美/日韩剧 + 海外电影）、尝鲜区。

### Step 2: 首次登录 Mini4k
```bash
python3 scripts/mini4k_auth.py
```
会打开浏览器，手动过 Cloudflare 盾并登录。登录成功后自动保存 `auth_state.json`。

验证凭证是否有效：
```bash
python3 scripts/mini4k_auth.py --verify
```

### Step 3: 搜索并下载
```bash
python3 scripts/mini4k_search.py "太平年"
python3 scripts/mini4k_search.py "怪奇物语" --download-dir ~/Downloads
python3 scripts/mini4k_search.py "飞行家" --no-headless  # 调试模式
```

筛选规则（自动执行）：
1. **排除杜比视界**（DV Tab 整体跳过 + 文件名二次检查）
2. **分辨率优先**：4K > 1080p > 720p
3. **下载方式优先**：种子/磁力 > 网盘
4. **中文字幕优先**
5. **网盘会员优先**：百度/夸克 > 其他

下载结果：
- 种子文件 → 保存 `.torrent` 到指定目录
- 磁力链接 → 保存 `{片名}_magnet.txt`
- 网盘链接 → 保存 `{片名}_cloud_links.txt`（百度⭐/夸克⭐ 优先）
- 外国资源无中字 → 自动输出 7 个字幕源搜索链接

### Step 4: 配置 qBittorrent（首次）
```bash
python3 scripts/qbit_push.py setup
```
配置 qBittorrent 的地址、端口、账号密码和 NAS 保存路径。

### Step 5: 推送到 qBittorrent
```bash
# 推送磁力链接
python3 scripts/qbit_push.py magnet "magnet:?xt=urn:btih:..."
python3 scripts/qbit_push.py magnet /path/to/片名_magnet.txt

# 推送种子文件
python3 scripts/qbit_push.py torrent /path/to/xxx.torrent

# 指定 NAS 保存路径
python3 scripts/qbit_push.py magnet "magnet:..." --save-path /mnt/nas/movies
```

## 完整一键流程示例

```bash
# 1. 搜索并下载种子
python3 scripts/mini4k_search.py "飞行家" --download-dir /tmp/torrents

# 2. 推送到 qBittorrent 下载到 NAS
python3 scripts/qbit_push.py torrent /tmp/torrents/xxx.torrent --save-path /mnt/nas/movies
# 或磁力链接
python3 scripts/qbit_push.py magnet /tmp/torrents/飞行家_magnet.txt --save-path /mnt/nas/movies
```

## 字幕源（外国资源自动提示）

| 序号 | 名称 | 特点 |
|------|------|------|
| 1 | 字幕库 (Zimuku) | ⭐ 更新最快 |
| 2 | SubHD | ⭐ 中英双语 |
| 3 | 伪射手 (Assrt) | 多语言 |
| 4 | A4k 字幕网 | 界面清爽 |
| 5 | OpenSubtitles | 海量数据 |
| 6 | R3 字幕网 | 台版字幕 |
| 7 | ChineseSubFinder | 自动化工具 |

## 注意事项

- `auth_state.json` 会过期，提示 Cloudflare 拦截时重新运行 `mini4k_auth.py`
- qBittorrent 需开启 Web UI（设置 → Web UI → 启用）
- Ubuntu VM 使用 `chromium`（非 chrome），已在脚本中配置
