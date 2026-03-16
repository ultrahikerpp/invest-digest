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
runner.py run      →  新集數轉錄 + 摘要，寄送審閱通知信（僅此一次）
     ↓ （收到信後人工確認摘要內容）
runner.py approve  →  產生 hashtags + 字卡 + 影片，自動部署網站
```

---

## 常用指令

> **注意**：所有指令請使用 venv 的 Python，或先執行 `source venv/bin/activate` 啟動虛擬環境。

```bash
# 抓取所有頻道最新集數、轉錄、生成摘要，並寄送審閱通知信
./venv/bin/python runner.py run

# 只抓取特定頻道
./venv/bin/python runner.py run --channel <channel_id>

# 處理所有待審閱集數：產生 hashtags、字卡、影片，並自動部署網站
./venv/bin/python runner.py approve

# 重新產生靜態網站（docs/）
./venv/bin/python runner.py build

# 部署：build + commit + push 到 GitHub Pages
./venv/bin/python runner.py deploy

# 產生指定影片的摘要字卡 PNG
./venv/bin/python runner.py cards <video_id>

# 產生指定影片的摘要短影片 MP4
./venv/bin/python runner.py video <video_id>

# ── Shorts 短影音 ──

# 產生指定影片的 Shorts 9:16 字卡 PNG（hook + 各段落 + CTA）
./venv/bin/python runner.py shorts-cards <video_id>

# 組裝 Shorts 字卡成 MP4 短影音
./venv/bin/python runner.py shorts-video <video_id>

# 發送最新集數影片通知 Email
./venv/bin/python runner.py notify

# 驗證 Chrome 中的 claude.ai 登入狀態
./venv/bin/python runner.py setup-browser

# ── 標的分析 ──

# 對所有歷史摘要補跑分析（首次啟用時執行一次）
./venv/bin/python runner.py backfill-analysis

# 查看近 30 天熱門標的 Top 10 與產業熱度
./venv/bin/python runner.py trending
./venv/bin/python runner.py trending --days 60

# 查詢特定標的的所有提及紀錄
./venv/bin/python runner.py track --name 台積電

# 查看各頻道對同一標的的多空立場比較
./venv/bin/python runner.py divergence
./venv/bin/python runner.py divergence --days 180 --min-channels 2
```

---

## 標的追蹤與產業分類

每次 `run` 產生摘要後，會自動呼叫 Claude 對摘要進行二次萃取，識別提及的投資標的（含多空情緒）與產業標籤，並寫入資料庫與 frontmatter。

```bash
# 對所有歷史摘要補跑分析（一次性回填，首次啟用時執行）
./venv/bin/python runner.py backfill-analysis

# 查看近 30 天熱門標的 Top 10 與產業熱度
./venv/bin/python runner.py trending

# 指定天數範圍
./venv/bin/python runner.py trending --days 60

# 查詢特定標的的所有提及紀錄
./venv/bin/python runner.py track --name 台積電
./venv/bin/python runner.py track --name NVDA

# 查看各頻道對同一標的的多空立場比較（近 90 天，2+ 頻道）
./venv/bin/python runner.py divergence

# 調整時間範圍與最低頻道數
./venv/bin/python runner.py divergence --days 180 --min-channels 2
```

`build` / `deploy` 時會同步產生 `docs/data/mentions.json`，靜態網站的「📊 標的追蹤」頁面會顯示：
- 熱門標的排行榜（含看多／看空／中立比例）
- 產業熱度橫條圖
- 集數列表可按產業篩選

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
│   ├── claude_browser.py  # Claude AI 瀏覽器自動化（摘要、hashtags、字卡金句、標的萃取）
│   ├── analyzer.py        # 標的追蹤 DB 操作（mentions / episode_industries）
│   ├── card_generator.py  # 字卡 PNG 產生（Pillow）
│   └── video_maker.py     # 短影片 MP4 組裝
├── docs/                  # GitHub Pages 靜態網站
│   ├── index.html         # 單頁應用（SPA，Vanilla JS）
│   ├── summaries/         # Markdown 摘要（由 build_site.py 複製）
│   └── data/
│       ├── episodes.json  # 集數索引（由 build_site.py 產生）
│       └── mentions.json  # 標的與產業統計（由 build_site.py 產生）
└── data/
    ├── subscriptions.db   # SQLite（episodes / mentions / episode_industries）
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
- **兩階段工作流程**：`run` 產出摘要進入 `pending_review`，人工確認後執行 `approve` 產出字卡與影片並自動部署
- **SQLite 狀態追蹤**：`data/subscriptions.db` 記錄每集狀態（`pending_review` / `done`），以及 `mentions`、`episode_industries` 表儲存標的與產業分析結果

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
industries: 台股, ETF, 總體經濟
---
```

`industries` 欄位由 `run` 或 `backfill-analysis` 自動填入，最多 3 個，從固定清單選取：
台股、美股、中港股、半導體、AI、科技、金融、房地產、能源、原物料、生技醫療、ETF、總體經濟、加密貨幣、新興市場
