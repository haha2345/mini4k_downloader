# Mini4k Downloader

自动化影视资源搜索和下载：豆瓣热榜 → Mini4k 搜索 → 种子/磁力下载 → qBittorrent 推送到 NAS。

## 功能

- 🎬 **豆瓣热榜聚合** — 国内/国外/最新上线分区展示
- 🔍 **Mini4k 智能搜索** — 自动搜索、筛选、下载种子/磁力/网盘链接
- 🛡️ **Cloudflare 绕过** — 有头浏览器手动登录 + 凭证持久化
- 📤 **qBittorrent 推送** — 自动推送到 qBit 下载到 NAS
- 🔤 **字幕源推荐** — 外国资源自动输出 7 个字幕站搜索链接

### 筛选规则（自动）
1. ❌ 排除杜比视界（DV Tab 跳过 + 文件名二检）
2. ⬆️ 分辨率优先：4K > 1080p > 720p
3. 🧲 种子/磁力优先于网盘
4. 🇨🇳 中文字幕优先
5. ⭐ 网盘：百度/夸克优先（用户会员）

---

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/mini4k_downloader.git
cd mini4k_downloader
```

### 2. 安装 Python 依赖

```bash
pip3 install -r requirements.txt
```

### 3. 安装 Chromium 浏览器引擎

```bash
python3 -m playwright install chromium
```

> **Linux (Ubuntu/Debian)** 需要额外安装系统依赖：
> ```bash
> sudo python3 -m playwright install-deps chromium
> ```
> 这会自动安装 `libnss3`, `libatk1.0`, `libgbm1` 等 Chromium 运行所需的系统库。

### 4. 配置 qBittorrent（可选）

确保 qBittorrent 已开启 Web UI：

- 打开 qBittorrent → 设置 → Web UI → 勾选"启用 Web 用户界面"
- 记住端口号（默认 8080）和用户名密码

然后运行配置向导：

```bash
python3 scripts/qbit_push.py setup
```

---

## 使用

### 查看豆瓣热榜

```bash
python3 scripts/douban_hot.py
```

### 首次登录 Mini4k

```bash
python3 scripts/mini4k_auth.py
```

> 会打开浏览器窗口，手动完成：过 Cloudflare 盾 → 登录 Mini4k。
> 登录成功后自动保存凭证到 `scripts/auth_state.json`。
>
> **Linux 无桌面环境说明**：需要 X11 或通过 SSH X 转发运行。
> 也可以在有桌面的机器上登录后，将 `auth_state.json` 复制到服务器。

验证凭证是否还有效：

```bash
python3 scripts/mini4k_auth.py --verify
```

### 搜索并下载

```bash
# 基本用法
python3 scripts/mini4k_search.py "太平年"

# 指定下载目录
python3 scripts/mini4k_search.py "怪奇物语" --download-dir ~/Downloads

# 调试模式（显示浏览器窗口）
python3 scripts/mini4k_search.py "飞行家" --no-headless
```

下载结果保存在 `下载目录/剧名/` 下：

```
~/Downloads/
├── 飞行家/
│   └── mv177399320014062205.torrent
├── 怪奇物语/
│   └── 怪奇物语_cloud_links.txt
└── 呼啸山庄/
    ├── 呼啸山庄_magnet.txt
    └── (字幕源搜索链接在终端输出)
```

### 推送到 qBittorrent

```bash
# 推送种子文件
python3 scripts/qbit_push.py torrent ~/Downloads/飞行家/xxx.torrent

# 推送磁力链接文件
python3 scripts/qbit_push.py magnet ~/Downloads/呼啸山庄/呼啸山庄_magnet.txt

# 推送磁力链接字符串
python3 scripts/qbit_push.py magnet "magnet:?xt=urn:btih:..."

# 指定 NAS 保存路径
python3 scripts/qbit_push.py torrent xxx.torrent --save-path /mnt/nas/movies
```

---

## 项目结构

```
mini4k_downloader/
├── scripts/
│   ├── douban_hot.py       # 模块一：豆瓣热榜（纯标准库）
│   ├── mini4k_auth.py      # 模块二：CF 绕过 + 登录（Playwright）
│   ├── mini4k_search.py    # 模块三：搜索 + 筛选 + 下载（Playwright）
│   └── qbit_push.py        # 模块四：qBittorrent 推送（纯标准库）
├── SKILL.md                # OpenClaw Skill 描述
├── requirements.txt        # Python 依赖
├── .gitignore
└── README.md
```

## 系统要求

|  | macOS | Ubuntu/Debian | 其他 Linux |
|--|-------|--------------|------------|
| Python | 3.9+ | 3.9+ | 3.9+ |
| Playwright | ✅ | ✅ (需 install-deps) | ✅ (需手动装库) |
| 浏览器引擎 | Chromium (自动) | Chromium (自动) | Chromium (自动) |
| qBittorrent | 可选 | 可选 | 可选 |

## 常见问题

**Q: 提示 Cloudflare 拦截怎么办？**
A: 凭证过期了，重新运行 `python3 scripts/mini4k_auth.py` 登录。

**Q: Linux 没有桌面环境怎么登录？**
A: 方法一：SSH X 转发 `ssh -X user@server`，然后运行 auth。
方法二：在其他有桌面的机器上运行 auth，把生成的 `auth_state.json` 复制过去。

**Q: qBittorrent 连接失败？**
A: 检查 Web UI 是否已启用，端口和密码是否正确。运行 `python3 scripts/qbit_push.py setup` 重新配置。

## License

MIT
