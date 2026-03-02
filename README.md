# Ultra Investment Digest

> YouTube 財經投資頻道自動摘要工具

每天自動抓取訂閱頻道的最新影片逐字稿，透過 Gemini AI 整理成結構化投資重點，部署為 GitHub Pages 靜態網站供瀏覽器查看。

---

## 快速開始

### 1. 安裝依賴套件

```bash
pip3 install -r requirements.txt
```

### 2. 設定 API Key

```bash
cp .env.example .env
# 編輯 .env，填入 GEMINI_API_KEY
```

---

## 常用指令

> **注意**：所有指令請使用 venv 的 Python，或先執行 `source venv/bin/activate` 啟動虛擬環境。

```bash
# 抓取所有頻道最新集數、轉錄、生成摘要
./venv/bin/python runner.py run

# 只抓取特定頻道
./venv/bin/python runner.py run --channel <channel_id>

# 重新產生靜態網站（docs/）
./venv/bin/python runner.py build

# 產生摘要字卡 PNG
./venv/bin/python runner.py cards <video_id>

# 產生摘要短影片 MP4
./venv/bin/python runner.py video <video_id>

# 發送最新集數影片通知 Email
./venv/bin/python runner.py notify

# 部署：build + commit + push 到 GitHub Pages
./venv/bin/python runner.py deploy
```

---

## 啟動本地預覽伺服器

```bash
cd docs && python3 -m http.server 8000
```

開啟瀏覽器前往 http://localhost:8000

---

## 設定每日自動批次執行（Crontab）

每天早上 8:00 自動執行，並將 log 寫入 `data/runner.log`：

```bash
# 開啟 crontab 編輯器
crontab -e
```

加入以下這行（請將路徑替換成實際專案路徑）：

```
0 8 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py run >> data/runner.log 2>&1
0 9 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py notify >> data/runner.log 2>&1
```

查看執行 log：

```bash
tail -f data/runner.log
```

---

## 專案結構

```
investment-digest/
├── runner.py              # 主 CLI（run / build / cards / video / deploy）
├── build_site.py          # 靜態網站產生器
├── channels.json          # 訂閱頻道設定
├── backend/
│   ├── worker.py          # 核心邏輯（RSS 抓取、轉錄、摘要）
│   ├── card_generator.py  # 字卡 PNG 產生
│   └── video_maker.py     # 短影片 MP4 組裝
├── docs/                  # GitHub Pages 靜態網站
│   ├── index.html         # 單頁應用（SPA）
│   └── data/
│       ├── episodes.json  # 集數索引（由 build_site.py 產生）
│       └── summaries/     # Markdown 摘要檔
└── data/
    ├── subscriptions.db   # SQLite（重複處理判斷）
    ├── summaries/         # Markdown 摘要（原始資料）
    ├── transcripts/       # Whisper 逐字稿（本機，不上傳）
    ├── cards/             # PNG 字卡（本機，不上傳）
    ├── videos/            # MP4 影片（本機，不上傳）
    └── runner.log         # 每日批次執行 log
```

---

## 摘要 Frontmatter 格式

```yaml
---
title: EP639 | 🐗
video_id: Y3UKwjPIVeE
channel_id: UC23rnlQU_qE3cec9x709peA
channel_name: Gooaye 股癌
published: 2026-02-27
processed: 2026-02-27
hashtags: "#台股 #ETF #升息 #通膨 #資產配置 #Gooaye股癌"
---
```
