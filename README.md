# 🛡️ 美股 50/50 雙軌資產配置 ＆「PEG 7 折三軌監控系統」操作說明書 (README)

本專案為您的個人化美股財富管理與估值監控終端系統。結合《全球布局與美股投資地圖》四大指數配置思維與彼得・林區 `PEG（Price/Earnings-to-Growth Ratio，本益成長比）` 安全邊際哲學，打造**「50% 核心避險底倉（35% `CSPX` + 15% `BND`）＋ 50% 衛星打折狙擊倉（`SHV` + `QQQ` + 22 檔 AI 巨頭三軌加碼）」**的自動化巡檢工具。

---

## 🚀 一、每週 3 分鐘標準操作流程（為什麼最適合每週觀察一次？）

這套策略的核心精神是**「右側價值狙擊、買在無人問津的 7 折區、長線抱緊處理」**，因此您**完全不需要每天盯盤**，最理想的操作節奏是**「每週末（例如週六或週日早上）花 3 分鐘巡檢一次」**（若遇美股單週暴跌超過 5% 的股災期，可於週間加看一次）：

### 📌 步驟 1：一鍵更新最新美股報價與財報資料
* 直接在資料夾內**雙擊執行 [`run_tracker.bat`](./run_tracker.bat)**（Windows 批次啟動檔）。
* 系統會在約 **5 ~ 8 秒內**透過多執行緒並行連線 **Yahoo Finance 公開市場資料（透過 `yfinance` 套件）**，自動拉取 22 檔巨頭的最新收盤價、過去 52 週最高／最低價、最新四季財報盈餘、自由現金流、即時匯率（`TWD=X`、`EURUSD=X`）與 `SHV` 短債殖利率，並在瀏覽器自動開啟美化版主控台 [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html)。

### 📌 步驟 2：檢視主控台「📊 分頁 2：每週巡檢表」頂部 4 張燈號卡
打開網頁後，切換至第二個分頁，直接看頂部 4 張關鍵指標卡片與表格最右側欄位（**單一股票配置上限為衛星池的 10%，即總資產的 5%**）：
1. **🔥 3 軌全滿（建議投入該股額度 `100%` 即總資產 `5%` ＋ 同步抄底 `QQQ`）**：
   * 代表「策略一（帳面盈餘 7 折）」、「策略二（52 週高點打 7 折）」、「策略三（真實自由現金流／遠期盈餘 7 折）」**三個獨立條件全部滿足**！這是極罕見的黃金鐵底（無前視偏差近五年回測勝率高達 **90.0%**），請將停泊在 `SHV`（短期美債）的資金換入買滿該股額度。
2. **🟢🟢 2 軌同時滿足（建議累計投入該股額度 `60%` 即總資產 `3%`）**：
   * 代表具備兩個獨立維度同時認證打 7 折（若策略一與策略三因預估盈餘缺漏而算出相同目標價，系統會自動去重算作 1 軌，不重複加碼；若獲利衰退 `>20%` 或高點崩跌 `>=45%` 則自動啟動「🛡️ 價值陷阱防禦鎖」限縮至 `30%`）。
3. **🟢 1 軌滿足（建議先投入該股額度 `30%` 即總資產 `1.5%` 基本試單倉）**：
   * 單一軌道率先跌入 7 折便宜區，先買 30% 確保不踏空，保留 70% 額度防範續跌。
4. **🟡 接近買點預警 ／ ⚪ 0 軌觀望（投入 `0%`，資金續留 `SHV` 領息）**：
   * 當股價高於所有 7 折線時，**什麼都不用做**！既有持股抱緊，閒置資金留在 `SHV` 領取短期美債殖利率收益。

### 📌 步驟 3：對照賣股目標價（三段式分批停利與抱緊處理）
* 若您手頭已有先前在 7 折買進的持股，可對照表格中的 **「🎯 賣股參考價（10 折合理 ／ 12 折過熱）」**：
  * 漲回 **🎯 10 折合理價（`買進目標價 ÷ 0.70`，約較 7 折目標價上漲 `+42.86%`）** ➔ 先賣出 **1/3 部位**鎖定估值修復獲利（轉入 `CSPX` 或 `SHV`）。
  * 衝上 **🔥 12 折過熱價（`10 折合理價 × 1.20`，約較 7 折目標價上漲 `+71.4%`）** ➔ 再賣出 **1/3 部位**收回本金並實現超額獲利。
  * **最後 1/3 零成本底倉** ➔ **永久抱緊處理**，陪著企業長期複利成長（無前視偏差回測證實，三段式分批停利平均累積總報酬達 **`+268.1%`**）！

---

## 🔍 二、這些股票的資料從哪裡取得？透明性與防錯機制說明

本系統採用**「Yahoo Finance 公開市場資料 (`yfinance`) ＋ 美國證管會 `SEC EDGAR` 官方 XBRL API (`--sec-edgar`) ＋ 分欄精細備援追蹤」**，資料來源與限制完全透明：

| 資料欄位 | 資料取得來源 | 更新頻率 | 可靠度與防錯處理機制 |
| :--- | :--- | :--- | :--- |
| **1. 目前股價 (`Current Price`)**<br>**2. 52 週最高／最低價 (`52W High/Low`)** | **Yahoo Finance 公開市場資料** (`yfinance` 開源爬蟲套件) | **每次執行 `run_tracker.bat` 時即時更新** | 反映美股最新交易日收盤或盤中行情，並由過去 1 年日 K 線動態滾動計算 52 週最高與最低價。 |
| **3. 帳面每股盈餘 (`GAAP TTM EPS`)**<br>**4. 預估遠期盈餘 (`Forward Non-GAAP EPS`)** | **Yahoo Finance 統計摘要** ＋ 可選用 **美國證管會 `SEC EDGAR` 官方 10-K API** (`--sec-edgar`) | **每次執行即時更新** | 若部分標的於 Yahoo 端遇到限流或缺漏 `Forward EPS`，系統會自動退回基準值並在介面明確標示 **`◐ 報價即時+部分備援 (HYBRID)`**，絕不將備援值偽裝成即時連線值。 |
| **5. 每股自由現金流 (`FCF per Share`)** | **Yahoo Finance 現金流量表** (`freeCashflow ÷ max(impliedSharesOutstanding, sharesOutstanding)`) | **每次執行即時更新** | 1. **多類別股數校正**：優先採用 `impliedSharesOutstanding` 涵蓋 `GOOGL` 等 A/B/C 類總股數。<br>2. **即時匯率校正**：動態抓取 `TWD=X` 與 `EURUSD=X` 校正台積電 (`TSM`) 與艾司摩爾 (`ASML`) 財報幣別。<br>3. **異常值防呆封頂**：設為 `max(GAAP EPS, Forward EPS) × 1.75` 上限，過濾單季預收款暴衝假象。 |
| **6. 歷年官方年報盈餘與 5 年成長率 (`CAGR`)** | **設定檔 [`watchlist_config.json`](./watchlist_config.json)** ＋ **`SEC EDGAR` 官方 XBRL API** (`data.sec.gov`) | **每年完整財年結束後更新（或加 `--sec-edgar` 即時校驗）** | 年度複合成長率 (`CAGR`) 代表公司過去 5 年長期獲利體質，預設以完整財年（2020→2025）定錨；加上 `--sec-edgar` 參數時可自動連線美國證管會官方資料庫動態更新最新財年 `EPS` 與 `CAGR`。 |

> 💡 **如何分辨每個欄位的資料狀態？**
> 在 [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html) 頂部導覽列與每檔股票名稱旁，會明確區分三種狀態：
> * **`● 即時連線 (LIVE)`**：股價與財務指標全數即時取得。
> * **`◐ 報價即時+部分備援 (HYBRID)`**：股價為即時，但特定欄位（滑鼠移上去可查看如 `Forward_EPS` 或 `FCF/Share`）因來源缺漏而採用內建基準備援。
> * **`○ 離線基準 (FALLBACK)`**：無網路環境下使用內建基準資料庫。

---

## 🔄 三、這 22 檔股票是固定的，還是也會定期更新？

1. **這 22 檔股票的「價格與當期財務資料」是動態更新的嗎？**
   * **是的！自動動態更新！** 每週點開 `run_tracker.bat` 時，現價、52 週高低點、當期帳面 EPS、預估 EPS、自由現金流、三軌 7 折買進價、10 折賣出價與滿足軌數燈號皆會重新計算，並自動以「同日去重覆寫（Upsert by Date）」方式歸檔至 `history_snapshots/` 資料夾。
2. **這 22 檔股票的「名單本身」如何增減或更新？**
   * **方式 A（永久加入監控表）**：用記事本打開資料夾內的 [**`watchlist_config.json`**](./watchlist_config.json)，新增美股代號與基準 EPS，存檔後執行 `run_tracker.bat` 即自動納入監控表（系統採用 `dataclasses.replace` 安全載入，不會污染原始常數）。
   * **方式 B（臨時快速試算）**：打開 [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html) 切換到 **「🧮 分頁 5：自訂美股試算」**，輸入任何美股代號與數字即可即時試算。

---

## 📂 四、專案資料夾檔案清單與用途一覽

| 檔案名稱 | 檔案類型與核心用途說明 |
| :--- | :--- |
| [**`run_tracker.bat`**](./run_tracker.bat) | **【每週一鍵啟動器】** 每週末雙擊此檔案，自動連線更新 22 檔美股最新資料並打開視覺化主控台網頁。 |
| [**`peg_valuation_dashboard.html`**](./peg_valuation_dashboard.html) | **【核心互動式主控台網頁】** 支援「🌙 深色黑曜石玻璃擬態 ／ ☀️ 淺色晨報模式」雙主題切換，內含 5 大分頁（1. 50/50 投資憲法與稅務邊界、2. 22 檔三軌買賣價雷達、3. 賣股指南與無前視偏差五年回測驗證、4. 50/50 資產配置試算器、5. 自訂股票試算器）。 |
| [**`README.md`**](./README.md) | **【本操作說明書】** 說明每週操作 SOP、資料來源透明揭露、22 檔名單更新與擴充方式。 |
| [**`MY_INVESTMENT_PLAYBOOK.md`**](./MY_INVESTMENT_PLAYBOOK.md) | **【防遺忘投資憲法備忘錄】** 記錄 50/50 配置理由（35% `CSPX` 省稅、15% `BND` 防守、`SHV` 停泊、`QQQ` 股災抄底）、稅務與升息風險邊界、1/2/3 軌金字塔法則與英文指標字典。 |
| [**`watchlist_config.json`**](./watchlist_config.json) | **【股票池外部設定檔】** 收錄 22 檔追蹤股票之基準設定，支援隨時自行新增第 23+ 檔自選美股。 |
| [**`peg_valuation_report.csv`**](./peg_valuation_report.csv) | **【Excel 中文估值報表】** 每次執行自動匯出的全中文欄位 CSV 檔案（含防禦鎖狀態與精細資料來源標記）。 |
| [**`peg_backtest_dashboard.html`**](./peg_backtest_dashboard.html) | **【無前視偏差五年歷史回測報告】** 2021~2026 歷年滾動財報（Point-in-Time）回測與三段式分批停利對照網頁。 |
| [**`peg_backtest_report.csv`**](./peg_backtest_report.csv)、[**`peg_backtest_trades.csv`**](./peg_backtest_trades.csv)、[**`peg_backtest_meta.json`**](./peg_backtest_meta.json) | **【五年回測驗證資料檔】** 記錄 22 檔股票無前視偏差五年回測統計、30 筆歷史買賣交易明細與動態回測摘要 JSON（供主控台動態讀取，零硬編碼）。 |
| [**`us_ai_peg_tracker.py`**](./us_ai_peg_tracker.py) & [**`peg_backtester.py`**](./peg_backtester.py) | **【Python 核心引擎】** 主監控程式與無前視偏差五年歷史回測引擎原始碼。 |

---

## 💻 五、進階命令列（CLI）操作參數（選用）

```powershell
# 1. 一般連線執行並自動開啟瀏覽器儀表板
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --open-browser

# 2. 啟用美國證管會 SEC EDGAR 官方 XBRL API 交叉校驗歷年 Diluted EPS
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --sec-edgar

# 3. 只針對特定幾檔股票進行快速巡檢（例如只看 NVDA, META, TSM, GOOGL）
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --tickers NVDA,META,TSM,GOOGL

# 4. 調整安全邊際折數（例如股災時想看更嚴格的 65 折買點）
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --discount 0.65

# 5. 在無網路環境下使用離線基準資料庫執行（不會污染正式歷史日誌）
C:\Users\weichen\AppData\Local\Python\bin\python.exe us_ai_peg_tracker.py --offline

# 6. 重新執行無前視偏差近五年（2021~2026）歷史獲利回測驗證
C:\Users\weichen\AppData\Local\Python\bin\python.exe peg_backtester.py

# 7. 執行自動化單元測試確認公式與回測引擎無誤
C:\Users\weichen\AppData\Local\Python\bin\python.exe -m pytest -v
```

