# 每日持續影子帳戶

## 這次交付

新增 `backend.research_daily`：延續同一帳戶的現金、模擬持倉、淨值高點、
回撤及停用狀態，建立每日不可覆寫決策與成交紀錄。
新增 `backend.research_quality`：列出缺值／缺時段／重複／時區錯誤，並提供有稽核證據的同來源補值。

這是新的 `daily-shadow-v1` 策略版本：每日檢視 MA20/60，與原本每五交易時段檢視的
回測版本不同，兩者績效不能混用。仍只做多、單標的目標最多 10%、15/25/30% 帳戶回撤控制。
trend_signal 另要求已可用的近期看多觀點。原有停用帳戶不會因隔日重新執行而恢復。

## 使用

```bash
# 明確建立一個示範影子帳戶：100000 為模擬資金，不是使用者真實資產。
venv/bin/python -m backend.research_daily init \
  --account us-demo-daily --currency USD --initial-cash 100000 \
  --universe US:NVDA US:AMD US:MSFT --benchmark US:SPY \
  --strategy trend_signal --buy-bps 10 --sell-bps 10

# 自動下載、檢查、快照、處理每日帳戶、輸出計畫及儀表板。
venv/bin/python -m backend.research_daily run --account us-demo-daily --refresh

# 離線重跑指定的已驗證 CSV。
venv/bin/python -m backend.research_daily run \
  --account us-demo-daily --prices data/research/us-20260910.csv
```

帳戶名稱、幣別、股票池、策略、成本及初始資金一旦建立便固定；同設定重跑 init 可安全略過。
不同策略需要新帳戶，不能修改已發生的歷史。成本為使用者輸入的模擬假設，不是內建現行費率。
台股可用 TWD 配 TW/TWO 股票池建立另一帳戶；原股與 ADR 仍需明確區分。

每日輸出位於 `data/research/daily/<account>/daily.html` 與 `daily.json`。
SQLite 位於 `data/research/daily.db`。原始帳戶、session、attempts 都禁止 UPDATE / DELETE。
HTML/JSON 是可重建的最新檢視，SQLite 才是不可覆寫的來源。

## 執行規則

1. 第一次只用最新已完成時段建立初始估值與下一時段計畫，不回補歷史成交。
2. 下一次執行，只有「原決策早於開盤，而且只前進一個完整交易時段」才模擬成交。
   後來得知的訊號不會用來改寫該筆成交。
3. 同一交易時段重跑回傳原狀態，不重複交易、不更新舊決策；即使後來修訂觀點也不改舊計畫。
4. 漏跑多個交易時段或晚建計畫時，只更新估值與風控，不補造錯過的成交，再規劃下一時段。
5. 任何資料失敗留下 blocked attempt 並輸出原因；先前待執行計畫作廢。
   資料恢復後重新建立計畫，不能回頭補成交。
6. 新資料必須包含前次時段及之前 60 個時段的相同調整價，否則停止。
   拆股、除息後供應商改寫調整基準時需先完成持倉調整，不沿用舊合成單位。
7. 開盤與收盤估值監看風險；漏跑期間只追蹤可重建的風控變化，不虛構退出。
   30% 停用會保留至後續日期，下一份計畫要求退出。

資料 freshness 上限暫定四個曆日，沒有交易所日曆判斷能力；長假可能保守阻擋。
遇停牌／缺失資料，工具不能判定可成交，不以前值填補。交易價格仍是調整後合成單位，
不是券商可執行股數；不支援槓桿、入出金、公司行動帳務與真實帳戶對帳。

## 品質稽核與修復

```bash
venv/bin/python -m backend.research_quality check data/research/tw-20260910.rejected.csv
venv/bin/python -m backend.research_quality repair \
  --original data/research/tw-20260910.rejected.csv \
  --backup data/research/tw-refresh-20260910.csv \
  --output data/research/tw-repaired.csv
```

只有同來源 yfinance、明確 auto_adjust、檔案 SHA256 正確、完全相同時段集合，
且所有原本有效報價仍一致時，才允許以新快照補回原本的無效價格。
不能用未調整交易所原價直接補進調整價序列；不能刪除日期、補前值、
改寫原始檔或把未知缺日當休市。修復另存新檔，metadata 保存來源與每一欄改動。
若新資料仍有缺值或有效報價也被修訂，工具拒絕修復；這不是多供應商自動備援。

## 排程與尚未涵蓋的範圍

`run --refresh` 可供既有排程在摘要完成後呼叫，行情與決策更新步驟已串接。
本次沒有變更現有摘要排程或重新開啟夜間開發 heartbeat，也沒有寄信或連券商。
跨市場合併仍是既有估值模組；尚未做共同現金帳本、產業／關聯曝險或帳戶級執行控制。
來源權重、自動策略晉升需要後續事前樣本，沒有在此版本自動調整。

## 驗證

```bash
venv/bin/python -m pytest tests/test_research_daily.py tests/test_research_quality.py -q
```

涵蓋連續兩日現金／持倉、重跑冪等、來源帳本不可覆寫、晚到／漏跑計畫作廢、
資料失敗作廢待執行計畫、歷史調整價變動拒絕、停用跨日保留、同來源補值及來源指紋驗證。
