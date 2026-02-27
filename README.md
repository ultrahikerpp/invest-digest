# Investment Digest 📈

> YouTube 投資頻道自動摘要工具

每天自動抓取訂閱頻道的最新影片字幕，透過 Claude AI 整理成結構化投資重點，用瀏覽器輕鬆查看。

---

## 快速開始

### 1. 安裝前置需求

```bash
# 確認 Python 3.8+
python3 --version

# 安裝套件
pip3 install -r requirements.txt
```

### 2. 設定 API Key（必要）

```bash
# 加到 ~/.zshrc 永久生效
echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

> API Key 取得：https://console.anthropic.com/

### 3. 啟動 APP

```bash
cd investment-digest
chmod +x start.sh
./start.sh
```

瀏覽器會自動開啟 http://localhost:8765

---

## 使用方式

### 訂閱頻道
1. 點擊上方 **「＋ 訂閱頻道」**
2. 輸入關鍵字搜尋（如「股感」「ETF」「財經M平方」）
3. 點擊 **「訂閱」** → APP 會立即抓取該頻道最新影片

### 查看摘要
- 點擊左側頻道可篩選
- 點擊任何影片卡片查看 AI 生成的投資重點
- 每份摘要包含：核心觀點、提及標的、關鍵數據、機會、風險

### 手動更新
- 點擊 **「⟳ 立即更新」** 手動觸發

---

## 每日自動排程（每天早上 8:00）

```bash
chmod +x start_scheduler.sh
./start_scheduler.sh
```

---

## 摘要格式

每份摘要存為 `data/summaries/<video_id>.md`，包含：

```
## 核心觀點
## 提及標的
## 關鍵數據
## 投資機會
## 風險提示
## 個人行動建議
```

---

## 目錄結構

```
investment-digest/
├── backend/
│   ├── main.py        # FastAPI 後端
│   ├── worker.py      # 抓取 + 摘要邏輯
│   └── scheduler.py   # 每日排程
├── frontend/
│   └── index.html     # Web UI
├── data/
│   ├── subscriptions.db  # SQLite 資料庫
│   ├── summaries/        # Markdown 摘要
│   └── transcripts/      # 原始逐字稿
├── start.sh              # 啟動 Web APP
├── start_scheduler.sh    # 啟動排程
└── requirements.txt
```

---

## 常見問題

**Q: 沒有字幕怎麼辦？**
APP 目前僅支援有字幕的 YouTube 影片。若頻道無字幕，該影片會被跳過。

**Q: 搜尋找不到頻道？**
可以直接輸入 YouTube 頻道 ID（格式：`UCxxxxxxxx`）後直接訂閱。

**Q: 要怎麼取得頻道 ID？**
在 YouTube 頻道頁面，URL 中 `/channel/` 後面的字串即為頻道 ID。
