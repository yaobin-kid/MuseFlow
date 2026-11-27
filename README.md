# MuseFlow · 全自动热门歌单聚合与音乐库管理系统

MuseFlow 是一套自托管的音乐自动化控制台：从网易云音乐、QQ 音乐、Spotify、Apple Music 采集榜单 → 跨平台交叉打分 → 高分准入 → Navidrome 去重 → 限流保护下的上游检索下载 → 标签/封面/歌词整理归档 → 自动扫库 → **自动在 Navidrome 生成并持续刷新歌单**。

一个容器即可跑起来，前端构建产物由 FastAPI 直接托管。

---

## 功能特性

- **账号登录**：JWT 鉴权，全部控制台接口需登录访问
- **多平台榜单**（可自由勾选调度）
  - 网易云音乐：热歌、飙升、新歌、原创、说唱
  - QQ 音乐：热歌、飙升、新歌、原创、Billboard、UK、日本、韩国、香港、台湾、内地
  - Spotify 官方 Top 50：Global / US / UK / Taiwan / Hong Kong / Japan / Korea / Singapore / Australia
  - Apple Music 每日 Top 50：US / GB / HK / TW / JP / KR / SG / CA / AU
- **跨平台交叉打分**：平台权重 + 排名分档 + 跨平台乘数 + 黑名单 + 自定义加减分规则，保存即重算
- **歌曲封面**：榜单、曲库与任务列表均展示封面，由上游封面 API 代理，异常时自动回退渐变封面
- **手动搜索直下**：跳过打分与去重，优先消耗上游配额
- **下载队列**：优先级队列、滑动窗口限流、失败重试/取消、进度与后处理状态实时推送
- **下载后处理**：自动写入标签、拉取仅歌词 API 保存 `.lrc`、拉取封面 API 并嵌入音频与专辑目录
- **Navidrome 去重**：Subsonic API 曲库索引同步，严格 / 宽松两种匹配模式，入库后触发扫库
- **Navidrome 歌单自动生成**：索引同步成功后，按已调度榜单创建/刷新同名歌单，每次更新只保留最新榜单曲目，新歌下载完成并扫库后自动刷新
- **实时看板**：配额仪表盘、抓取/去重/入库漏斗、跨平台重合度、音质分布、任务趋势、实时日志（WebSocket）
- **Webhook 通知**：通用 JSON / Telegram / Bark / 企业微信 / 钉钉 / Discord
- **演示模式**：`DEMO_MODE=true` 时首次启动自动生成示例数据，无网络也能完整体验界面

---

## 技术栈与架构

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ · FastAPI · APScheduler · SQLite（aiosqlite） |
| 前端 | Vue 3 · Vite · Element Plus · ECharts |
| 部署 | 单容器，前端构建产物由 FastAPI 托管在 `/` |

```text
┌────────────────────────────┐
│  Vue3 控制台（SPA）         │
└─────────────┬──────────────┘
              │ /api  /ws
┌─────────────▼──────────────┐
│ FastAPI                    │
│  ├─ 采集器（4 平台）        │
│  ├─ 打分引擎                │
│  ├─ 下载队列 + 限流         │
│  ├─ 后处理（标签/封面/歌词）│
│  └─ Navidrome Subsonic 客户端│
└──────┬──────────────┬──────┘
       │              │
  SQLite /data    音乐库 /music ──► Navidrome
```

---

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
git clone git@github.com:yaobin-kid/MuseFlow.git
cd MuseFlow
cp .env.example .env
# 编辑 .env：至少修改 ADMIN_PASSWORD、SECRET_KEY，并按需填写 Navidrome 连接信息
docker compose up -d --build
```

启动后访问 `http://<NAS-IP>:8000`，默认账号 `admin` / `admin123`。

常用命令：

```bash
docker compose logs -f          # 查看日志
docker compose restart          # 重启
docker compose down             # 停止并移除容器
docker compose up -d --build    # 修改代码或配置后重新构建
```

### 方式二：本地开发运行

环境要求：Python 3.11+、Node.js 18+。

```powershell
# 一键启动（自动创建虚拟环境、安装依赖、构建前端并启动）
.\start.ps1

# 或手动执行
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd ..\frontend
npm install
npm run build        # 产物输出到 backend/app/static

cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 <http://localhost:8000>，默认账号 `admin` / `admin123`。

> 前后端分离调试：`cd frontend && npm run dev`，Vite 已配置 `/api` 与 `/ws` 代理到后端。

---

## Docker Compose 配置

[docker-compose.yml](docker-compose.yml) 默认内容：

```yaml
services:
  museflow:
    build:
      context: .
      args:
        NPM_REGISTRY: https://registry.npmmirror.com
        PIP_INDEX_URL: https://pypi.tuna.tsinghua.edu.cn/simple
    image: museflow:latest
    container_name: museflow
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      TZ: Asia/Shanghai
      DATA_DIR: /data
      TEMP_DOWNLOAD_DIR: /data/downloads/temp
      FINAL_MUSIC_DIR: /music
    volumes:
      - ./data:/data
      # 将左侧修改为 NAS 上的实际音乐目录
      - ./music:/music
```

| 配置项 | 说明 |
| --- | --- |
| `build.args.NPM_REGISTRY` | 前端依赖镜像源，国内网络建议保留 |
| `build.args.PIP_INDEX_URL` | Python 依赖镜像源 |
| `ports` | 左侧为宿主机端口，按需改为 `8080:8000` 等 |
| `env_file` | 读取 `.env` 中的全部环境变量 |
| `DATA_DIR=/data` | SQLite 数据库、日志、临时下载文件目录（必须持久化） |
| `FINAL_MUSIC_DIR=/music` | 最终音乐库目录，需与音量挂载一致，并让 Navidrome 扫描同一目录 |
| `./data:/data` | 数据持久化挂载 |
| `./music:/music` | 音乐库挂载，改为 NAS 实际路径，例如 `/volume1/music:/music` |

**与 Navidrome 联动示例**（同一台 NAS）：

```yaml
services:
  navidrome:
    image: deluan/navidrome:latest
    restart: unless-stopped
    ports:
      - "4533:4533"
    environment:
      ND_MUSICFOLDER: /music
    volumes:
      - /volume1/music:/music
      - ./navidrome-data:/data
```

此时 MuseFlow 的 `.env` 中填写：

```ini
NAVIDROME_ENABLED=true
NAVIDROME_URL=http://navidrome:4533
NAVIDROME_USERNAME=admin
NAVIDROME_PASSWORD=你的Navidrome密码
NAVIDROME_SYNC_PLAYLISTS=true
```

> 两个容器需在同一 Docker 网络内（同一 compose 文件默认即可），`NAVIDROME_URL` 才可使用容器名访问。若 Navidrome 部署在别处，改为其可访问的地址与端口。

---

## 环境变量说明

复制 `.env.example` 为 `.env` 后修改。控制台「系统设置」中保存的配置会写入数据库并**优先于**环境变量默认值；点击「恢复环境变量默认值」可重置。

### 基础

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `MuseFlow` | 应用名称 |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 监听地址与端口 |
| `TZ` | `Asia/Shanghai` | 容器时区 |
| `TIMEZONE` | `Asia/Shanghai` | 定时任务时区 |
| `DATA_DIR` | `./data` | 数据目录（SQLite、日志、临时文件） |
| `ADMIN_USERNAME` | `admin` | 登录账号 |
| `ADMIN_PASSWORD` | `admin123` | 登录密码（**生产环境必须修改**） |
| `SECRET_KEY` | 内置示例值 | JWT 签名密钥（**生产环境必须修改**） |
| `TOKEN_EXPIRE_MINUTES` | `10080` | 登录有效期（分钟，默认 7 天） |
| `DEMO_MODE` | `true` | 演示模式：空库时生成示例数据 |
| `COLLECT_ON_STARTUP` | `false` | 启动后立即执行一次采集 |
| `CORS_ORIGINS` | `*` | 允许的跨域来源，逗号分隔 |

### 上游音源服务

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `UPSTREAM_BASE_URL` | `https://music.gdstudio.xyz` | 上游搜索/下载服务地址 |
| `UPSTREAM_TIMEOUT_SEC` | `60` | 上游请求超时（秒） |
| `UPSTREAM_BITRATE` | `999` | 期望码率（`999` 表示尽量取最高/Hi-Res） |
| `UPSTREAM_SOURCE_ORDER` | `netease,tencent,kugou,kuwo,migu,joox,spotify,apple` | 上游音源优先级 |
| `UPSTREAM_FILE_PATH_TEMPLATE` | `/music/{filename}` | 上游返回 JSON 文件名时，按此模板拼接音频地址 |
| `UPSTREAM_COVER_PATH` | `/api/pic` | 上游「歌曲封面图片数据」接口路径（参数 `source`、`id`） |
| `UPSTREAM_LYRIC_PATH` | `/api/lyric` | 上游「仅歌词下载」接口路径 |

### 网络与防风控

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PROXY_URL` | 空 | HTTP / SOCKS5 代理，例如 `http://192.168.1.2:7890` |
| `FLARESOLVERR_ENABLED` | `false` | 是否启用 FlareSolverr 过盾 |
| `FLARESOLVERR_URL` | `http://flaresolverr:8191/v1` | FlareSolverr 地址 |
| `FLARESOLVERR_TIMEOUT_SEC` | `60` | 过盾超时 |
| `COOLDOWN_BASE_SEC` | `15` | 同平台歌单之间的基础冷却 |
| `COOLDOWN_JITTER_SEC` | `10` | 冷却随机抖动上限 |

### 限流

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RATE_LIMIT_WINDOW_SEC` | `300` | 滑动窗口长度（秒） |
| `RATE_LIMIT_MAX_REQUESTS` | `50` | 窗口内允许的上游请求数 |

### 动态打分

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MIN_DOWNLOAD_SCORE` | `75` | 高分准入门槛，低于该分数不下载 |
| `WEIGHT_NETEASE` | `0.15` | 网易云权重 |
| `WEIGHT_QQ` | `0.15` | QQ 音乐权重 |
| `WEIGHT_SPOTIFY` | `0.35` | Spotify 权重（默认偏高以纳入英文热门） |
| `WEIGHT_APPLE` | `0.35` | Apple Music 权重（默认偏高以纳入英文热门） |
| `BLACKLIST_KEYWORDS` | `DJ,喊麦,伴奏,铃声,串烧` | 黑名单关键词，逗号分隔 |

### Navidrome

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NAVIDROME_ENABLED` | `false` | 启用 Navidrome 去重与歌单同步 |
| `NAVIDROME_URL` | `http://navidrome:4533` | Navidrome 地址（Subsonic API 根） |
| `NAVIDROME_USERNAME` | `admin` | Subsonic 用户名 |
| `NAVIDROME_PASSWORD` | 空 | Subsonic 密码 |
| `NAVIDROME_MATCH_MODE` | `strict` | 去重匹配：`strict`（歌手+歌名）/ `loose`（歌名优先） |
| `NAVIDROME_AUTO_SCAN` | `true` | 入库后自动触发 Navidrome 扫库 |
| `NAVIDROME_SYNC_PLAYLISTS` | `true` | 索引同步成功后自动创建/刷新 Navidrome 歌单 |
| `NAVIDROME_PLAYLIST_PREFIX` | `MuseFlow` | 歌单名称前缀，最终名称形如 `MuseFlow · 网易云音乐 · 热歌榜` |
| `NAVIDROME_PLAYLIST_REFRESH_DELAY_SEC` | `30` | 下载完成后等待扫库完成再刷新歌单的延迟（秒） |
| `NAVIDROME_SYNC_INTERVAL_MINUTES` | `60` | 曲库索引 + 歌单定时刷新间隔 |

### 目录

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TEMP_DOWNLOAD_DIR` | `./data/downloads/temp` | 临时下载目录 |
| `FINAL_MUSIC_DIR` | `./data/music_library` | 最终音乐库目录（Navidrome 需扫描同一目录） |

### Webhook 通知

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEBHOOK_ENABLED` | `false` | 是否启用通知 |
| `WEBHOOK_TYPE` | `generic` | `generic` / `telegram` / `bark` / `wecom` / `dingtalk` / `discord` |
| `WEBHOOK_URL` | 空 | 通知地址 |
| `WEBHOOK_EVENTS` | `job_completed,manual_download_completed,error_alert` | 订阅事件，逗号分隔 |

### 定时任务

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SCHEDULER_ENABLED` | `true` | 启用定时调度 |
| `COLLECT_INTERVAL_MINUTES` | `360` | 榜单采集间隔（分钟） |

### Spotify

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPOTIFY_CLIENT_ID` | 空 | Spotify 应用 Client ID（香港/台湾等市场需要） |
| `SPOTIFY_CLIENT_SECRET` | 空 | Spotify 应用 Client Secret |
| `SPOTIFY_MARKET` | `TW` | 默认市场 |
| `SPOTIFY_PLAYLISTS_JSON` | 空 | 自定义歌单 JSON，覆盖内置 9 个 Top 50，如 `[{"id":"37i9dQZEVXbMDoHDwVN2tF","name":"Global Top 50"}]` |

---

## 使用指南

1. **登录控制台** → 使用 `ADMIN_USERNAME` / `ADMIN_PASSWORD`。
2. **数据源**：勾选需要调度的榜单。同平台会串行抓取并加入随机冷却，避免触发风控。
3. **打分规则**：调整平台权重、跨平台乘数、准入门槛、黑名单与自定义加减分规则；保存后立即重算。
4. **手动采集**：点击「立即采集」，或等待定时任务。采集完成后高分曲目自动进入下载队列。
5. **下载队列**：查看下载/整理进度，可重试或取消任务。
6. **系统设置**：
   - 配置上游服务、限流、代理、目录；
   - 配置 Navidrome 连接，点击「测试连接」；
   - 点击「立即同步索引」可手动触发索引同步与歌单刷新；
   - 点击「刷新歌单」仅重建 Navidrome 歌单。
7. **Navidrome 客户端**：在歌单页即可看到 `MuseFlow · 平台 · 榜单名` 的歌单，曲目始终保持最新。

---

## Navidrome 歌单同步机制

启用条件：`NAVIDROME_ENABLED=true` 且 `NAVIDROME_SYNC_PLAYLISTS=true`。

流程：

1. 采集完成后，高分曲目进入下载队列；
2. 每首曲目入库（标签、封面、歌词整理）后触发 Navidrome 增量扫库；
3. 等待 `NAVIDROME_PLAYLIST_REFRESH_DELAY_SEC` 秒后（默认 30 秒，等待扫库完成），自动刷新歌单；
4. 索引同步（手动或每小时定时）结束后同样会自动刷新歌单。

实现细节：

- 歌单名称：`{NAVIDROME_PLAYLIST_PREFIX} · {平台中文名} · {榜单名}`，例如 `MuseFlow · 网易云音乐 · 热歌榜`；
- 每个已勾选榜单对应一个 Navidrome 歌单，仅包含**本次榜单**的曲目（重新采集会清空旧列表，只保留最新排名曲目）；
- 曲目通过 Subsonic `search3` 按「歌名 + 主歌手」匹配本地曲库中的 song id，匹配成功后写入索引缓存；
- 使用 Subsonic `createPlaylist`（带 `playlistId`）覆盖更新，实现「始终最新」；
- 本地 `navidrome_playlists` 表记录本地榜单与 Navidrome 歌单 id 的映射；若远端歌单被删除，会自动重建；
- 尚未下载或曲库中不存在的曲目会被自动跳过，因此歌单只包含真正可播放的歌曲。

前端「系统设置 → Navidrome」中可查看已同步歌单数与曲目数，并手动触发刷新。

---

## 上游 API 说明

| 接口 | 用途 |
| --- | --- |
| `GET /api/search` | 多源搜索，按 `UPSTREAM_SOURCE_ORDER` 聚合 |
| `GET /api/download` | 获取音频；可能直接返回音频流，或返回包含文件名的 JSON |
| `GET {UPSTREAM_COVER_PATH}?source=&id=` | 歌曲封面图片数据 |
| `GET {UPSTREAM_LYRIC_PATH}?source=&id=` | 仅歌词（LRC） |

MuseFlow 内置 `/api/cover` 代理封面接口，供浏览器 `<img>` 直接引用；上游不可用时前端自动回退为渐变首字封面。

---

## 数据与目录结构

```text
data/
├─ museflow.db              # SQLite：配置、榜单、曲目、任务、日志、索引缓存
└─ downloads/temp/          # 临时下载文件
music_library/             # 最终音乐库（按 歌手/专辑/歌曲 归档）
backend/app/static/        # 前端构建产物（由 FastAPI 托管）
```

如需从演示数据切换到干净环境：删除 `data/museflow.db`（Docker 为挂载的 `./data/museflow.db`）后重启即可重新初始化。

---

## 常见问题

**Q：首次启动页面是空的 / 没有数据？**
默认 `DEMO_MODE=true` 会在空库时生成演示数据；若仍为空，请检查 `data` 目录是否可写，或查看容器日志。

**Q：接了真实平台却抓不到数据？**
确认 `DEMO_MODE=false`，并在「数据源」页勾选榜单。平台存在风控，建议配置代理（`PROXY_URL`）、保留冷却与限流参数。

**Q：Navidrome 里看不到歌单？**
依次检查：Navidrome 已启用且密码正确 → 索引有数据（「立即同步索引」）→ 歌单开关已打开 → Navidrome 已扫描到音乐文件。歌词/封面不存在的曲目不影响歌单生成。

**Q：Navidrome 歌单里歌曲不全？**
只包含已完成下载并已被 Navidrome 索引的曲目。若刚下载完成，请等待刷新延迟或点「刷新歌单」。

**Q：下载失败提示「上游未找到匹配音源」？**
上游音源覆盖有限，可调整 `UPSTREAM_SOURCE_ORDER`，或在「手动搜索」中用正确歌名/歌手重试。

**Q：修改了 `.env` 但没生效？**
控制台「系统设置」中的数据库配置优先级更高，「恢复环境变量默认值」后重启，或重新部署。

**Q：端口被占用？**
修改 `docker-compose.yml` 的 `ports`，例如 `"8080:8000"`。

---

## 免责声明

本项目仅用于个人自托管音乐库的自动化管理，采集与下载依赖第三方服务，请遵守各平台服务条款与当地法律法规，勿用于商业用途或大规模分发。
