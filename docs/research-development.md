# 台美股波段研究：規劃與首版操作

## 決策與範圍

2026-09-10：先建立可重現的訊號帳本、基準回測、影子投組及來源成效統計。
交易方向為台美股、持有數週至數月。首版是本機離線研究工具，不連券商、
不寄信、不部署、不改動現有摘要流程。使用標準函式庫，不增加安裝依賴。

不採用完整 Superpowers 開發流程；保留書面規格、可重現測試、差異檢查。
Skills 適合封裝重複的專業流程，並非開發的必要前提。此選擇不代表
較新模型能免除驗證，也不變更或移除使用者既有 skills。

## 已實作

1. `snapshot`：唯讀擷取 subscriptions.db 與摘要內容，寫入獨立 SQLite。
   記錄全文、原始名稱、ticker、情緒、來源、發布時間、快照時間及內容版本。
   UPDATE / DELETE 由 SQLite trigger 拒絕；相同內容重跑不新增，A→B→A 保留三版。
   舊模型／提示詞版本無法還原，明確記為 unknown，不宣稱擁有原始逐字稿引文。
2. `replay`：比較 MA20/60 趨勢與趨勢加看多訊號。每五個交易時段檢視一次，
   用前一交易日收盤資訊、下一交易日開盤模擬成交。看多只是候選訊號，
   不代表經驗證的優勢；同一標的有其他來源看空時，首版仍可能通過看多篩選。
3. 長倉、不槓桿、單標的目標最高 10%，剩餘保留現金。
   買賣成本分開指定，含手續費、稅、滑價的假設總和；沒有內建現行費率。
   賣出先於買入，買入預算包含成本。期末報酬扣除模擬平倉成本。
4. 回撤以模擬帳戶淨值高點計算：15% 總曝險上限 50%；25% 上限 25%
   且禁止買入；30% 停用並在下一開盤清倉，當次 replay 不自動恢復。
   這是把先前「新倉預算減半」具體化為更保守的總曝險限制。
   每日開盤／收盤檢查；沒有盤中價格。40% 是不可接受界線，不是可保證的損失上限。
5. 首次捕捉的看多觀點，追蹤 20/60 個完整交易時段淨報酬與相對基準報酬。
   未成熟回報 pending；缺行情回報 missing_prices。版本修訂不重複計分。
   來源均值只是描述統計，重疊樣本非獨立，自動權重調整保持關閉。
6. 報告包含行情、訊號、程式 SHA256、成本設定、交易、淨值、持倉與限制。
   同樣输入重跑使用同一報告，不能覆寫；全部輸出預設在 gitignored data/research。

## 操作

使用專案根目錄與既有 venv：

```bash
venv/bin/python -m backend.research --help
venv/bin/python -m backend.research snapshot --symbols data/research/symbols.json
venv/bin/python -m backend.research replay \
  --prices data/research/us-prices.csv --benchmark US:SPY \
  --buy-bps 10 --sell-bps 10
```

上述成本僅示範語法，必須換成實際券商／市場與滑價假設。
每次既有摘要流程完成後執行 snapshot。首版尚未掛入排程。

`symbols.json` 必須人工核對原始實體名稱與上市市場，例如：

```json
{"台積電": "TW:2330", "NVIDIA": "US:NVDA"}
```

ADR 與原股不自動視為同一商品。未映射標的保留在原始快照，但不進入策略。
發布時間缺少時區或只有日期者不參與訊號策略，待校正來源資料後重新捕捉。
內容發布超過 90 日不因補跑而變成近期訊號。快照時間不可由 CLI 回填。
修訂與刪除只從新快照時間生效。

行情 CSV 欄位：

```csv
symbol,open_at,close_at,adjusted_open,adjusted_close,currency
US:SPY,2026-09-08T13:30:00Z,2026-09-08T20:00:00Z,650,651,USD
US:NVDA,2026-09-08T13:30:00Z,2026-09-08T20:00:00Z,170,171,USD
```

價格僅為格式示例，不是真實行情。每次至少 61 個完整時段，前 60 日暖機。
同一檔案僅允許一個市場日曆與幣別，所有商品及基準必須有一致時段。
日光節約時間請由資料來源提供正確 UTC offset；不能把台美股同一日期合併。
不前填停牌、缺漏、下市或上市前價格；遇到不完整序列停止。

adjusted_open / adjusted_close 必須由相同供應商以同一公司行動調整尺度產生，
涵蓋拆股與股息，不能把原始開盤配上調整收盤。工具無法替代資料來源稽核。
模擬的是調整後合成單位，positions 不是可下單股數。台、美市場須分別執行；
尚不能合併成具匯率換算的真實帳戶。

## 驗收與測試

```bash
venv/bin/python -m pytest tests/test_research.py -q
```

測試涵蓋版本重跑／回復、禁止覆寫、修訂時序、舊內容排除、未來資料不改過去交易、
下一開盤執行、成本與現金守恆、回撤臨界值、跳空超標、停用後不得恢復買入、
缺價／重複／NaN 拒絕、報告重現與到期成效計算。

## 後續里程碑與晉升條件

夜間增量開發已完成下節列出的匯入、估值、驗證與儀表板介面。
以下里程碑中的歷史股票池、執行層及實盤升級條件仍未完成。

1. 資料層：加入可追溯行情來源、公司行動、歷史股票池與下市處理；
   新生成訊號保存模型／提示詞版本及原文證據。驗收：按當時可用資訊重建。
2. 投組層：產業與關聯曝險、台美股匯率及共同帳本、交易計畫與私有儀表板。
   驗收：部位、現金、入出金調整後淨值與對帳一致。
3. 進化層：預先登記候選策略、保留所有實驗、時序訓練／驗證／測試與重疊樣本隔離。
   驗收：扣成本樣本外增益、回撤與壓力測試共同達標；樣本不足維持舊版。
   禁止由進化引擎放寬風險上限。重複使用測試集後不得再稱獨立樣本外結果。
4. 實盤層：影子執行、券商訂單狀態機、去重、部分成交、重連、持倉對帳与停止開關。
   需另行確認券商、資金、記帳幣別及實盤授權。完成後才進入小額實盤。

現階段固定提供的股票池可能有選擇／倖存者偏誤，沒有產業、流動性與完整多市場風控，
不能作為实盤上線或獲利證明。尤其目前新建快照尚無成熟的事前追蹤績效，
不應用歷史發布日期替換快照時間，以製造回測績效。

## 夜間新增功能與一鍵驗收

`backend.research_market` 提供 fetch、fetch-fx、audit。沿用已安裝 yfinance，
只下載公開行情；保存 metadata、調整方式、公司行動和 SHA256。
TW/TWO 分別代表上市／上櫃。每日收盤以當地 23:59:59 才可用的保守時間標記，
不是聲稱真實交易所於該時刻收盤。當日未完結資料不匯入。
缺價格或不同時段序列直接拒絕，不填補；被拒絕股價保存為 .rejected.csv 供稽核。

```bash
venv/bin/python -m backend.research_market audit
venv/bin/python -m backend.research_market fetch \
  --symbols US:SPY US:NVDA US:AMD US:MSFT \
  --start 2024-01-01 --end 2026-09-10 --output data/research/us-new.csv
venv/bin/python -m backend.research_bundle \
  --prices data/research/us-new.csv --symbols data/research/symbols.json \
  --benchmark US:SPY --buy-bps 10 --sell-bps 10
```

bundle 依序保存快照、兩種策略回放、時序驗證、離線 HTML，最後寫 manifest.json。
每次建立新的時間戳資料夾；沒有 complete manifest 的 bundle 代表未完成。
成本是假設值，並非實際券商費率。全部研究產物預設留在 data/research，不部署。

`backend.research_validation`：180 交易時段訓練、60 時段隔離、60 時段測試，
比較固定兩個候選。只以訓練集的「淨報酬−最大回撤」選擇，
無交易資料的訊號候選不得因零報酬而勝出；另測雙倍成本。
每個切分重置帳戶，不能拼接當成連續實盤績效。結果是回溯研究，禁止自動晉升。

`backend.research_portfolio`：讀取各市場回放與 FX CSV，以資料時間點之前已知的
匯率換算共同記帳幣別；缺價、過期、錯誤權重或缺匯率直接拒絕。
初始權重代表共同起點配置，尚不支援入出金、換匯費用或跨市場再平衡。
帳戶回撤僅提供提示，不執行交易，因此不是完整帳戶風控。

```bash
venv/bin/python -m backend.research_market fetch-fx \
  --start 2025-07-01 --end 2026-09-10 --output data/research/usdtwd-new.csv
venv/bin/python -m backend.research_portfolio \
  --books data/research/books.json --fx data/research/usdtwd-new.csv \
  --base TWD --output data/research/combined-new.json
```

books.json 為陣列，每筆包含 report（回放 JSON 路徑，相對路徑以 books 所在資料夾為準）、
strategy（trend 或 trend_signal）、weight（正數且合計 1）。
FX CSV 欄位 currency,at,rate；rate 為每一單位外幣值多少記帳幣別，例如 USD 的 32 表示 1 USD=32 TWD。

`backend.research_dashboard`：產生可直接用瀏覽器開啟的單一 HTML，沒有外部 CDN，
可切換策略，查看交易、淨值、成熟度及時序驗證。訊號資料以文字方式渲染並防止 script 標籤注入。
可選 --portfolio 載入跨市場估值。曲線和統計不是風險曝險匹配的 alpha 評估。

早晨實際成果與資料品質問題記錄在本機 data/research/morning-report.md。
