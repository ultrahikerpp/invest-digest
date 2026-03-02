# Ultra Investment Digest

> YouTube 財經投資頻道自動摘要工具

每天自動抓取訂閱頻道的最新影片，透過 Whisper 轉錄逐字稿、Claude AI 整理成結構化投資重點摘要與字卡，並部署為 GitHub Pages 靜態網站供瀏覽器查看。

---

## 快速開始

### 1. 安裝依賴套件

```bash
pip3 install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入 GMAIL_APP_PASSWORD（Gmail 應用程式密碼）
```

### 3. 設定 Claude 瀏覽器登入

本工具透過 Playwright 自動化操作 Chrome 瀏覽器，從 Chrome 讀取已登入的 claude.ai session cookies，**不需要輸入帳號密碼**。

```bash
# 確認 Chrome 已登入 claude.ai，然後執行驗證
./venv/bin/python runner.py setup-browser
```

---

## 日常工作流程

```
runner.py run       →  新集數轉錄 + 摘要，寄送審閱通知信
     ↓ （收到信後人工確認摘要內容）
runner.py approve   →  產生 hashtags + 字卡 + 影片，寄送完成通知信
     ↓
runner.py deploy    →  更新靜態網站並推送 GitHub Pages
```

---

## 常用指令

> **注意**：所有指令請使用 venv 的 Python，或先執行 `source venv/bin/activate` 啟動虛擬環境。

```bash
# 抓取所有頻道最新集數、轉錄、生成摘要，並寄送審閱通知信
./venv/bin/python runner.py run

# 只抓取特定頻道
./venv/bin/python runner.py run --channel <channel_id>

# 處理所有待審閱集數：產生 hashtags、字卡、影片，並寄送完成通知信
./venv/bin/python runner.py approve

# 重新產生靜態網站（docs/）
./venv/bin/python runner.py build

# 部署：build + commit + push 到 GitHub Pages
./venv/bin/python runner.py deploy

# 產生指定影片的摘要字卡 PNG
./venv/bin/python runner.py cards <video_id>

# 產生指定影片的摘要短影片 MP4
./venv/bin/python runner.py video <video_id>

# 發送最新集數影片通知 Email
./venv/bin/python runner.py notify

# 驗證 Chrome 中的 claude.ai 登入狀態
./venv/bin/python runner.py setup-browser
```

---

## 啟動本地預覽伺服器

```bash
cd docs && python3 -m http.server 8000
```

開啟瀏覽器前往 http://localhost:8000

---

## 設定每日自動批次執行（Crontab）

每天早上 8:30 自動執行 `run`，9:00 發送通知，log 寫入 `data/runner.log`：

```bash
# 開啟 crontab 編輯器
crontab -e
```

加入以下這行（請將路徑替換成實際專案路徑）：

```
30 8 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py run >> data/runner.log 2>&1
0  9 * * * cd /path/to/investment-digest && ./venv/bin/python runner.py notify >> data/runner.log 2>&1
```

查看執行 log：

```bash
tail -f data/runner.log
```

---

## 專案結構

```
investment-digest/
├── runner.py              # 主 CLI（run / approve / build / cards / video / deploy / notify）
├── build_site.py          # 靜態網站產生器
├── channels.json          # 訂閱頻道設定
├── backend/
│   ├── worker.py          # 核心邏輯（RSS 抓取、Whisper 轉錄、Email 通知）
│   ├── claude_browser.py  # Claude AI 瀏覽器自動化（摘要、hashtags、字卡金句）
│   ├── card_generator.py  # 字卡 PNG 產生（Pillow）
│   └── video_maker.py     # 短影片 MP4 組裝
├── docs/                  # GitHub Pages 靜態網站
│   ├── index.html         # 單頁應用（SPA，Vanilla JS）
│   ├── summaries/         # Markdown 摘要（由 build_site.py 複製）
│   └── data/
│       └── episodes.json  # 集數索引（由 build_site.py 產生）
└── data/
    ├── subscriptions.db   # SQLite（處理狀態追蹤與去重）
    ├── summaries/         # Markdown 摘要（原始資料，依頻道分資料夾）
    ├── transcripts/       # Whisper 逐字稿（本機，不上傳）
    ├── cards/             # PNG 字卡（本機，不上傳）
    ├── videos/            # MP4 影片（本機，不上傳）
    └── runner.log         # 每日批次執行 log
```

---

## 技術架構重點

- **無 YouTube Data API**：透過 RSS feed 抓取影片清單
- **無 Gemini / OpenAI API**：透過 Playwright 自動化操作 Chrome，讀取 Chrome 本機的 claude.ai session cookies，直接使用 Claude.ai 網頁介面產生摘要與金句
- **無 Web Server**：靜態 GitHub Pages；所有資料於建置時預先產生
- **摘要審閱流程**：`run` 產出摘要後進入 `pending_review` 狀態，人工確認後執行 `approve` 才產出字卡與影片
- **SQLite 去重**：`data/subscriptions.db` 追蹤每集處理狀態（`pending_review` / `done`）

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
hashtags: #台股 #ETF #升息 #通膨 #資產配置 #Gooaye股癌
---
```
