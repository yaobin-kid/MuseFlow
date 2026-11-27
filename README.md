# MusicFlow · 全自动热门歌单聚合与音乐库管理系统

MusicFlow 是一套自托管的音乐自动化控制台：从网易云音乐、QQ 音乐、Spotify、Apple Music 采集榜单 → 跨平台交叉打分 → 高分准入 → Navidrome 去重 → 限流保护下的上游检索下载 → 标签/封面/歌词整理归档 → 自动扫库 → **自动在 Navidrome 生成并持续刷新歌单**。

一个容器即可跑起来，前端构建产物由 FastAPI 直接托管。

***

## 功能特性

- **账号登录**：JWT 鉴权，全部控制台接口需登录访问
- **多平台榜单**（可自由勾选调度）
  - 网易云音乐：热歌、飙升、新歌、原创、说唱
  - QQ 音乐：热歌、飙升、新歌、原创、Billboard、UK、日本、韩国、香港、台湾、内地
  - Spotify 官方 Top 50：Global / US / UK / Taiwan / Hong Kong / Japan / Korea / Singapore / Australia
  - Apple Music 每日 Top 50：US / GB / HK / TW / JP / KR / SG / CA / AU
- **跨平台交叉打分**：平台权重 + 排名分档 + 跨平台乘数 + 黑名单 + 自定义加减分规则，保存即重算
- **歌曲封面**：榜单、曲库与任务列表均展示封面，由上游封面 API 代理，异常时自动回退渐变封面
- **手动搜索直下**：跳过打分准入，仍检测 Navidrome 曲库，优先消耗上游配额
- **低分曲目手动补下**：在「数据源与打分」列表可直接对低分/被过滤曲目点击下载，复用自动下载的检索与整理流程
- **下载队列**：优先级队列、滑动窗口限流、失败重试/取消、进度与后处理状态实时推送
- **下载后处理**：自动写入标签、拉取仅歌词 API 保存 `.lrc`、拉取封面 API 并嵌入音频与专辑目录
- **Navidrome 去重**：Subsonic API 曲库索引同步，严格 / 宽松两种匹配模式，入库后触发扫库
- **Navidrome 歌单自动生成**：按平台各生成一个歌单（合并该平台所有榜单并去重），每次更新只保留最新曲目，新歌下载完成并扫库后自动刷新
- **实时看板**：配额仪表盘、抓取/去重/入库漏斗、跨平台重合度、音质分布、任务趋势、实时日志（WebSocket）
- **Webhook 通知**：通用 JSON / Telegram / Bark / 企业微信 / 钉钉 / Discord
- **演示模式**：`DEMO_MODE=true` 时首次启动自动生成示例数据，无网络也能完整体验界面
- **内置上游服务**：Docker 镜像基于 `ghcr.io/juneix/nas-music-kit`，同一容器内自动启动上游搜索/下载/歌词/封面 API（8080 内部端口），开箱即用

***

## 技术栈与架构

| 层  | 技术                                                       |
| -- | -------------------------------------------------------- |
| 后端 | Python 3.11+ · FastAPI · APScheduler · SQLite（aiosqlite） |
| 前端 | Vue 3 · Vite · Element Plus · ECharts                    |
| 部署 | 单容器：MusicFlow + 内置上游服务，前端构建产物由 FastAPI 托管在 `/`            |

```text
┌────────────────────────────┐
│  Vue3 控制台（SPA）         │
└─────────────┬──────────────┘
              │ /api  /ws
┌─────────────▼──────────────┐        ┌───────────────────────────┐
│ FastAPI (8000)             │──────► │ 内置上游服务 (8080)        │
│  ├─ 采集器（4 平台）        │ HTTP   │ 搜索/下载/歌词/封面        │
│  ├─ 打分引擎                │        │ 文件下载到 /music（只读）  │
│  ├─ 下载队列 + 限流         │        └───────────────────────────┘
│  ├─ 后处理（标签/封面/歌词）│
│  └─ Navidrome Subsonic 客户端│
└──────┬──────────────┬──────┘
       │              │
  SQLite /data    音乐库 /library ──► Navidrome
```

***

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

> **使用预构建镜像**：仓库已配置 GitHub Actions，每次推送到 `main` 会自动构建并推送 amd64 / arm64 多架构镜像：
>
> ```bash
> docker pull ghcr.io/yaobin-kid/museflow:latest
> ```
>
> 将 `docker-compose.yml` 中的 `build:` 段替换为 `image: ghcr.io/yaobin-kid/museflow:latest`，再执行 `docker compose up -d` 即可（无需本地构建环境）。

仅构建镜像不启动：

```bash
docker build -t museflow:latest .
# 或
docker compose build
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

***

## Docker Compose 配置

仓库根目录的 [docker-compose.yml](docker-compose.yml) 是**完整可直接运行**的版本，复制到 NAS 后无需额外查找配置：

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
      # 需要直接访问内置上游 Web 界面时，取消下一行注释
      # - "8080:8080"
    env_file:
      - .env
    environment:
      TZ: Asia/Shanghai
      DATA_DIR: /data
      TEMP_DOWNLOAD_DIR: /data/downloads/temp
      FINAL_MUSIC_DIR: /library
      RUN_UPSTREAM: "true"
      UPSTREAM_PORT: "8080"
    volumes:
      # 数据库、日志、临时文件
      - ./data:/data
      # 上游服务固定下载目录：MusicFlow 只读读取，不写入
      - ./music:/music
      # MusicFlow 整理后的音乐库，供 Navidrome 扫描
      - ./library:/library
```

### 目录约定（重要）

| 容器路径       | 宿主机路径       | 归属       | 说明                              |
| ---------- | ----------- | -------- | ------------------------------- |
| `/music`   | `./music`   | 上游服务专用   | 上游固定下载目录，MusicFlow **只读**读取，绝不写入 |
| `/library` | `./library` | MusicFlow | 最终音乐库（按歌手/专辑归档），Navidrome 只扫描这里 |
| `/data`    | `./data`    | MusicFlow | SQLite 数据库、日志、整理暂存文件            |

| 配置项                                         | 说明                                                  |
| ------------------------------------------- | --------------------------------------------------- |
| `build.args.NPM_REGISTRY` / `PIP_INDEX_URL` | 前端 / Python 依赖镜像源，国内网络建议保留                          |
| `ports`                                     | 左侧为宿主机端口，可改为 `"8080:8000"` 等                        |
| `FINAL_MUSIC_DIR=/library`                  | 必须与 `./library:/library` 挂载一致                       |
| `RUN_UPSTREAM` / `UPSTREAM_PORT`            | 内置上游开关与内部端口（默认 8080，仅容器内）                           |
| `./music:/music`                            | 改为 NAS 实际路径，例如 `/volume1/upstream-music:/music`     |
| `./library:/library`                        | 改为 NAS 实际路径，例如 `/volume1/museflow-library:/library` |

### 完整版：MusicFlow + Navidrome 一起部署

同一台 NAS 上直接使用下面的完整文件即可（Navidrome 只挂载 `/library` 只读扫描）：

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
      FINAL_MUSIC_DIR: /library
      RUN_UPSTREAM: "true"
      UPSTREAM_PORT: "8080"
    volumes:
      - ./data:/data
      - ./music:/music
      - ./library:/library

  navidrome:
    image: deluan/navidrome:latest
    container_name: navidrome
    restart: unless-stopped
    ports:
      - "4533:4533"
    environment:
      TZ: Asia/Shanghai
      ND_MUSICFOLDER: /library
      ND_SCANSCHEDULE: 1h
    volumes:
      - ./library:/library:ro
      - ./navidrome-data:/data
```

配套 `.env`（可直接复制，按注释修改密码即可）：

```ini
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
SECRET_KEY=change-me-to-a-long-random-string

DEMO_MODE=true
TZ=Asia/Shanghai

# 内置上游（保持默认即可）
RUN_UPSTREAM=true
UPSTREAM_PORT=8080
UPSTREAM_BASE_URL=http://127.0.0.1:8080
UPSTREAM_LOCAL_DOWNLOAD_DIR=/music
UPSTREAM_BITRATE=999
UPSTREAM_SOURCE_ORDER=netease,netease2,kuwo,joox,bilibili
UPSTREAM_COVER_PATH=/api/pic
UPSTREAM_LYRIC_PATH=/api/lyric

# 目录（与 compose 挂载保持一致，无需修改）
DATA_DIR=/data
TEMP_DOWNLOAD_DIR=/data/downloads/temp
FINAL_MUSIC_DIR=/library

# 打分（默认权重偏向 Spotify / Apple 英文热门）
MIN_DOWNLOAD_SCORE=75
WEIGHT_NETEASE=0.15
WEIGHT_QQ=0.15
WEIGHT_SPOTIFY=0.35
WEIGHT_APPLE=0.35
BLACKLIST_KEYWORDS=DJ,喊麦,伴奏,铃声,串烧

# Navidrome（修改为你的密码）
NAVIDROME_ENABLED=true
NAVIDROME_URL=http://navidrome:4533
NAVIDROME_USERNAME=admin
NAVIDROME_PASSWORD=你的Navidrome密码
NAVIDROME_MATCH_MODE=strict
NAVIDROME_AUTO_SCAN=true
NAVIDROME_SYNC_PLAYLISTS=true
NAVIDROME_SYNC_INTERVAL_MINUTES=60

# 定时任务
SCHEDULER_ENABLED=true
COLLECT_INTERVAL_MINUTES=360
```

> **内置上游说明**：镜像基于 `ghcr.io/juneix/nas-music-kit:latest`，容器启动时会先在内部 `8080` 启动上游服务（`/api/search`、`/api/download`、`/api/lyric`、`/api/cover`），再启动 MusicFlow。默认 `UPSTREAM_BASE_URL=http://127.0.0.1:8080`，无需额外部署上游容器；如需使用外部上游，设置 `RUN_UPSTREAM=false`、清空 `UPSTREAM_LOCAL_DOWNLOAD_DIR` 并修改 `UPSTREAM_BASE_URL`。
>
> **目录不要混用**：`/music` 是上游固定下载目录（不要修改，也不要让 Navidrome 扫描）；MusicFlow 会把整理后的文件复制到 `/library`，Navidrome 只扫描 `/library`。旧版本数据库中若音乐库仍指向 `/music`，启动时会自动迁移到 `/library`。
>
> `NAVIDROME_URL` 使用容器名，两个服务需在同一 Docker 网络（同一 compose 文件默认满足）；Navidrome 部署在别处时改成实际地址。

***

## 环境变量说明

复制 `.env.example` 为 `.env` 后修改。控制台「系统设置」中保存的配置会写入数据库并**优先于**环境变量默认值；点击「恢复环境变量默认值」可重置。

### 基础

| 变量                     | 默认值                | 说明                     |
| ---------------------- | ------------------ | ---------------------- |
| `APP_NAME`             | `MusicFlow`         | 应用名称                   |
| `HOST` / `PORT`        | `0.0.0.0` / `8000` | 监听地址与端口                |
| `TZ`                   | `Asia/Shanghai`    | 容器时区                   |
| `TIMEZONE`             | `Asia/Shanghai`    | 定时任务时区                 |
| `DATA_DIR`             | `./data`           | 数据目录（SQLite、日志、临时文件）   |
| `ADMIN_USERNAME`       | `admin`            | 登录账号                   |
| `ADMIN_PASSWORD`       | `admin123`         | 登录密码（**生产环境必须修改**）     |
| `SECRET_KEY`           | 内置示例值              | JWT 签名密钥（**生产环境必须修改**） |
| `TOKEN_EXPIRE_MINUTES` | `10080`            | 登录有效期（分钟，默认 7 天）       |
| `DEMO_MODE`            | `true`             | 演示模式：空库时生成示例数据         |
| `COLLECT_ON_STARTUP`   | `false`            | 启动后立即执行一次采集            |
| `CORS_ORIGINS`         | `*`                | 允许的跨域来源，逗号分隔           |

### 上游音源服务

| 变量                            | 默认值                                   | 说明                                                         |
| ----------------------------- | ------------------------------------- | ---------------------------------------------------------- |
| `UPSTREAM_BASE_URL`           | `http://127.0.0.1:8080`（镜像内）          | 上游搜索/下载服务地址，指向外部上游时改为其地址                                   |
| `UPSTREAM_TIMEOUT_SEC`        | `60`                                  | 上游请求超时（秒）                                                  |
| `UPSTREAM_BITRATE`            | `999`                                 | 期望码率（`999` 表示尽量取最高/Hi-Res）                                 |
| `UPSTREAM_SOURCE_ORDER`       | `netease,netease2,kuwo,joox,bilibili` | 上游音源优先级（仅支持 `netease`、`netease2`、`bilibili`、`joox`、`kuwo`） |
| `UPSTREAM_FILE_PATH_TEMPLATE` | `/music/{filename}`                   | 外部上游返回 JSON 文件名时，按此模板拼接音频地址                                |
| `UPSTREAM_LOCAL_DOWNLOAD_DIR` | `/music`（镜像内）                         | 内置上游下载目录（只读），MusicFlow 从这里复制文件；留空则走 HTTP 下载                 |
| `UPSTREAM_COVER_PATH`         | `/api/pic`                            | 上游「歌曲封面图片数据」接口路径（参数 `source`、`id`）                         |
| `UPSTREAM_LYRIC_PATH`         | `/api/lyric`                          | 上游「仅歌词下载」接口路径                                              |

### 内置上游进程（仅 Docker 镜像）

| 变量              | 默认值    | 说明                               |
| --------------- | ------ | -------------------------------- |
| `RUN_UPSTREAM`  | `true` | 是否在容器内启动内置上游服务；使用外部上游时设为 `false` |
| `UPSTREAM_PORT` | `8080` | 内置上游监听端口（仅容器内部，默认不对宿主机暴露）        |

### 网络与防风控

| 变量                         | 默认值                           | 说明                                            |
| -------------------------- | ----------------------------- | --------------------------------------------- |
| `PROXY_URL`                | 空                             | HTTP / SOCKS5 代理，例如 `http://192.168.1.2:7890` |
| `FLARESOLVERR_ENABLED`     | `false`                       | 是否启用 FlareSolverr 过盾                          |
| `FLARESOLVERR_URL`         | `http://flaresolverr:8191/v1` | FlareSolverr 地址                               |
| `FLARESOLVERR_TIMEOUT_SEC` | `60`                          | 过盾超时                                          |
| `COOLDOWN_BASE_SEC`        | `15`                          | 同平台歌单之间的基础冷却                                  |
| `COOLDOWN_JITTER_SEC`      | `10`                          | 冷却随机抖动上限                                      |

### 限流

| 变量                        | 默认值   | 说明          |
| ------------------------- | ----- | ----------- |
| `RATE_LIMIT_WINDOW_SEC`   | `300` | 滑动窗口长度（秒）   |
| `RATE_LIMIT_MAX_REQUESTS` | `50`  | 窗口内允许的上游请求数 |

### 动态打分

| 变量                   | 默认值              | 说明                          |
| -------------------- | ---------------- | --------------------------- |
| `MIN_DOWNLOAD_SCORE` | `75`             | 高分准入门槛，低于该分数不下载             |
| `WEIGHT_NETEASE`     | `0.15`           | 网易云权重                       |
| `WEIGHT_QQ`          | `0.15`           | QQ 音乐权重                     |
| `WEIGHT_SPOTIFY`     | `0.35`           | Spotify 权重（默认偏高以纳入英文热门）     |
| `WEIGHT_APPLE`       | `0.35`           | Apple Music 权重（默认偏高以纳入英文热门） |
| `BLACKLIST_KEYWORDS` | `DJ,喊麦,伴奏,铃声,串烧` | 黑名单关键词，逗号分隔                 |

### Navidrome

| 变量                                     | 默认值                     | 说明                                         |
| -------------------------------------- | ----------------------- | ------------------------------------------ |
| `NAVIDROME_ENABLED`                    | `false`                 | 启用 Navidrome 去重与歌单同步                       |
| `NAVIDROME_URL`                        | `http://navidrome:4533` | Navidrome 地址（Subsonic API 根）               |
| `NAVIDROME_USERNAME`                   | `admin`                 | Subsonic 用户名                               |
| `NAVIDROME_PASSWORD`                   | 空                       | Subsonic 密码                                |
| `NAVIDROME_MATCH_MODE`                 | `strict`                | 去重匹配：`strict`（歌手+歌名）/ `loose`（歌名优先）        |
| `NAVIDROME_AUTO_SCAN`                  | `true`                  | 入库后自动触发 Navidrome 扫库                       |
| `NAVIDROME_SYNC_PLAYLISTS`             | `true`                  | 索引同步成功后自动创建/刷新 Navidrome 歌单                |
| `NAVIDROME_PLAYLIST_PREFIX`            | `MusicFlow`              | 歌单名称前缀，最终名称形如 `MusicFlow · 网易云音乐`（一个平台一个歌单） |
| `NAVIDROME_PLAYLIST_REFRESH_DELAY_SEC` | `30`                    | 下载完成后等待扫库完成再刷新歌单的延迟（秒）                     |
| `NAVIDROME_SYNC_INTERVAL_MINUTES`      | `60`                    | 曲库索引 + 歌单定时刷新间隔                            |

### 目录

| 变量                  | 默认值                         | 说明                                    |
| ------------------- | --------------------------- | ------------------------------------- |
| `TEMP_DOWNLOAD_DIR` | `/data/downloads/temp`（镜像内） | 整理暂存目录：上游文件复制到此补标签/封面，入库后清空（不是上游下载目录） |
| `FINAL_MUSIC_DIR`   | `/library`（镜像内）             | MusicFlow 最终音乐库，Navidrome 只扫描该目录       |

### Webhook 通知

| 变量                | 默认值                                                   | 说明                                                                 |
| ----------------- | ----------------------------------------------------- | ------------------------------------------------------------------ |
| `WEBHOOK_ENABLED` | `false`                                               | 是否启用通知                                                             |
| `WEBHOOK_TYPE`    | `generic`                                             | `generic` / `telegram` / `bark` / `wecom` / `dingtalk` / `discord` |
| `WEBHOOK_URL`     | 空                                                     | 通知地址                                                               |
| `WEBHOOK_EVENTS`  | `job_completed,manual_download_completed,error_alert` | 订阅事件，逗号分隔                                                          |

### 定时任务

| 变量                         | 默认值    | 说明         |
| -------------------------- | ------ | ---------- |
| `SCHEDULER_ENABLED`        | `true` | 启用定时调度     |
| `COLLECT_INTERVAL_MINUTES` | `360`  | 榜单采集间隔（分钟） |

### Spotify

| 变量                       | 默认值  | 说明                                                                                      |
| ------------------------ | ---- | --------------------------------------------------------------------------------------- |
| `SPOTIFY_CLIENT_ID`      | 空    | Spotify 应用 Client ID（香港/台湾等市场需要）                                                        |
| `SPOTIFY_CLIENT_SECRET`  | 空    | Spotify 应用 Client Secret                                                                |
| `SPOTIFY_MARKET`         | `TW` | 默认市场                                                                                    |
| `SPOTIFY_PLAYLISTS_JSON` | 空    | 自定义歌单 JSON，覆盖内置 9 个 Top 50，如 `[{"id":"37i9dQZEVXbMDoHDwVN2tF","name":"Global Top 50"}]` |

***

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
7. **Navidrome 客户端**：在歌单页即可看到 `MusicFlow · 平台名` 的 4 个歌单，各平台所有榜单已合并去重，曲目始终保持最新。

***

## Navidrome 歌单同步机制

启用条件：`NAVIDROME_ENABLED=true` 且 `NAVIDROME_SYNC_PLAYLISTS=true`。

流程：

1. 采集完成后，高分曲目进入下载队列；
2. 每首曲目入库（标签、封面、歌词整理）后触发 Navidrome 增量扫库；
3. 等待 `NAVIDROME_PLAYLIST_REFRESH_DELAY_SEC` 秒后（默认 30 秒，等待扫库完成），自动刷新歌单；
4. 索引同步（手动或每小时定时）结束后同样会自动刷新歌单。

实现细节：

- 歌单名称：`{NAVIDROME_PLAYLIST_PREFIX} · {平台中文名}`，例如 `MusicFlow · 网易云音乐`；
- **一个平台只生成一个 Navidrome 歌单**：合并该平台所有已勾选榜单的曲目并按 `track_key` 去重，按各榜单中的最好名次排序；4 个平台最终只有 4 个歌单；
- 每次刷新会清空旧列表并写入当前最新曲目（未下载或曲库中不存在的曲目自动跳过），因此歌单只包含真正可播放的歌曲；
- 曲目通过 Subsonic `search3` 按「歌名 + 主歌手」匹配本地曲库中的 song id，匹配成功后写入索引缓存；
- 使用 Subsonic `createPlaylist`（带 `playlistId`）覆盖更新，实现「始终最新」；
- 本地 `navidrome_platform_playlists` 表记录平台与 Navidrome 歌单 id 的映射；若远端歌单被删除，会自动重建；
- 升级后首次同步会自动删除旧版本按单个榜单创建的歌单，避免 Navidrome 中堆积重复歌单。

前端「系统设置 → Navidrome」中可查看已同步歌单数与曲目数，并手动触发刷新。

***

## 上游 API 说明

| 接口                                      | 用途                                |
| --------------------------------------- | --------------------------------- |
| `GET /api/search`                       | 多源搜索，按 `UPSTREAM_SOURCE_ORDER` 聚合 |
| `GET /api/download`                     | 获取音频；可能直接返回音频流，或返回包含文件名的 JSON     |
| `GET {UPSTREAM_COVER_PATH}?source=&id=` | 歌曲封面图片数据                          |
| `GET {UPSTREAM_LYRIC_PATH}?source=&id=` | 仅歌词（LRC）                          |

MusicFlow 内置 `/api/cover` 代理封面接口，供浏览器 `<img>` 直接引用；上游不可用时前端自动回退为渐变首字封面。

自动下载的检索规则：`name` 参数只使用**歌曲名**（不含歌手），按 `UPSTREAM_SOURCE_ORDER` 从第一个音源开始逐个尝试；前一个音源没有匹配结果才尝试下一个（单个音源报错也会跳过），所有音源都失败才标记任务失败。

***

## 数据与目录结构

```text
data/
├─ museflow.db              # SQLite：配置、榜单、曲目、任务、日志、索引缓存
└─ downloads/temp/          # 整理暂存（补标签/封面，入库后清空）
library/                   # 最终音乐库（按 歌手/专辑/歌曲 归档，Navidrome 扫描此目录）
music/                     # 上游服务的下载目录（只读，MusicFlow 不写入）
backend/app/static/        # 前端构建产物（由 FastAPI 托管）
```

如需从演示数据切换到干净环境：删除 `data/museflow.db`（Docker 为挂载的 `./data/museflow.db`）后重启即可重新初始化。

***

## 常见问题

**Q：首次启动页面是空的 / 没有数据？**
默认 `DEMO_MODE=true` 会在空库时生成演示数据；若仍为空，请检查 `data` 目录是否可写，或查看容器日志。

**Q：接了真实平台却抓不到数据？**
确认 `DEMO_MODE=false`，并在「数据源」页勾选榜单。平台存在风控，建议配置代理（`PROXY_URL`）、保留冷却与限流参数。

**Q：Navidrome 里看不到歌单？**
依次检查：Navidrome 已启用且密码正确 → 索引有数据（「立即同步索引」）→ 歌单开关已打开 → Navidrome 已扫描到音乐文件。歌词/封面不存在的曲目不影响歌单生成。

**Q：Navidrome 歌单里歌曲不全？**
只包含已完成下载并已被 Navidrome 索引的曲目。若刚下载完成，请等待刷新延迟或点「刷新歌单」。

**Q：下载失败提示「所有音源均未找到匹配音源」？**
表示已按 `UPSTREAM_SOURCE_ORDER` 把所有音源都试过且没有匹配结果。上游 `source` 仅支持 `netease`、`netease2`、`bilibili`、`joox`、`kuwo`，可调整尝试顺序，或在「手动搜索」中用正确歌名/歌手重试。

**Q：修改了 `.env` 但没生效？**
控制台「系统设置」中的数据库配置优先级更高，「恢复环境变量默认值」后重启，或重新部署。

**Q：镜像里为什么同时有两个服务？**
运行时镜像基于 `ghcr.io/juneix/nas-music-kit`，容器入口会先在内部 `8080` 启动上游搜索下载服务，再在 `8000` 启动 MusicFlow。宿主机只需映射 `8000`；如需直接访问上游 Web 界面，可额外映射 `"8080:8080"`。

**Q：升级镜像后没有使用内置上游？**
若数据库中的上游地址仍是旧默认值 `https://music.gdstudio.xyz` 且未自定义，启动时会自动迁移到 `http://127.0.0.1:8080`。如果你手动改过配置，请在「系统设置 → 路径与上游服务」中改为 `http://127.0.0.1:8080`，或点击「恢复环境变量默认值」后重启。

**Q：任务一直停留在「下载中」？**
重启时会自动恢复状态为「排队中」的任务继续下载；正在下载/整理中的任务会被标记为失败（信息为「服务重启，任务已中断」），不会卡在下载中。失败的记录可在「任务队列」或「手动下载记录」中删除，或点「重试」重新入队。

**Q：数据源里显示「待下载」，但任务队列里没有？**
「待下载」表示对应下载任务已创建并入队，正常会在任务队列看到。若任务记录被删除或来自演示数据，启动时会自动把这些孤立状态恢复为「待处理」，可再次点击「下载」。

**Q：端口被占用？**
修改 `docker-compose.yml` 的 `ports`，例如 `"8080:8000"`。

***

## 支持项目

MusicFlow 完全开源免费，没有广告，也不会加入任何收费功能。如果它帮你省下了手动找歌、整理入库的时间，欢迎请作者喝杯咖啡：

<p align="center">
  <img src="static/wechat.png" alt="微信赞赏码" width="260" />
</p>

<p align="center"><sub>赞赏完全自愿，不影响任何功能。你的使用与反馈就是最大的支持。</sub></p>

***

## 免责声明

本项目仅用于个人自托管音乐库的自动化管理，采集与下载依赖第三方服务，请遵守各平台服务条款与当地法律法规，勿用于商业用途或大规模分发。
