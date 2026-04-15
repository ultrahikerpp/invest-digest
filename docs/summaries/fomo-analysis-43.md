---
title: 下一個瓶頸是CPU？x86還是ARM？誰才是CPU概念股？ - 深入分析第43期：AMD，Intel，ARM
video_id: fomo-analysis-43
channel_id: fomo-newsletter
channel_name: FOMO研究院
source_type: newsletter
source_url: https://fomosoc.substack.com/p/cpux86armcpu-43amdintelarm
published: 2026-04-15
processed: 2026-04-15
hashtags: #投資 #財經 #重點摘要 #市場分析 #股市 #FOMO研究院
industries: AI, 半導體, 科技
---

# 下一個瓶頸是CPU？x86還是ARM？誰才是CPU概念股？ - 深入分析第43期：AMD，Intel，ARM

🔗 [閱讀原文於 Substack](https://fomosoc.substack.com/p/cpux86armcpu-43amdintelarm)

## 本期主題總覽



- CPU 需求復興的產業背景與驅動原因

- CPU vs GPU 的本質差異與歷史演進

- 三股引爆 CPU 需求的力量（推論時代、Agentic AI、RL 訓練）

- CPU 架構戰爭：x86 vs ARM，AMD EPYC vs Intel Xeon vs NVIDIA Grace/Vera

- 超大規模資料中心的 CPU 搶購潮與買家結構

- AMD、Intel、ARM Holdings 的投資定位分析




---


## 各主題重點


### CPU 需求復興的產業背景



- 2026 年 AI 資料中心的算力瓶頸已從 GPU 擴散至記憶體、光模塊、電力、散熱，而 CPU 是其中尚未被市場充分討論的機會。

- AMD CEO 蘇姿丰公開指出 EPYC 伺服器 CPU 需求「遠超預期」，交貨期拉長至 6 個月以上，並擁有 10–15% 的漲價定價權，是 CPU 復興最直接的市場訊號。

- Intel 伺服器 CPU 庫存於 2025 年底意外見底，甚至須將 PC 產線晶圓緊急轉供伺服器 CPU 生產，反映需求之急迫。

- 連 NVIDIA 自家 AI 基礎設施主管都公開承認「CPU 正在成為 Agentic 工作流的瓶頸」，具有極高說服力。




---


### CPU vs GPU 的本質差異與歷史演進



- KP 認為，CPU 的設計哲學是「通用性」，擅長處理複雜邏輯判斷與「If/Then」條件分支，如同十位頂尖大學教授，是系統的指揮官。

- GPU 原為遊戲畫面渲染而生，其核心優勢是以成千上萬個簡單核心進行「平行運算」，如同一萬名士兵同時執行相同動作。

- 2012 年科學家發現深度學習的底層數學（矩陣乘法）與畫像素的數學本質相同，這才讓 GPU 意外成為 AI 訓練的霸主。

- 過去十年 AI 突破建立在「把一切問題變成平行數學題」的基礎上，但 2026 年 AI 必須「走入現實世界做事」，單靠 GPU 已不足夠。

- GPU 是肌肉、CPU 是神經系統，當 AI 產業的肌肉已足夠強大，現在需要能指揮這些肌肉的強大 CPU。




---


### 三股引爆 CPU 需求的力量



- 第一股力量「推論時代」是量的爆炸——全球 AI 推論需求從每天數百萬次暴增至數十億次，每一次請求都需要 CPU 負責接收、排隊、Tokenization、格式化回傳等大量前後端工作。

- 第二股力量「Agentic AI」是質的翻轉——AI 不再只是單次問答，而是展開多步驟循環（規劃、呼叫工具、邏輯判斷、驗證），每個請求中 50% 至 90% 的工作量壓在 CPU 上，使單一請求的 CPU 工作量暴增 5 至 10 倍。

- Agentic AI 導致 GPU 機架內 CPU:GPU 比例從過去 1:8 劇變至 1:2 甚至 1:1，NVIDIA 最新 Vera Rubin NVL72 機架即配備 36 顆 CPU 對應 72 顆 GPU。

- 第三股力量「RL 訓練與合成資料」發生在 GPU 機架外部——AI 必須靠「自己跟自己練習」突破能力上限，需要 CPU 搭建大量虛擬模擬環境，同時開啟 10,000 至 100,000 個平行虛擬環境，CPU 擔任裁判與考場管理員。

- 推論數量爆炸與每個請求 CPU 工作量劇增是「相乘關係」，兩者交疊遠超華爾街分析師預測，這是 CPU 需求爆發的核心邏輯。




---


### CPU 架構戰爭：x86 vs ARM，三大廠商比較



- x86（AMD + Intel）的最大優勢是「無敵的軟體相容性」，數十年企業軟體皆為 x86 撰寫，但代價是歷史包袱重、較耗電。

- ARM 已從省電小玩具逆襲為效能怪物，蘋果 M 系列晶片顛覆市場認知後，AWS Graviton、Google Axion、微軟 Cobalt 及 NVIDIA Grace/Vera 全部採用 ARM 架構，核心驅動是資料中心的省電效益。

- AMD 的 Chiplet 積木架構使其能堆疊至 192 乃至 256 核，「人多好辦事」特性讓它成為 RL 模擬農場（純 CPU 平行任務）的絕對霸主。

- NVIDIA Vera 的 Monolithic 單體架構雖核心數僅 88 顆，但核心間幾乎零延遲，搭配 NVLink-C2C 私人高鐵（頻寬雙向 1.8 TB/s，為 PCIe 的 7 倍以上），讓 CPU 與 GPU 可共享記憶體，鎖定「GPU 機架內部超快大腦」的位置。

- 雲端巨頭採「混合部署」策略——最核心 GPU 機架搭配 NVIDIA Superchip，外圍龐大 CPU 支援農場則大量採購 AMD EPYC 與 Intel Xeon，市場非零和博弈，而是整體 TAM 擴張。




---


### 超大規模資料中心 CPU 搶購潮



- 儘管 NVIDIA 推出超強自研 CPU，AMD EPYC 在 2026 年依然賣到缺貨並強勢漲價，原因在於 RL 農場需要的是 AMD 擅長的「海量平行核心」，而非 NVIDIA 強項的「緊密耦合低延遲」。

- NVIDIA 自家旗艦 AI 伺服器 DGX Rubin NVL8 官方預設仍搭載 Intel Xeon x86 CPU，反映 x86 軟體生態系護城河之深，以及 NVIDIA CPU 產能受台積電先進封裝限制、無法大量供貨的現實。

- Agentic AI 創造了兩種截然不同的 CPU 需求：「與 GPU 緊密結合的超快大腦」由 NVIDIA 吃下，「在後勤瘋狂模擬的超級大軍」則由 AMD 與 Intel 吃下。




---


## 核心觀點



- 「AI = GPU」的大眾認知在 2026 年已過時；真正決定 AI 發展速度的下一個瓶頸是 CPU，而這個機會尚未被市場充分定價討論。

- 這場 CPU 復興並非零和競爭，而是整體市場規模擴張——NVIDIA、AMD、Intel 三者因架構差異而各踞不同生態位，投資者應依使用場景差異（緊密耦合推論 vs 平行模擬農場 vs 傳統軟體部署）來區分不同受益者。

- ARM 架構對 x86 長達 40 年壟斷的結構性侵蝕，是本波 CPU 趨勢中最深遠的長期投資邏輯，使得只靠收取設計授權版稅的 ARM Holdings 能坐享結構性紅利，而 AMD 與 Intel 則須靠軟體生態護城河與核心數優勢捍衛地盤。




---


## 提及標的


| 類別 | 名稱 |
| --- | --- |
| 個股 | AMD（Advanced Micro Devices） |
| 個股 | Intel |
| 個股 | ARM Holdings |
| 個股 | NVIDIA |
| 公司 | Apple（蘋果，M 系列晶片背景提及） |
| 公司 | AWS（Amazon Web Services，Graviton CPU） |
| 公司 | Google（Axion CPU） |
| 公司 | Microsoft 微軟（Cobalt CPU） |
| 公司 | OpenAI |
| 公司 | xAI |
| 公司 | Anthropic |
| 公司 | Meta |
| 產品/架構 | AMD EPYC（Turin、Venice） |
| 產品/架構 | Intel Xeon（Clearwater Forest） |
| 產品/架構 | NVIDIA Grace、Vera CPU |
| 產品/架構 | NVIDIA Vera Rubin NVL72、DGX Rubin NVL8 |



---


## 關鍵數據


| 數據 | 說明 |
| --- | --- |
| 6 個月以上 | AMD EPYC 伺服器 CPU 當前交貨等待期 |
| 10–15% | AMD EPYC 目前擁有的漲價定價權幅度 |
| 5–10 倍 | Agentic AI 使單一請求 CPU 工作量的暴增倍數 |
| 50–90% | Agentic AI 循環中壓在 CPU 的延遲與工作量佔比 |
| 1:8 → 1:2 或 1:1 | GPU 機架內 CPU:GPU 比例的劇變趨勢 |
| 36 顆 CPU / 72 顆 GPU | NVIDIA Vera Rubin NVL72 機架的 CPU/GPU 配置 |
| 88 核 | NVIDIA Vera CPU 核心數 |
| 192–256 核 | AMD EPYC 最高核心數 |
| 288 核（E-core） | Intel Xeon Clearwater Forest 核心數 |
| 雙向 1.8 TB/s | NVIDIA NVLink-C2C 頻寬 |
| PCIe 的 7 倍以上 | NVLink-C2C 相較傳統 PCIe 的頻寬優勢 |
| ARM 能效 1.5–2 倍 | NVIDIA Vera（ARM）相較 x86 在特定 AI 任務的能效優勢 |
| 256 顆 CPU / 1 機架 | NVIDIA Vera 純 CPU 機架規格，可同時運行 22,500+ 個平行 RL 環境 |
| 10,000–100,000 個 | RL 訓練時前沿實驗室同時開啟的平行虛擬環境數量 |
| 60–70% | 2026 年推論算力佔 AI 總算力之預測比例 |
| 2026 年 3 月 | NVIDIA GTC 大會，黃仁勳宣告「推論時代」全面降臨 |
| 2026 年 2 月 | SemiAnalysis 報告指出前沿 AI 實驗室 CPU 已不足以支撐 RL 訓練 |
| 2025 年底 | Intel 伺服器 CPU 庫存意外見底時間點 |



---


## 創作者建議的觀察方向


本次提供內容中，尚未明確點出具體的後續觀察指標，但從行文脈絡可歸納以下隱含觀察方向：



- 持續追蹤 AMD EPYC 的交貨期與漲價幅度，作為 CPU 需求強度的領先指標

- 觀察 NVIDIA Vera Rubin 機架的出貨規模，以及 CPU:GPU 配比的實際演變趨勢

- 留意各雲端巨頭（AWS、Google、Microsoft）在自研 ARM CPU 採購量上的季度揭露

- 關注 OpenAI、Anthropic、xAI、Meta 等前沿實驗室在純 CPU 伺服器農場的採購動態

- 第 5–7 章（AMD、Intel、ARM Holdings 的具體投資建議）為本期核心投資結論，建議閱讀完整版本