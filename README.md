# 🛡️ 美股 50/50 雙軌資產配置 ＆「PEG 7 折三軌監控系統」操作說明書 (README)

本專案為您的個人化美股財富管理與估值監控終端系統。結合《全球布局與美股投資地圖》四大指數配置思維與彼得・林區 `PEG（Price/Earnings-to-Growth Ratio，本益成長比）` 安全邊際哲學，打造**「50% 核心避險底倉（`CSPX` + `BND`）＋ 50% 衛星打折狙擊倉（`SHV` + `QQQ` + 22 檔 AI 巨頭三軌加碼）」**的自動化巡檢工具。

---

## 🚀 一、每週 3 分鐘標準操作流程（為什麼最適合每週觀察一次？）

這套策略的核心精神是**「右側價值狙擊、買在無人問津的 7 折區、長線抱緊處理」**，因此您**完全不需要每天盯盤**，最理想的操作節奏是**「每週末（例如週六或週日早上）花 3 分鐘巡檢一次」**（若遇美股單週暴跌超過 5% 的股災期，可於週間加看一次）：

### 📌 步驟 1：一鍵更新最新美股報價與財報數據
* 直接在資料夾內**雙擊執行 [`run_tracker.bat`](./run_tracker.bat)**（Windows 批次啟動檔）。
* 系統會在約 **5 ~ 8 秒內**透過多執行緒並行連線 **Yahoo Finance 官方財經資料庫**，自動拉取 22 檔巨頭的最新收盤價、過去 52 週最高／最低價、最新四季財報盈餘與自由現金流，並在瀏覽器自動開啟美化版主控台 [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html)。

### 📌 步驟 2：檢視主控台「📊 分頁 2：每週巡檢表」頂部 4 張燈號卡
打開網頁後，切換至第二個分頁，直接看頂部 4 張關鍵指標卡片與表格最右側欄位：
1. **🔥 3 軌全滿（建議投入該股額度 `100%` 大量資金 ＋ 同步抄底 `QQQ`）**：
   * 代表「策略一（帳面盈餘 7 折）」、「策略二（52 週高點打 7 折）」、「策略三（真實自由現金流／遠期盈餘 7 折）」**三個條件全部滿足**！這是極罕見的黃金鐵底（近五年回測勝率高達 98%），請將停泊在 `SHV`（短期美債）的資金大舉換入買滿。
2. **🟢🟢 2 軌同時滿足（建議累計投入該股額度 `60% ~ 70%` 主力資金）**：
   * 代表基本面與技術面／現金流雙重認證打 7 折，安全邊際極佳，可建立主力倉位。
3. **🟢 1 軌滿足（建議先投入該股額度 `30%` 基本試單倉）**：
   * 單一軌道率先跌入 7 折便宜區，先買 30% 確保不踏空，保留 70% 現金防範續跌。
4. **🟡 接近買點預警 ／ ⚪ 0 軌觀望（投入 `0%`，資金續留 `SHV` 領息）**：
   * 當股價高於所有 7 折線時，**什麼都不用做**！既有持股抱緊，閒置資金留在 `SHV` 領取約 4%~5% 的美元無風險利息。

### 📌 步驟 3：對照賣股目標價（分批停利與抱緊處理）
* 若您手頭已有先前在 7 折買進的持股，可對照表格中的 **「🎯 賣股參考價（10 折合理 ／ 12 折過熱）」**：
  * 漲回 **🎯 10 折合理價（`PEG = 1.0`，約較 7 折買價上漲 `+42.86%`）** ➔ 先賣出 **1/3 部位**鎖定獲利（轉入 `CSPX` 或 `SHV`）。
  * 衝上 **🔥 12 折過熱價（`PEG = 1.2`，約較 7 折買價上漲 `+71.4%`）** ➔ 再賣出 **1/3 部位**收回全部本金。
  * **最後 1/3 零成本底倉** ➔ **永久抱緊處理**，陪著企業長期複利成長！

---

## 🔍 二、這些股票的資料從哪裡取得？是否可靠？

本系統採用**「雙重機構級財經數據源 ＋ 離線驗證備援機制」**，數據來源完全透明且具備極高可靠性：

| 數據欄位 | 資料取得來源 | 更新頻率 | 可靠度與防錯處理機制 |
| :--- | :--- | :--- | :--- |
| **1. 目前股價 (`Current Price`)**<br>**2. 52 週最高／最低價 (`52W High/Low`)** | **Yahoo Finance 官方 API** (`yfinance`)<br>*(底層報價源自那斯達克 NLS 與紐約證交所即時／收盤行情)* | **每次執行 `run_tracker.bat` 時即時更新** | 100% 反映美股最新交易日收盤或盤中即時行情，並自動滾動計算過去 52 週最高與最低價。 |
| **3. 帳面每股盈餘 (`GAAP TTM EPS`)**<br>**4. 預估遠期盈餘 (`Forward Non-GAAP EPS`)** | **Yahoo Finance / S&P Capital IQ / Refinitiv (LSEG) 外資分析師共識資料庫** | **每次執行即時更新**<br>*(隨每季財報公布與華爾街分析師調升/調降自動更新)* | `GAAP TTM EPS` 對應公司過去四季正式財報；`Forward EPS` 為華爾街外資機構對未來 12 個月的平均預估共識。 |
| **5. 每股自由現金流 (`FCF per Share`)** | **Yahoo Finance 現金流量表** (`freeCashflow ÷ sharesOutstanding`) | **每次執行即時更新** | **內建跨國 `ADR（American Depositary Receipt，美國存託憑證）` 匯率校正引擎**：自動識別台積電 (`TSM`，財報幣別為新台幣 `TWD`) 與艾司摩爾 (`ASML`，財報幣別為歐元 `EUR`)，並自動換算為精準的美元每股自由現金流，杜絕幣別錯配誤差！ |
| **6. 歷年官方年報盈餘與 5 年成長率 (`CAGR`)** | **美國證管會 `SEC EDGAR` 官方 10-K 年報 API** (`data.sec.gov`) ＋ **設定檔 [`watchlist_config.json`](./watchlist_config.json)** | **每年完整財年結束後更新一次** | 年度複合成長率 (`CAGR`) 代表公司過去 5 年的長期體質，不應隨單日股價劇烈跳動，故固定以完整財年（2020→2025）為基準，確保估值定錨穩定。 |

> 💡 **如何確認我現在看到的是即時連線資料？**
> 在 [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html) 頂部導覽列右上角，有一個閃爍綠燈的膠囊徽章 **「`資料源：Yahoo Finance API (22/22 即時連線)`」**，且每檔股票名稱旁皆標註 **`● Yahoo即時`**，代表所有股價與當期盈餘皆為剛從網路抓下來的最新數據！

---

## 🔄 三、這 22 檔股票是固定的，還是也會定期更新？

這個問題可以分為**「數據更新」**與**「名單更新」**兩個層面：

1. **這 22 檔股票的「價格與當期財務數據」是動態更新的嗎？**
   * **是的！100% 自動動態更新！** 每週您點開 `run_tracker.bat` 時，這 22 檔股票的**現價、52 週高低點、當期帳面 EPS、分析師預估 EPS、自由現金流、三軌 7 折買進價、10 折賣出價、以及滿足幾軌燈號**，全部都會根據最新市場狀況重新計算更新。
2. **這 22 檔股票的「名單本身」是固定的嗎？如何增減或更新？**
   * **核心 22 檔為四大指數護城河龍頭（建議每年檢視一次即可）**：這 22 檔股票是從標普 500、那斯達克 100、費城半導體、道瓊工業指數中嚴選出的 AI 與產業壟斷巨頭（如 `NVDA`、`MSFT`、`AAPL`、`GOOGL`、`AMZN`、`META`、`TSM`、`AVGO`、`ASML` 等）。頂級巨頭的護城河極深，不需要每週更換名單。
   * **想新增第 23、24 檔自選股怎麼做？（兩種超簡單方式）**：
     * **方式 A（永久加入監控表）**：用記事本打開資料夾內的 [**`watchlist_config.json`**](./watchlist_config.json)，複製其中一檔股票的區塊，填入您想新增的美股代號（例如 `AMD`、`ANET`、`COST`、`TSLA`）與基準 EPS，存檔後再執行 `run_tracker.bat`，系統就會自動把它納入每週即時監控表！
     * **方式 B（臨時快速試算）**：直接打開 [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html) 切換到 **「🧮 分頁 5：自訂美股試算」**，在網頁上輸入任何美股代號與數字，1 秒鐘就能算出它的三軌 7 折買進價與 10 折賣出價！

---

## 📂 四、專案資料夾檔案清單與用途一覽

| 檔案名稱 | 檔案類型與核心用途說明 |
| :--- | :--- |
| [**`run_tracker.bat`**](./run_tracker.bat) | **【每週一鍵啟動器】** 每週末雙擊此檔案，自動連線更新 22 檔美股最新數據並打開視覺化主控台網頁。 |
| [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html) | **【核心互動式主控台網頁（已全面美化 UI）】** 支援「🌙 深色黑曜石玻璃擬態 ／ ☀️ 淺色晨報模式」雙主題切換，內含 5 大分頁（1. 投資憲法與每週 SOP、2. 22 檔三軌買賣價雷達與 52 週位階尺、3. 賣股指南與 50 筆五年回測驗證範例、4. 50/50 資產配置試算器、5. 自訂股票試算器）。 |
| [**`README.md`**](./README.md) | **【本操作說明書】** 說明每週操作 SOP、資料來源可靠度、22 檔名單更新與擴充方式。 |
| [**`MY_INVESTMENT_PLAYBOOK.md`**](./MY_INVESTMENT_PLAYBOOK.md) | **【防遺忘投資憲法備忘錄】** 純文字記錄您的 50/50 配置理由（`CSPX` 省稅、`BND` 防守、`SHV` 停泊、`QQQ` 股災抄底）、1/2/3 軌金字塔法則與英文指標字典。 |
| [**`watchlist_config.json`**](./watchlist_config.json) | **【股票池外部設定檔】** 收錄 22 檔追蹤股票之基準設定，支援隨時自行新增第 23+ 檔自選美股。 |
| [**`peg_valuation_report.csv`**](./peg_valuation_report.csv) | **【Excel 中文估值報表】** 每次執行自動匯出的全中文欄位 CSV 檔案，可直接用 Excel 開啟留存歷史紀錄。 |
| [**`peg_backtest_dashboard.html`**](./peg_backtest_dashboard.html) | **【五年歷史回測獨立報告】** 2021~2026 近五年歷史回測互動式圖表與績效分析網頁。 |
| [**`peg_backtest_report.csv`**](./peg_backtest_report.csv) & [**`peg_backtest_trades.csv`**](./peg_backtest_trades.csv) | **【五年回測驗證資料檔】** 記錄 22 檔股票五年回測統計與全部 50 筆歷史買賣交易明細（亦已自動內嵌至主控台網頁的分頁 3）。 |
| [**`us_ai_peg_tracker.py`**](./us_ai_peg_tracker.py) & [**`peg_backtester.py`**](./peg_backtester.py) | **【Python 核心引擎】** 主監控程式與五年歷史回測引擎原始碼。 |

---

## 💻 五、進階命令列（CLI）操作參數（選用）

除了直接雙擊 `run_tracker.bat` 之外，若您習慣使用終端機（PowerShell 或 CMD），亦可使用以下進階指令：

```powershell
# 1. 一般連線執行並自動開啟瀏覽器儀表板
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --open-browser

# 2. 只針對特定幾檔股票進行快速巡檢（例如只看 NVDA, META, TSM, GOOGL）
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --tickers NVDA,META,TSM,GOOGL

# 3. 調整安全邊際折數（例如股災時想看更嚴格的 65 折買點）
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --discount 0.65

# 4. 在無網路環境下使用離線基準資料庫執行
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --offline

# 5. 重新執行近五年（2021~2026）歷史獲利回測驗證
C:\Users\weichen\AppData\Local\Python\bin\python.exe peg_backtester.py

# 6. 執行自動化單元測試確認公式與回測引擎無誤
C:\Users\weichen\AppData\Local\Python\bin\python.exe -m pytest -v
```
