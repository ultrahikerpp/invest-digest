---
title: 被遺忘的巨人重返巔峰？跨資料中心互連（DCI）成下一重點？ - 深入分析第48期：Nokia，Cisco
video_id: fomo-analysis-48
channel_id: fomo-newsletter
channel_name: FOMO研究院
source_type: newsletter
source_url: https://www.fomosoc.com/p/dci-48nokiacisco
published: 2026-05-20
processed: 2026-05-20
hashtags: #Nokia #DCI #AI基礎設施 #資料中心互連 #Cisco #FOMO研究院
industries: AI, 科技, 美股
---

# 被遺忘的巨人重返巔峰？跨資料中心互連（DCI）成下一重點？ - 深入分析第48期：Nokia，Cisco

🔗 [閱讀原文於 Substack](https://www.fomosoc.com/p/dci-48nokiacisco)

### 本期主題總覽



- AI 算力擴張的物理極限與 Scale-Across 概念的誕生

- AI 網路三層架構（Scale-up / Scale-out / Scale-across）解析

- 機器流量 vs. 人類流量的本質差異

- Nokia 的失落十五年與轉型歷程

- Nokia 三張關鍵牌：Infinera 整合、Nvidia 入股、資料中心交換器

- Cisco 的中年危機：從網路霸主到雲端化衝擊




---


### 各主題重點


#### AI 算力擴張的物理極限



- 作者認為，2026 年 AI 訓練目標已從 1 萬張 GPU 擴展至 10 萬乃至 100 萬個 XPU 等級的超級叢集，單一資料中心在土地、電力、散熱上已無法容納此規模

- 作者認為，現實解法是在同一區域內建置多座資料中心，再以高速、超寬頻的互連網路串接，使其在邏輯上運作如同一台超級電腦

- 作者認為，這個新的互連需求催生了「Scale-Across」這個全新的基礎設施類別，是整個 AI 算力競賽決勝點的轉移



#### AI 網路三層架構



- 作者認為，**Scale-up**（機架內 GPU 間通訊）是 Nvidia NVLink 的絕對主場，距離極短、追求極致頻寬

- 作者認為，**Scale-out**（同一資料中心內機架間通訊）透過乙太網路或 InfiniBand 串聯，是現行主流討論重心

- 作者認為，**Scale-across**（跨資料中心互連）是一個此前幾乎不存在的全新戰場，需在數十公里距離上提供極致頻寬、極低延遲與無損傳輸



#### 機器流量 vs. 人類流量



- 作者認為，傳統網路為「人類流量」設計，偶發的封包遺失或數十毫秒的延遲對使用者體驗影響甚微

- 作者認為，AI 訓練的「機器流量」是同步性極強的集體運算，任何一次封包遺失或延遲都會迫使整個百萬 GPU 叢集停擺等待

- 作者認為，這種「牽一髮而動全身」的特性，使得傳統廣域網路（WAN）或舊有 DCI 方案根本無法勝任 AI 訓練需求



#### Nokia 的失落十五年與轉型



- 作者認為，Nokia 手機帝國瓦解後，其電信與資料基礎設施業務始終存在，只是長期被忽視

- 作者認為，2016 年以 166 億美元併購 Alcatel-Lucent 的邏輯是合體挑戰華為與 Ericsson、搭上 5G 浪潮，但 5G 超級週期未如預期，Nokia 長年被市場貼上「穩定但缺乏想像力」的標籤

- 作者認為，Nokia 的 2026 年轉型在很大程度上是「被動式」的——是 AI 算力撞上物理極限，市場才赫然發現 Nokia 一直都在做 DCI 與光纖傳輸這門生意

- 作者認為，2025 年從 Intel 資料中心與 AI 事業群挖來的新執行長 Justin Hotard，是將 Nokia 底牌兌現的關鍵人物



#### Nokia 三張關鍵牌



- 作者認為，**第一張牌**是將 2024 年併購的 Infinera 武器化：Infinera 的客戶本就是 Google、Meta、Microsoft 等 Hyperscaler，Nokia 藉此完成從「賣給電信公司」到「賣給 AI 巨頭」的客戶結構根本性轉變

- 作者認為，**第二張牌**是 Nvidia 以 10 億美元入股 Nokia，背後邏輯是 AI-RAN（AI 原生無線接取網路）——將 GPU 放入電信基地台，讓停滯的 5G 投資獲得第二條 AI 變現路徑；但作者同時指出 AI-RAN 目前仍屬早期，2027 年才有第一個商業版本

- 作者認為，**第三張牌**是 Nokia 資料中心交換器 7220 IXR-H6 達到 102.4 Tb/s，首次正面挑戰 Cisco 與 Arista 的市場，促使 Nokia 將 2026 年 Network Infrastructure 成長指引從 6–8% 大幅上調至 12–14%



#### Cisco 的中年危機



- 作者認為，Cisco 的根本威脅來自「從地端走向雲端」的產業大遷移，使設備大買家從「全球數萬家企業 IT 部門」濃縮為「少數幾家 Hyperscaler」

- 作者認為，Hyperscaler 的採購邏輯與傳統企業截然不同——他們要的是最便宜、最開放、最大量，不需要 Cisco 昂貴的保固服務或封閉軟體系統

- 作者認為，Cisco 並非被動等待，而是在意識到威脅後花了十年時間默默打造應對武器庫（文章後續未提供，應為截斷內容）




---


### 核心觀點



- 作者認為，2026 年 AI 基礎設施競賽的瓶頸已從「GPU 算力本身」轉移至「誰能用最快的網路把 GPU 連起來」，Scale-Across 與 DCI 是這場競賽的新決勝戰場

- 作者認為，Nokia 與 Cisco 的投資價值重估，根源在於它們過去數十年深耕的光纖傳輸與網路設備技術，恰好精準對應了 AI 算力擴張所催生的全新需求，這是一種「時代鑰匙插入舊鎖」的結構性機遇

- 作者認為，AI-RAN 雖然長期想像空間巨大（讓電信業者的 5G 資本支出獲得 AI 第二春），但投資人必須留意其商業化時程仍在 2026–2027 年的早期驗證階段，不宜過度提前定價




---


### 提及標的


**公司**
Nokia、Cisco、Arista、Nvidia、Infinera（已被 Nokia 併購）、Alcatel-Lucent（已被 Nokia 併購）、Microsoft（含 Windows Phone 與 Azure）、Intel、Apple、Google（GCP）、Meta、Amazon（AWS）、T-Mobile、Ericsson、華為


**提及產業**
光纖傳輸設備、資料中心互連（DCI）、AI 網路基礎設施、電信設備、AI-RAN、資料中心交換器、半導體（XPU/GPU）



---


### 關鍵數據


| 數據 | 說明 |
| --- | --- |
| 1,500 億美元 | Nokia 2007 年高峰市值 |
| 150 億美元 | Nokia 手機業務崩跌後市值 |
| 72 億美元 | 2014 年 Nokia 手機部門出售給 Microsoft 的價格 |
| 166 億美元 | 2016 年 Nokia 併購 Alcatel-Lucent 金額 |
| 23 億美元 | 2024 年 Nokia 併購 Infinera 金額 |
| 10 億美元 | Nvidia 入股 Nokia 金額 |
| 3–4 歐元 | 2023 年底 Nokia 長期股價區間 |
| 200 億美元以下 | 2023 年底 Nokia 市值 |
| 5,500 億美元 | Cisco 2000 年 3 月盤中最高估值 |
| 90% | Cisco 泡沫破裂後兩年內股價跌幅 |
| 數百兆瓦（MW）至逼近 GW | 10 萬 GPU 資料中心的估計耗電量 |
| 102.4 Tb/s | Nokia 7220 IXR-H6 交換器吞吐量 |
| 12–14% | Nokia 2026 年 Network Infrastructure 業務上調後成長指引 |
| 6–8% | Nokia 原始成長指引（上調前） |
| 2027 年 | AI-RAN 預計首個商業版本時程 |



---


### 創作者建議的觀察方向


本期文章（截斷於 Cisco 章節前半段）中，作者明確或隱含建議關注以下方向：



- **Scale-Across / DCI 市場的競爭格局演變**：Nokia、Cisco、Arista 三方在資料中心交換器與跨資料中心互連市場的份額消長

- **Nokia 客戶結構轉變進度**：Hyperscaler（Google、Meta、Microsoft）在 Nokia 營收中的佔比提升速度，作為估值重估的核心驗證指標

- **AI-RAN 商業化里程碑**：2026 年商業試點結果、2027 年首個商業版本的落地情況，以及電信營運商採購意願

- **Cisco 的反擊策略**（文章後續未提供，但作者鋪陳明顯）：Cisco 花費十年打造的「武器庫」內容，是本期未完結的核心懸念

- **Hyperscaler 資本支出方向**：AI 訓練超大叢集的建置節奏，直接決定 DCI 與 Scale-Across 設備需求的成長速度