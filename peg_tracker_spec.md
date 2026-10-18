# 美股三大指數與 AI 企業巨頭「本益成長比 7 折雙軌監控系統」本地端開發規格書

本規格書完整記錄目前線上版 Google 試算表監控系統之核心演算法、資料欄位結構、22 檔追蹤標的基準數據，以及**本地端（Python）進階擴充規格**（解決線上版 `GOOGLEFINANCE` 無法抓取 Non-GAAP 遠期 EPS 與自由現金流之限制）。

## 1. 系統架構與雙版本定位

| 比較維度 | 線上雲端版（Google Sheets + Apps Script） | 本地端進階版（Python + `yfinance` / SEC API） |
| :--- | :--- | :--- |
| **主要用途** | 隨時隨地開啟手機/網頁檢視即時報價、雲端全自動每週寄信 | 本地深度回測、自動抓取 **Non-GAAP 遠期 EPS / 自由現金流**、自訂微調參數 |
| **即時報價來源** | `GOOGLEFINANCE(ticker, "price" / "high52" / "low52")` | `yfinance` (`currentPrice`, `fiftyTwoWeekHigh`, `fiftyTwoWeekLow`) |
| **當期盈餘來源** | `GOOGLEFINANCE(ticker, "eps")`（僅限帳面 GAAP TTM EPS） | `yfinance` (`trailingEps` 帳面 EPS + **`forwardEps` 分析師預估 Non-GAAP EPS**) |
| **歷年 EPS 來源** | 試算表內建 2020–2025 驗證財報基準值 | `yfinance` (`ticker.income_stmt`)、SEC EDGAR 官方免費 API 或 FMP API |
| **通知機制** | Gemini 每週一定時排程 + Google Apps Script (`MailApp`) | 本地 `smtplib` (Gmail App Password) + 匯出本地 CSV/HTML 報表 |

## 2. 財務數據網路自動取得管道（API 來源對照表）

在本地端開發時，所有財務與股價指標皆可透過網路免費取得，不需手動輸入：

| 需要的財務指標 | 免費網路取得管道（推薦優先順序） | Python 欄位 / 端點路徑 | 實戰用途與注意事項 |
| :--- | :--- | :--- | :--- |
| **即時股價與 52 週高低點** | **Yahoo Finance (`yfinance`)**（免金鑰） | `tk.info["currentPrice"]`、`tk.info["fiftyTwoWeekHigh"]`、`tk.info["fiftyTwoWeekLow"]` | 完全免費且即時，直接供【策略二：52 週高點打 7 折】與回測驗證使用 |
| **帳面當期 EPS (GAAP TTM)** | **Yahoo Finance (`yfinance`)**（免金鑰） | `tk.info["trailingEps"]` | 適合 AI 算力硬體與雲端巨頭（如 `NVDA`、`GOOGL`、`AMZN`、`TSM`） |
| **預估遠期 EPS (Non-GAAP Forward EPS)** | **Yahoo Finance (`yfinance`)**（免金鑰） | `tk.info["forwardEps"]` | **本地端最大優勢**：自動扣除 SBC（員工股權獎勵）扭曲，解決 `PLTR`、`NOW`、`PANW` 帳面 EPS 過低問題 |
| **每股自由現金流 (FCF per Share)** | **Yahoo Finance (`yfinance`)**（免金鑰） | `tk.info["freeCashflow"] / tk.info["sharesOutstanding"]` | 企業級 SaaS 軟體股（如 `NOW`、`CRM`、`PANW`、`ADBE`）最真實的獲利能力指標 |
| **近 4～5 年年度歷史 EPS** | **Yahoo Finance (`yfinance`)**（免金鑰） | `tk.income_stmt.loc["Diluted EPS"]` | `yfinance` 預設提供最近 4～5 個完整財年損益表，可直接計算滾動 CAGR |
| **長達 10 年完整 GAAP 歷史 EPS** | **SEC EDGAR 官方 API**（免金鑰，需帶 `User-Agent` Header） | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` (`EarningsPerShareDiluted`) | 美國證管會官方免費資料庫，涵蓋所有美股上市企業 10-K 年報原始數據 |
| **Non-GAAP 歷史財報與分析師共識** | **Financial Modeling Prep (FMP)** / **Finnhub**（免費註冊 API Key） | `https://financialmodelingprep.com/api/v3/income-statement/{ticker}` | 若未來想自動化抓 10 年結構化財報與華爾街共識預估，可串接免費額度 API |

## 3. 核心估值演算法規格（三軌可微調公式）

本地端程式建議將原本的「雙軌模型」進一步擴充為**「三軌自動適配模型」**，並將所有門檻抽離為可微調參數（Config）：

### 3.1 可微調核心參數（`CONFIG`）
* `SAFETY_DISCOUNT = 0.70`：安全邊際折數（預設打 7 折，即保留 30% 安全邊際）。
* `MAX_PE_CAP = 45.0`：合理本益比封頂上限（預設 45 倍，打 7 折後最高給予 **31.5 倍本益比**；避免高成長股算出天價）。
* `MIN_CAGR_FLOOR = 5.0`：最低成長率門檻（預設 5%；低於 5% 視為成熟收息股，不套用 PEG 模型）。
* `NEAR_TARGET_THRESHOLD = 0.10`：接近達標預警範圍（預設距離目標價 **+10% 以內** 發出黃燈預警）。

### 3.2 歷史年均複合成長率（CAGR）計算公式
$$\text{CAGR (\%)} = \left( \left( \frac{\text{EPS}_{\text{最新完整財年 (2025)}}}{\text{EPS}_{\text{基準財年 (2020 或轉盈年)}}} \right)^{\frac{1}{N}} - 1 \right) \times 100$$
* 一般穩健獲利公司：$N = 5$（2020 年至 2025 年）。
* 近年轉虧為盈之高成長企業 AI 軟體股（如 `PLTR`、`PANW`）：自動偵測第一個正 EPS 年度（如 2023 年）作為基準年，$N = 2$，並由 `MAX_PE_CAP = 45.0` 自動封頂。

### 3.3 三大目標價計算邏輯
1. **【策略一：GAAP 基本面 PEG 7 折目標價】（適用 AI 算力硬體與雲端巨頭）**
   * $\text{採計本益比} = \min(\text{CAGR}, \text{MAX\_PE\_CAP})$
   * $\text{策略一理想價} = \text{GAAP TTM EPS} \times \text{採計本益比}$
   * $\text{策略一 7 折目標價} = \text{策略一理想價} \times 0.70$
2. **【策略二：52 週高點打 7 折目標價】（適用高估值企業 AI 軟體股技術面回檔）**
   * $\text{策略二 7 折目標價} = \text{52 週最高價} \times 0.70$
   * 回測有效性檢核：若 $\text{策略二 7 折目標價} \ge \text{52 週最低價}$，代表過去一年內該跌幅真實發生過，具備實戰可執行性。
3. **【策略三（本地端專屬擴充）：Forward / FCF 真實獲利 PEG 7 折目標價】（專解 SaaS 軟體股 SBC 扭曲）**
   * $\text{真實獲利基數} = \max(\text{GAAP TTM EPS}, \text{Forward Non-GAAP EPS}, \text{每股自由現金流 FCF per Share})$
   * $\text{策略三 7 折目標價} = \text{真實獲利基數} \times \min(\text{CAGR}, \text{MAX\_PE\_CAP}) \times 0.70$
   * 實證效果：以 `NOW`（ServiceNow）為例，GAAP EPS 僅 `$1.60`（策略一僅 `$50.40`），但改取預估 Non-GAAP EPS（約 `$4.18`）或每股 FCF 後，策略三算出的 7 折目標價為 **`$131.67`**，與策略二（52 週高點打 7 折 **`$135.08`**）誤差不到 3%！

## 4. 雲端與本地共用 22 檔追蹤標的基準資料庫

| 代號 | 公司名稱 | 分類角色與指數 | 基準年 | 基準 EPS | 2025 EPS | 原始 CAGR (%) | 備援現價 | 備援 52W 高 | 備援 52W 低 | 備援 TTM EPS |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **GOOGL** | Alphabet | AI 雲端基建 (納斯達克/FANG+) | 2020 | $2.96 | $10.91 | 29.81% | $340.59 | $408.61 | $244.15 | $19.90 |
| **NVDA** | NVIDIA | AI 算力與 NIM 企業軟體 (費半/道瓊) | 2020 | $0.16 | $4.06 | 90.93% | $214.13 | $243.37 | $164.27 | $7.91 |
| **NFLX** | Netflix | 串流與 AI 推薦巨頭 (納斯達克/FANG+) | 2020 | $0.63 | $2.58 | 32.57% | $70.53 | $124.86 | $65.10 | $3.17 |
| **ORCL** | Oracle | 企業資料庫與 OCI AI 雲 (標普500) | 2019 | $3.23 | $5.94 | 12.96% | $128.23 | $304.28 | $114.50 | $6.38 |
| **INTU** | Intuit | 中小企業財稅 AI (納斯達克) | 2020 | $7.52 | $14.73 | 14.39% | $325.15 | $689.17 | $252.84 | $16.48 |
| **AVGO** | Broadcom | AI ASIC 與 VMware 私有雲 (費半) | 2020 | $0.66 | $4.90 | 49.32% | $328.75 | $495.00 | $289.96 | $7.83 |
| **ADBE** | Adobe | Firefly 企業行銷設計 AI (納斯達克) | 2020 | $10.94 | $16.73 | 8.87% | $245.20 | $363.70 | $190.12 | $17.92 |
| **IBM** | IBM | watsonx 企業混合雲與 AI 諮詢 (道瓊) | 2020 | $6.27 | $11.35 | 12.60% | $232.14 | $332.46 | $199.19 | $11.26 |
| **AMZN** | Amazon | AWS Bedrock 企業 AI 雲 (道瓊/納斯達克) | 2020 | $2.13 | $7.29 | 27.90% | $250.00 | $287.16 | $196.00 | $12.43 |
| **NOW** | ServiceNow | Now Assist 企業工作流 AI 代理 (標普500) | 2020 | $0.12 | $1.69 | 69.72% | $141.97 | $192.97 | $81.24 | $1.60 |
| **ACN** | Accenture | 全球最大企業 AI 導入顧問 (標普500) | 2020 | $8.27 | $12.21 | 8.10% | $229.68 | $291.09 | $118.15 | $13.56 |
| **PANW** | Palo Alto | Precision AI 企業資安平台 (納斯達克) | 2023 | $1.00 | $1.67 | 29.23% | $342.00 | $432.33 | $139.57 | $0.40 |
| **PLTR** | Palantir | AIP 企業數據與決策 AI 平台 (納斯達克) | 2023 | $0.09 | $0.69 | 176.69% | $186.03 | $212.94 | $106.38 | $1.17 |
| **CRM** | Salesforce | Agentforce 企業客戶 AI 代理 (道瓊) | 2020 | $3.92 | $7.56 | 14.04% | $240.70 | $269.11 | $146.32 | $10.98 |
| **TSM** | TSMC (ADR) | AI 晶片製造龍頭 (費半) | 2020 | $3.56 | $10.60 | 24.39% | $412.61 | $487.47 | $266.82 | $15.15 |
| **MSFT** | Microsoft | Copilot 與 Azure 企業 AI (道瓊/納斯達克) | 2020 | $6.78 | $16.04 | 18.79% | $529.05 | $553.72 | $349.20 | $17.95 |
| **META** | Meta | Llama 開源 AI 與廣告巨頭 (納斯達克) | 2020 | $10.23 | $23.97 | 18.57% | $709.33 | $779.82 | $520.26 | $26.56 |
| **KLAC** | KLA | 半導體製程檢測龍頭 (費半/納斯達克) | 2020 | $0.88 | $3.46 | 31.50% | $165.74 | $307.37 | $107.20 | $3.66 |
| **ASML** | ASML | EUV 微影設備龍頭 (費半/納斯達克) | 2020 | $9.99 | $28.52 | 23.34% | $1641.52 | $1999.96 | $946.11 | $39.33 |
| **AMAT** | Applied Mat. | 半導體設備龍頭 (費半/納斯達克) | 2020 | $3.95 | $8.72 | 17.16% | $409.29 | $739.67 | $203.46 | $11.59 |
| **LRCX** | Lam Research | 半導體蝕刻設備龍頭 (費半/納斯達克) | 2020 | $2.05 | $4.90 | 19.04% | $263.94 | $438.50 | $135.50 | $5.76 |
| **AAPL** | Apple | Apple Intelligence 終端 AI (道瓊/納斯達克) | 2020 | $3.74 | $7.92 | 16.19% | $343.46 | $348.15 | $243.42 | $8.72 |

## 5. 本地端開發與執行流程建議

1. **安裝依賴套件**：在本地電腦終端機執行 `pip install yfinance pandas requests`。
2. **執行本地端監控腳本（`us_ai_peg_tracker.py`）**：
   * 腳本會自動連線 `yfinance` 抓取最新股價、52 週高低點、GAAP EPS、**預估遠期 Non-GAAP EPS (`forwardEps`)** 與**每股自由現金流 (`FCF/Share`)**。
   * 若網路未連線或特定欄位缺漏，會自動退回使用上方基準資料庫，確保程式永不中斷。
   * 執行後會在終端機印出對照表、自動匯出 `peg_valuation_report.csv`，並可透過環境變數設定 Gmail 應用程式密碼寄發 HTML 週報。
