---
title: HBM DRAM不夠用？NVIDIA 記憶體分層革命? SSD當記憶體？ - 深入分析第53期：NAND Flash控制器 (慧榮 SIMO，群聯)
video_id: fomo-analysis-53
channel_id: fomo-newsletter
channel_name: FOMO研究院
source_type: newsletter
source_url: https://www.fomosoc.com/p/hbm-dramnvidia-ssd-53nand-flash-simo
published: 2026-06-24
processed: 2026-06-24
hashtags: #KVCache #NAND控制器 #NVIDIA #HBM #慧榮SIMO #FOMO研究院
industries: 半導體, AI, 科技
---

# HBM DRAM不夠用？NVIDIA 記憶體分層革命? SSD當記憶體？ - 深入分析第53期：NAND Flash控制器 (慧榮 SIMO，群聯)

🔗 [閱讀原文於 Substack](https://www.fomosoc.com/p/hbm-dramnvidia-ssd-53nand-flash-simo)

### 本期主題總覽



- AI 推理工作流程：Prefill 與 Decode 兩階段運作原理

- KV Cache 的記憶體需求與 HBM 容量危機

- 預填與解碼分離（Disaggregation）新架構方向

- 記憶體金字塔層級與 DRAM 飢荒成因

- NVIDIA CMX 平台（記憶體分層架構）解析

- NAND Flash 與 DRAM 的物理本質差異

- 裸 NAND 三大缺陷與 SSD 控制器的必要性

- 儲存架構從消費級、資料中心到 AI 時代的演進




---


### 各主題重點


#### AI 推理工作流程：Prefill 與 Decode



- 作者認為，AI 推理可拆分為「預填（Prefill）」與「解碼（Decode）」兩個性質截然不同的階段，前者可高度平行運算，GPU 利用率極高；後者只能逐字生成，GPU 主要在等待資料搬運。

- 作者認為，Decode 階段的瓶頸不在算力，而在於能以多快的速度將 KV Cache 搬運至運算單元。

- 作者認為，KV Cache 是一種「以空間換時間」的機制，記錄 AI 讀過每個字所產生的中間結果，避免每次生成新字都需重讀整段輸入。

- 作者認為，KV Cache 的體積遠超想像，光是幾千字的對話就可能超過 1GB，乘上長上下文與大量並發用戶，HBM 容量瞬間耗盡。




---


#### KV Cache 危機與兩種應對方式



- 作者認為，當 HBM 裝不下 KV Cache 時，工程師面臨「丟棄舊筆記」或「尋找分層儲存方案」兩條路，而重新運算的代價遠高於調閱儲存資料。

- 作者認為，業界正朝「預填與解碼分離（Prefill/Decode Disaggregation）」架構發展，將兩類工作拆分至不同伺服器，各司其職。

- 作者認為，分離架構雖解決了算力分配問題，卻衍生出 KV Cache 必須在不同伺服器間高速傳輸的新難題，問題本質仍是「龐大的 KV Cache 該存在哪裡」。




---


#### 記憶體金字塔與 DRAM 飢荒



- 作者認為，AI 系統的儲存層級由快到慢可分為 HBM（極快、極貴、容量小）、DRAM（快但有限）、NAND SSD（慢但便宜且容量大）三層。

- 作者認為，HBM 製造工藝極其複雜，每生產 1GB HBM 約消耗傳統 DDR5 三倍的晶圓產能，導致大量產能被 HBM 吸走，進而造成標準 DRAM 結構性短缺與價格飆漲。

- 作者認為，面對「高速記憶體又貴又缺」的現實，整個晶片產業已形成共識：讓便宜、大容量的 SSD 扮演原本由 DRAM 負責的角色。




---


#### NVIDIA CMX 平台解析



- 作者認為，NVIDIA 提出的 CMX（Context Memory Storage）平台，是在 DRAM（G2）與傳統硬碟之間新增一個「G3.5」記憶體層，由高速 NVMe SSD 陣列構成，專門承接海量 KV Cache。

- 作者認為，CMX 平台由四大角色協同運作：NVIDIA Dynamo／NIXL 負責預判並預載資料；BlueField-4 DPU 負責資料傳輸且不佔用主機 CPU；NVIDIA Grove 負責將任務分配至離資料最近的機櫃；Spectrum-X 乙太網路則提供極低延遲的高頻寬連接。

- 作者認為，CMX 平台的核心價值在於讓 HBM 只保留最核心的模型與當下 KV Cache，大幅釋放 GPU 算力；同時藉由預載機制（Prestage）讓資料傳輸對 GPU 近乎無感。

- 作者認為，CMX 平台的共享架構使同一機櫃內的所有 GPU 都能調閱彼此存放的脈絡資料，實現跨 GPU 的無縫接力，避免重新計算。




---


#### NAND Flash 與 DRAM 的物理本質差異



- 作者認為，DRAM 追求極致速度，結構上只能「蓋平房」，因此容量小、造價昂貴；NAND Flash 可垂直堆疊（3D NAND），如同「蓋摩天大樓」，容量大、單位成本僅 DRAM 的幾十分之一。

- 作者認為，現今 NAND 技術已可輕鬆疊至 200 至 300 層以上，使其在相同晶圓面積上能提供遠超 DRAM 的儲存密度。

- 作者認為，DRAM 可由處理器直接定址存取，無需中介；NAND 則因物理特性充滿缺陷，必須依賴控制器晶片與 FTL 軟體才能穩定使用。




---


#### 裸 NAND 三大缺陷與 SSD 控制器



- 作者認為，裸 NAND 存在三大根本缺陷：反覆寫入造成磨損報廢、無法以最小單位覆寫（需整塊擦除）、隨時間累積產生位元錯誤（Bit Error）。

- 作者認為，SSD 控制器與 FTL 軟體扮演「超級騙子兼翻譯官」的角色，透過平均抹寫（Wear Leveling）、垃圾回收（Garbage Collection）及錯誤修正（ECC）三大機制，將問題重重的裸 NAND 包裝成可靠的儲存產品。

- 作者認為，當業界希望 SSD 承擔更多原本由 DRAM 負責的工作時，控制器的能力高低便成為決定成敗的關鍵因素。




---


#### 儲存架構的歷史演進



- 作者認為，儲存架構歷經消費級零售時代、傳統資料中心時代與 AI 時代三個階段，每個階段對儲存的需求性質都有根本性的改變。

- 文章在提供的節錄中對此章節僅呈現框架，第一階段（消費級零售時代）的具體論述因內容截斷而未完整呈現。




---


### 核心觀點



- 作者認為，AI 產業的真正瓶頸已從算力轉移至記憶體，HBM 容量不足且價格昂貴、標準 DRAM 因產能被 HBM 排擠而結構性短缺，這兩個問題共同迫使整個產業尋求讓 SSD 扮演記憶體角色的解方，這是一個產業級別的共識轉向，而非單一廠商的嘗試。

- 作者認為，SSD 被拉進記憶體層級這一趨勢，使得 SSD 控制器晶片的重要性大幅提升。控制器的效能高低，將直接決定 SSD 能否有效承擔 KV Cache 儲存與快速存取的任務，意味著控制器廠商（如慧榮 SIMO、群聯）在 AI 基礎設施升級浪潮中具有值得關注的結構性地位。

- 作者認為，NVIDIA 透過 CMX 平台所建立的記憶體分層架構，代表的不只是一個硬體產品，而是一套涵蓋軟體（Dynamo）、網路（Spectrum-X）、DPU（BlueField-4）與 SSD 陣列的完整生態系整合方案，這種垂直整合的思路將重新定義 AI 推理伺服器的架構標準。




---


### 提及標的


**公司：**



- NVIDIA（CMX 平台、BlueField-4 DPU、Spectrum-X、Dynamo、NIXL、Grove）

- AMD（收購 MEXT）

- MEXT（記憶體優化新創，被 AMD 收購）

- 慧榮科技（SIMO）

- 群聯電子（Phison）



**產品／平台：**



- NVIDIA CMX 平台（Context Memory Storage）

- NVIDIA Dynamo 推理框架

- NVIDIA NIXL 傳輸函式庫

- NVIDIA Grove

- Spectrum-X 乙太網路

- BlueField-4 DPU



**產業：**



- HBM（高頻寬記憶體）

- DRAM / DDR5

- NAND Flash / 3D NAND

- NVMe SSD

- SSD 控制器




---


### 關鍵數據



- 生產每 1GB 的 HBM，約消耗傳統 DDR5 記憶體 **三倍**的晶圓產能

- 數千字對話產生的 KV Cache 體積可超過 **1GB**

- 現今 3D NAND 技術已可堆疊至 **200 層、甚至 300 層以上**

- AMD 收購 MEXT 的時間點：**2026 年 6 月**

- NVIDIA 提出 CMX 架構的時間點：**2026 年初**

- CMX 平台在機櫃（Pod）規模下可為 GPU 提供 **TB（太位元組）級別**的共享儲存空間




---


### 創作者建議的觀察方向


根據本期節錄內容，作者雖未以明確條列方式提出「觀察建議」，但從行文脈絡可歸納出以下隱含的追蹤方向：



- 觀察 **SSD 控制器廠商**（慧榮 SIMO、群聯）在 AI 推理伺服器市場中的角色演變，此為本期標題點名的核心主題，後續章節應有更深入分析。

- 觀察 **NVIDIA CMX 平台生態系**的落地進展，包括 BlueField-4 DPU 與 Spectrum-X 的採用狀況。

- 觀察 **AMD 收購 MEXT** 後，其記憶體預測技術如何整合進 AMD 的 AI 推理產品線。

- 關注 **HBM 與標準 DRAM 的產能分配**動態，此結構性短缺是驅動 SSD 進入記憶體層的根本成因。

- 追蹤 **Prefill/Decode Disaggregation 架構**的產業採用速度，此架構的普及將直接拉升對高效能 SSD 與控制器的需求。


---
**⚠️ 負責任 AI 聲明與投資風險提示：**
1. 本摘要由 AI 自動生成，旨在萃取作者之邏輯框架與分析觀點，不代表本平台立場。
2. 投資涉及風險，摘要內容可能遺漏原文關鍵細節或產生解讀偏差，**請務必點擊上方連結閱讀原文** 以獲得完整資訊。
3. 摘要中提及之情境規劃與機率分佈均為作者個人觀點，不應視為具體投資建議或獲利保證。
