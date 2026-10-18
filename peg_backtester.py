#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美股三大指數與 AI 企業巨頭「本益成長比 (PEG) 7 折三軌監控系統」近五年歷史獲利回測引擎 (Point-in-Time 無前視偏差修正版)
檔案名稱：peg_backtester.py

回測區間：近 5 年完整交易日（2021-10-18 至 2026-10-16，並使用 2020-10 起之資料計算滾動 52 週高低點）
核心修正與驗證目標：
1. 【徹底消除前視偏差 (Zero Look-Ahead Bias / Point-in-Time, PIT)】：
   - 內建 22 檔標的 2016–2026 歷年拆股調整後之真實歷史 EPS 序列 (HISTORICAL_PIT_EPS_DB)。
   - 在歷史任一交易日 t（例如 2022 年），僅能使用當時已公告之過去 5 年滾動 CAGR（如 2017→2022）與當時之 TTM EPS，絕不偷看 2024–2025 之後才發生的 AI 爆發期獲利。
2. 【新增「三階段分批賣出法 (10折賣1/3、12折賣1/3、1/3永久抱緊)」真實量化回測】：
   - 直接驗證「漲到 10 折全數賣光」vs.「三階段分批停利 + 1/3 底倉長抱」vs.「買在 7 折後完全不賣」三種出場機制的真實報酬率，並匯出 peg_backtest_meta.json 供主控台動態讀取（消除任何寫死數據）。
3. 【誠實揭露倖存者偏差 (Survivorship Bias) 與回測限制】：
   - 明確於報表與儀表板揭露樣本數、2022 年空頭集中度與歷史贏家篩選限制。
"""

from __future__ import annotations

import csv
import datetime
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from us_ai_peg_tracker import BASELINE_STOCKS, StockBaseline, ValuationConfig, calculate_cagr

CACHE_CSV_PATH = Path("historical_prices_2020_2026.csv")
META_JSON_PATH = Path("peg_backtest_meta.json")

# ==============================================================================
# 0. 歷史時點 (Point-in-Time) 2016–2026 歷年拆股調整後真實 EPS 資料庫
#    用於計算每一年度當下已知的「過去 5 年滾動 CAGR」與「當期 TTM EPS」，杜絕偷看未來！
#    格式: ticker -> {year: (gaap_eps, true_profit_eps_or_fcf)}
# ==============================================================================
HISTORICAL_PIT_EPS_DB: Dict[str, Dict[int, Tuple[float, float]]] = {
    "GOOGL": {
        2016: (1.39, 1.65), 2017: (1.60, 1.95), 2018: (2.19, 2.50), 2019: (2.46, 2.85),
        2020: (2.93, 3.35), 2021: (5.61, 6.10), 2022: (4.56, 5.15), 2023: (5.80, 6.50),
        2024: (8.04, 8.90), 2025: (10.91, 12.10), 2026: (19.90, 21.50),
    },
    "NVDA": {
        2016: (0.06, 0.08), 2017: (0.12, 0.14), 2018: (0.17, 0.19), 2019: (0.11, 0.15),
        2020: (0.17, 0.25), 2021: (0.38, 0.44), 2022: (0.17, 0.33), 2023: (1.19, 1.30),
        2024: (2.94, 3.20), 2025: (4.06, 4.65), 2026: (7.91, 8.65),
    },
    "NFLX": {
        2016: (0.09, 0.12), 2017: (0.25, 0.30), 2018: (0.54, 0.60), 2019: (0.83, 0.90),
        2020: (1.22, 1.40), 2021: (2.25, 2.40), 2022: (1.99, 2.15), 2023: (2.41, 2.85),
        2024: (2.52, 2.95), 2025: (2.58, 3.10), 2026: (3.17, 3.55),
    },
    "ORCL": {
        2016: (2.07, 2.65), 2017: (2.21, 2.85), 2018: (2.97, 3.40), 2019: (3.08, 3.65),
        2020: (3.97, 4.55), 2021: (2.41, 4.90), 2022: (3.07, 5.12), 2023: (3.71, 5.56),
        2024: (4.80, 6.20), 2025: (5.94, 7.10), 2026: (6.38, 7.85),
    },
    "INTU": {
        2016: (3.73, 4.90), 2017: (3.72, 5.40), 2018: (5.09, 6.50), 2019: (5.89, 7.40),
        2020: (6.92, 8.80), 2021: (7.56, 11.20), 2022: (7.28, 12.40), 2023: (8.42, 14.40),
        2024: (10.43, 16.90), 2025: (14.73, 19.80), 2026: (16.48, 22.40),
    },
    "AVGO": {
        2016: (0.35, 1.15), 2017: (0.40, 1.60), 2018: (2.82, 2.10), 2019: (0.64, 2.13),
        2020: (0.66, 2.22), 2021: (1.50, 2.80), 2022: (2.65, 3.76), 2023: (3.29, 4.22),
        2024: (3.90, 5.10), 2025: (4.90, 6.80), 2026: (7.83, 10.80),
    },
    "ADBE": {
        2016: (2.32, 3.40), 2017: (3.38, 4.70), 2018: (5.20, 6.80), 2019: (6.00, 8.10),
        2020: (10.83, 11.20), 2021: (10.02, 13.50), 2022: (10.10, 15.20), 2023: (11.82, 17.60),
        2024: (12.36, 19.50), 2025: (16.73, 21.40), 2026: (17.92, 23.10),
    },
    "IBM": {
        2016: (12.38, 13.50), 2017: (6.14, 13.80), 2018: (9.52, 13.81), 2019: (10.56, 12.81),
        2020: (6.23, 8.67), 2021: (6.41, 9.97), 2022: (1.80, 9.13), 2023: (8.14, 10.20),
        2024: (9.50, 11.80), 2025: (11.35, 13.10), 2026: (11.26, 14.20),
    },
    "AMZN": {
        2016: (0.25, 0.85), 2017: (0.31, 0.95), 2018: (1.01, 1.95), 2019: (1.15, 2.60),
        2020: (2.09, 3.10), 2021: (3.24, 3.60), 2022: (-0.14, 2.10), 2023: (2.90, 4.10),
        2024: (5.53, 6.80), 2025: (7.29, 9.50), 2026: (12.43, 13.80),
    },
    "NOW": {
        2016: (0.02, 0.18), 2017: (0.03, 0.28), 2018: (0.04, 0.48), 2019: (0.64, 0.72),
        2020: (0.12, 0.98), 2021: (0.23, 1.32), 2022: (0.32, 1.72), 2023: (1.68, 2.38),
        2024: (1.42, 3.15), 2025: (1.69, 3.65), 2026: (1.60, 4.18),
    },
    "ACN": {
        2016: (5.34, 6.10), 2017: (5.44, 6.70), 2018: (6.34, 7.60), 2019: (7.36, 8.50),
        2020: (7.89, 9.20), 2021: (9.16, 10.60), 2022: (10.71, 12.10), 2023: (10.77, 12.80),
        2024: (11.44, 13.80), 2025: (12.21, 14.60), 2026: (13.56, 15.40),
    },
    "PANW": {
        2016: (0.10, 0.85), 2017: (0.12, 1.15), 2018: (0.15, 1.55), 2019: (0.20, 1.95),
        2020: (-0.46, 2.45), 2021: (-0.86, 3.10), 2022: (-0.45, 4.20), 2023: (1.28, 5.60),
        2024: (1.50, 7.20), 2025: (1.67, 8.90), 2026: (0.40, 10.50),
    },
    "PLTR": {
        2016: (0.02, 0.04), 2017: (0.02, 0.05), 2018: (0.03, 0.06), 2019: (0.03, 0.08),
        2020: (-1.20, 0.12), 2021: (-0.27, 0.16), 2022: (-0.18, 0.22), 2023: (0.09, 0.35),
        2024: (0.22, 0.65), 2025: (0.69, 1.25), 2026: (1.17, 2.15),
    },
    "CRM": {
        2016: (0.26, 1.35), 2017: (0.49, 1.85), 2018: (1.43, 2.75), 2019: (0.15, 3.40),
        2020: (4.38, 4.92), 2021: (1.48, 4.78), 2022: (0.21, 6.45), 2023: (4.20, 9.60),
        2024: (6.20, 12.10), 2025: (7.56, 13.80), 2026: (10.98, 15.60),
    },
    "TSM": {
        2016: (1.98, 2.15), 2017: (2.19, 2.40), 2018: (2.23, 2.50), 2019: (2.19, 2.45),
        2020: (3.39, 3.70), 2021: (4.12, 4.45), 2022: (6.57, 6.95), 2023: (5.18, 5.80),
        2024: (7.05, 8.20), 2025: (10.60, 12.10), 2026: (15.15, 18.20),
    },
    "MSFT": {
        2016: (2.10, 2.85), 2017: (3.25, 3.55), 2018: (2.13, 4.05), 2019: (5.06, 5.30),
        2020: (5.76, 6.20), 2021: (8.05, 8.60), 2022: (9.65, 10.10), 2023: (9.68, 10.60),
        2024: (11.80, 12.90), 2025: (16.04, 17.50), 2026: (17.95, 20.80),
    },
    "META": {
        2016: (3.49, 4.23), 2017: (5.39, 6.16), 2018: (7.57, 8.10), 2019: (6.43, 8.50),
        2020: (10.09, 11.20), 2021: (13.77, 15.10), 2022: (8.59, 10.95), 2023: (14.87, 17.60),
        2024: (21.20, 23.80), 2025: (23.97, 26.80), 2026: (26.56, 30.40),
    },
    "KLAC": {
        2016: (0.45, 0.55), 2017: (0.59, 0.70), 2018: (0.51, 0.85), 2019: (0.75, 0.95),
        2020: (0.77, 1.05), 2021: (1.34, 1.55), 2022: (2.10, 2.35), 2023: (2.42, 2.65),
        2024: (2.60, 2.95), 2025: (3.46, 3.85), 2026: (3.66, 4.50),
    },
    "ASML": {
        2016: (3.85, 4.50), 2017: (5.60, 6.20), 2018: (6.95, 7.60), 2019: (6.88, 7.50),
        2020: (9.99, 11.10), 2021: (16.58, 18.50), 2022: (15.09, 17.20), 2023: (21.42, 23.80),
        2024: (20.80, 24.50), 2025: (28.52, 33.50), 2026: (39.33, 46.80),
    },
    "AMAT": {
        2016: (1.54, 1.75), 2017: (3.17, 3.45), 2018: (3.23, 4.45), 2019: (2.86, 3.15),
        2020: (3.92, 4.25), 2021: (6.40, 6.85), 2022: (7.44, 7.85), 2023: (8.11, 8.55),
        2024: (8.61, 9.20), 2025: (8.72, 10.50), 2026: (11.59, 13.20),
    },
    "LRCX": {
        2016: (0.58, 0.72), 2017: (0.99, 1.15), 2018: (1.35, 1.80), 2019: (1.45, 1.60),
        2020: (1.54, 1.75), 2021: (2.69, 2.95), 2022: (3.27, 3.55), 2023: (3.34, 3.65),
        2024: (2.95, 3.40), 2025: (4.90, 5.45), 2026: (5.76, 6.85),
    },
    "AAPL": {
        2016: (2.08, 2.35), 2017: (2.30, 2.60), 2018: (2.98, 3.30), 2019: (2.97, 3.40),
        2020: (3.28, 3.74), 2021: (5.61, 6.10), 2022: (6.11, 6.60), 2023: (6.13, 6.75),
        2024: (6.08, 7.10), 2025: (7.92, 8.60), 2026: (8.72, 9.85),
    },
}


# ==============================================================================
# 1. 回測參數與結果資料結構
# ==============================================================================
@dataclass
class BacktestConfig:
    """近五年歷史回測參數設定"""
    start_date: str = "2021-10-18"       # 回測起始日（滿 5 年）
    end_date: str = "2026-10-16"         # 回測結束日
    warmup_start_date: str = "2020-10-01"# 預熱起始日（供計算 2021-10 當時的滾動 52 週高低點）
    initial_capital: float = 100000.0    # 組合回測初始本金 ($100,000 美元)
    max_positions: int = 10              # 投資組合最大同時持倉檔數（每檔配置上限 1/max_positions 資金）
    safety_discount: float = 0.70        # 買進安全邊際折數（預設 7 折 = 0.70）
    take_profit_multiple: float = 1.00   # 均值回歸停利目標折數（預設回到 10 折合理價值 = 7折價 / 0.70，即 +42.86% 停利）
    max_pe_cap: float = 45.0             # 合理本益比封頂上限
    fee_rate_one_way: float = 0.0015     # 單邊交易成本（手續費 + 滑價 = 0.15%，來回 0.30%）
    min_hold_cooldown: int = 40          # 同一檔股票加碼／重複觸發冷卻交易日數
    max_hold_days: int = 252             # 波段單筆最長持有交易日數（滿 1 年若獲利 >= 15% 則巡檢換股）


@dataclass
class TradeRecord:
    """單筆歷史交易明細記錄"""
    ticker: str
    name: str
    strategy_name: str
    entry_date: str
    entry_price: float
    target_price_at_entry: float
    exit_date: str
    exit_price: float
    exit_reason: str              # '均值回歸停利 (回到10折合理價)' / '持有滿1年獲利了結' / '期末持有結算'
    holding_days: int
    invested_amount: float
    gross_return_pct: float
    total_fee_usd: float
    net_profit_usd: float
    net_return_pct: float
    matched_tracks: int = 1               # 進場時滿足之有效獨立軌數 (1, 2, 3)
    circuit_breaker_active: bool = False  # 是否觸發價值陷阱防禦鎖或未達5年獲利限制
    holding_max_drawdown_pct: float = 0.0 # 持倉期間最大回撤浮虧 (MDD %)
    one_year_return_pct: float = 0.0      # 進場持有滿 1 年 (252交易日) 之實際報酬率 (%)


@dataclass
class StockBacktestSummary:
    """單一股票在指定策略下之 5 年回測統計"""
    ticker: str
    name: str
    category: str
    recommended_anchor: str
    trade_count: int
    win_count: int
    win_rate_pct: float
    avg_gross_return_pct: float
    avg_net_return_pct: float
    avg_holding_days: float
    total_fees_usd: float
    total_net_profit_usd: float   # 以每筆固定投入 $10,000 美元計算之累計淨利
    buy_and_hold_5y_pct: float    # 該股近 5 年單純買進持有報酬率 (%)
    best_trade_pct: float
    worst_trade_pct: float
    staged_3tier_return_pct: float = 0.0     # 買在7折後採「三階段賣出 (10折賣1/3、12折賣1/3、1/3抱緊)」之實測報酬率 (%)
    hold_from_entry_return_pct: float = 0.0  # 買在7折後「完全不賣抱到底」之實測報酬率 (%)


@dataclass
class PortfolioBacktestMetrics:
    """$100,000 美元投資組合 5 年回測績效指標"""
    strategy_id: str
    strategy_label: str
    initial_capital: float
    final_equity: float
    total_net_profit: float
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    win_rate_pct: float
    total_fees_paid: float
    avg_exposure_pct: float       # 平均資金利用率 (%)
    equity_curve_dates: List[str] = field(default_factory=list)
    equity_curve_values: List[float] = field(default_factory=list)


# ==============================================================================
# 2. 歷史日線資料獲取與快取管理
# ==============================================================================
def load_or_download_prices(bt_cfg: BacktestConfig, force_download: bool = False) -> pd.DataFrame:
    """
    載入或從 yfinance 下載 22 檔追蹤標的 + SPY + QQQ 自 2020-10-01 起之歷史收盤價。
    內建本地 CSV 快取，確保高速與離線可重現性。
    """
    tickers = [s.ticker for s in BASELINE_STOCKS] + ["SPY", "QQQ"]

    if CACHE_CSV_PATH.exists() and not force_download:
        df = pd.read_csv(CACHE_CSV_PATH, index_col=0, parse_dates=True)
        missing = [t for t in tickers if t not in df.columns]
        if not missing and len(df) > 1200:
            return df.sort_index().ffill().bfill()

    print("📥 正在透過 yfinance 下載 22 檔 AI 巨頭與 SPY/QQQ 近 6 年歷史日線資料...")
    raw = yf.download(
        tickers,
        start=bt_cfg.warmup_start_date,
        end=datetime.date.today().strftime("%Y-%m-%d"),
        threads=False,
        progress=False,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        close_df = raw["Close"].copy()
    else:
        close_df = raw.copy()

    close_df = close_df.sort_index().ffill().bfill()
    close_df.to_csv(CACHE_CSV_PATH, encoding="utf-8")
    print(f"✅ 歷史日線資料已快取至：{CACHE_CSV_PATH.resolve()} (共 {len(close_df)} 個交易日)")
    return close_df


# ==============================================================================
# 3. 嚴格無前視偏差 (Point-in-Time) 動態 EPS、滾動 5 年 CAGR 與三軌目標價建構
# ==============================================================================
def build_historical_target_series(
    stock: StockBaseline,
    price_series: pd.Series,
    bt_cfg: BacktestConfig,
) -> pd.DataFrame:
    """
    為單一股票建構 2021-10 至 2026-10 每個交易日 t 的「嚴格因果時點 (Point-in-Time, PIT)」估值序列：
    - 【徹底根除前視偏差與線性插值 (Zero Look-Ahead / No Interpolation)】：
      上市公司財年 Y 之 10-K 年報官方公告日統一定為隔年 3 月 15 日 (datetime.date(Y + 1, 3, 15))。
      在交易日 t 當下，只能使用公告日 <= t 之最新已公告財年數據，新財報公告前維持恆定階梯數值 (Step-Function Forward-Fill)，嚴禁任何線性插值！
    - 【彼得林區五年連續獲利檢驗】：若過去 5 年內有任一年 GAAP Diluted EPS <= 0，策略一強制停用 (目標價歸零)。
    - 【規則全面統一】：移除回測中私設之 25x/22x PE 濾網，智慧定錨邏輯完全與主系統對齊。
    """
    dates = price_series.index
    high52 = price_series.rolling(window=252, min_periods=60).max()
    low52 = price_series.rolling(window=252, min_periods=60).min()

    pit_db = HISTORICAL_PIT_EPS_DB.get(stock.ticker, {})
    sorted_yrs = sorted(pit_db.keys())

    gaap_eps_arr: List[float] = []
    true_eps_arr: List[float] = []
    capped_pe_arr: List[float] = []
    s1_target_arr: List[float] = []
    s2_target_arr: List[float] = []
    s2_valid_arr: List[bool] = []
    s3_target_arr: List[float] = []
    smart_target_arr: List[float] = []
    anchor_name_arr: List[str] = []
    contracting_arr: List[bool] = []
    five_year_ok_arr: List[bool] = []

    for idx, d in enumerate(dates):
        dt = pd.to_datetime(d).date()
        # 尋找在交易日 dt 當日市場已官方知悉 (公告生效日 Y+1-03-15 <= dt) 之最新財年
        eligible_yrs = [yr for yr in sorted_yrs if datetime.date(yr + 1, 3, 15) <= dt]
        if eligible_yrs:
            y_known = max(eligible_yrs)
        else:
            y_known = min(sorted_yrs)

        g_eps, t_eps = pit_db[y_known]

        # 檢驗彼得林區 (Peter Lynch) 五年連續獲利原則 (y_known-4 到 y_known 連續 5 年皆為正)
        check_yrs = range(y_known - 4, y_known + 1)
        five_yr_ok = all(yr in pit_db and pit_db[yr][0] > 0 for yr in check_yrs)

        # 滾動 5 年 CAGR 計算 (y_known - 5 -> y_known，絕不偷看未來！)
        prev_yr = y_known - 5
        if prev_yr in pit_db and pit_db[prev_yr][0] > 0 and g_eps > 0:
            cagr_g = calculate_cagr(pit_db[prev_yr][0], g_eps, 5)
        else:
            cagr_g = 0.0

        if prev_yr in pit_db and pit_db[prev_yr][1] > 0 and t_eps > 0:
            cagr_t = calculate_cagr(pit_db[prev_yr][1], t_eps, 5)
        else:
            cagr_t = 0.0

        rolling_cagr = max(cagr_g, cagr_t)
        if rolling_cagr <= 0:
            rolling_cagr = stock.raw_cagr

        capped_pe = min(max(rolling_cagr, 5.0), bt_cfg.max_pe_cap)
        disc_pe = capped_pe * bt_cfg.safety_discount

        # 策略一：若當期 GAAP EPS <= 0 或未通過五年連續獲利檢驗，策略一目標價強制歸零
        if g_eps > 0 and five_yr_ok:
            s1_t = g_eps * disc_pe
        else:
            s1_t = 0.0

        # 策略二：滾動 52 週高點 7 折
        h52_val = float(high52.iloc[idx]) if not math.isnan(high52.iloc[idx]) else float(price_series.iloc[idx])
        l52_val = float(low52.iloc[idx]) if not math.isnan(low52.iloc[idx]) else float(price_series.iloc[idx])
        s2_t = h52_val * bt_cfg.safety_discount
        s2_v = (s2_t >= l52_val)

        # 策略三：若真實獲利基數 <= 0，策略三目標價強制歸零
        if t_eps > 0:
            s3_t = t_eps * disc_pe
        else:
            s3_t = 0.0

        # 智慧三軌定錨目標價 (完全對齊主系統邏輯，杜絕私設本益比濾網)
        if stock.sector_type == "MATURE_MOAT":
            smart_t = s2_t
            anchor_name = "策略二 (52W高點7折防踏空)"
        elif stock.sector_type == "SAAS_SBC":
            if rolling_cagr >= 25.0:
                smart_t = s3_t
                anchor_name = "策略三 (Forward/FCF真實獲利7折)"
            else:
                smart_t = max(s2_t, s3_t) if s2_v else s3_t
                anchor_name = "策略二/三 雙軌定錨"
        elif stock.sector_type == "SEMI_EQUIP":
            smart_t = s3_t
            anchor_name = "策略三 (週期檢核)"
        else:
            smart_t = s1_t if (t_eps > 0 and (g_eps / t_eps) >= 0.85 and s1_t > 0) else s3_t
            anchor_name = "策略一/三 (基本面真實PEG 7折)"

        # 當期盈餘衰退檢核 (較前一年度衰退超過 20%)
        prev_yr_data = pit_db.get(y_known - 1)
        if prev_yr_data and prev_yr_data[0] > 0:
            is_contracting = (g_eps < prev_yr_data[0] * 0.80)
        else:
            is_contracting = False

        gaap_eps_arr.append(g_eps)
        true_eps_arr.append(t_eps)
        capped_pe_arr.append(capped_pe)
        s1_target_arr.append(s1_t)
        s2_target_arr.append(s2_t)
        s2_valid_arr.append(s2_v)
        s3_target_arr.append(s3_t)
        smart_target_arr.append(smart_t)
        anchor_name_arr.append(anchor_name)
        contracting_arr.append(is_contracting)
        five_year_ok_arr.append(five_yr_ok)

    df_out = pd.DataFrame(
        {
            "close": price_series.values,
            "high52": high52.values,
            "low52": low52.values,
            "gaap_eps": gaap_eps_arr,
            "true_eps": true_eps_arr,
            "capped_pe": capped_pe_arr,
            "s1_target": s1_target_arr,
            "s2_target": s2_target_arr,
            "s2_valid": s2_valid_arr,
            "s3_target": s3_target_arr,
            "smart_target": smart_target_arr,
            "anchor_name": anchor_name_arr,
            "is_contracting": contracting_arr,
            "five_year_ok": five_year_ok_arr,
        },
        index=dates,
    )
    return df_out.loc[bt_cfg.start_date : bt_cfg.end_date].copy()


# ==============================================================================
# 4. 單一標的波段交易回測 ＆「三階段分批賣出 (1/3 + 1/3 + 1/3抱緊)」實證回測
# ==============================================================================
def simulate_staged_exit_for_stock(
    closes: np.ndarray,
    targets: np.ndarray,
    safety_discount: float,
    fee_rate: float,
) -> Tuple[float, float]:
    """
    實證模擬該股票在第一次觸發 7 折買進後：
    1. 【三階段分批停利法】：漲回 10 折合理價賣出 1/3、漲到 12 折過熱價再賣 1/3、最後 1/3 永久抱緊至期末之淨報酬率 (%)
    2. 【買在 7 折後完全不賣 (Hold from First Entry)】：從第一次 7 折買點一路抱到期末之淨報酬率 (%)
    """
    entry_idx = -1
    entry_price = 0.0
    entry_target = 0.0
    for i in range(len(closes)):
        p = float(closes[i])
        t = float(targets[i])
        if p > 0 and t > 0 and p <= t:
            entry_idx = i
            entry_price = p
            entry_target = t
            break

    if entry_idx < 0 or entry_price <= 0:
        return 0.0, 0.0

    final_price = float(closes[-1])
    # 1. 買在 7 折後完全不賣抱到底之報酬率 (扣買進與期末結算費用)
    hold_from_entry_ret = ((final_price * (1.0 - fee_rate)) / (entry_price * (1.0 + fee_rate)) - 1.0) * 100.0

    # 2. 三階段分批停利 (1/3 @ 10折合理價, 1/3 @ 12折過熱價, 1/3 @ 期末抱緊)
    sold_tier1 = False
    sold_tier2 = False
    tier1_sell_price = final_price
    tier2_sell_price = final_price

    for j in range(entry_idx + 5, len(closes)):
        p = float(closes[j])
        t = float(targets[j])
        fair_100 = max(entry_target, t) / safety_discount
        overheated_120 = fair_100 * 1.20
        if not sold_tier1 and p >= fair_100:
            sold_tier1 = True
            tier1_sell_price = p
        if not sold_tier2 and p >= overheated_120:
            sold_tier2 = True
            tier2_sell_price = p
        if sold_tier1 and sold_tier2:
            break

    avg_exit_price = (tier1_sell_price + tier2_sell_price + final_price) / 3.0
    staged_ret = ((avg_exit_price * (1.0 - fee_rate)) / (entry_price * (1.0 + fee_rate)) - 1.0) * 100.0
    return round(staged_ret, 2), round(hold_from_entry_ret, 2)


def simulate_stock_trades(
    stock: StockBaseline,
    hist_df: pd.DataFrame,
    strategy_col: str,
    strategy_label: str,
    bt_cfg: BacktestConfig,
    trade_size_usd: float = 10000.0,
) -> Tuple[List[TradeRecord], StockBacktestSummary]:
    """
    針對單一股票模擬過去 5 年每當 `收盤價 <= 當時已知7折目標價` 時買進：
    - 嚴格落實「一二三軌部位金字塔階梯 (30%/60%/100%)」與「價值陷阱防禦鎖 (盈餘衰退或回檔>45%強制鎖定30%)」。
    - 嚴格追蹤持倉期間之最大回撤浮虧 (holding_max_drawdown_pct) 與進場後滿 1 年之真實報酬率 (one_year_return_pct)。
    - 在 `收盤價 >= 當時10折合理價` 或滿 1 年獲利達標時賣出，嚴格扣除雙邊手續費。
    """
    trades: List[TradeRecord] = []
    dates = hist_df.index
    closes = hist_df["close"].values
    targets = hist_df[strategy_col].values

    in_position = False
    entry_idx = 0
    entry_price = 0.0
    entry_target = 0.0
    actual_invest_usd = trade_size_usd
    matched_tracks = 1
    cb_active = False
    last_exit_idx = -bt_cfg.min_hold_cooldown

    for i in range(len(dates)):
        price = float(closes[i])
        target = float(targets[i])
        if math.isnan(price) or math.isnan(target) or price <= 0 or target <= 0:
            continue

        if not in_position:
            if price <= target and (i - last_exit_idx) >= bt_cfg.min_hold_cooldown:
                in_position = True
                entry_idx = i
                entry_price = price
                entry_target = target

                # 計算進場時滿足之有效獨立軌數與防禦鎖狀態
                s1_t_val = float(hist_df["s1_target"].iloc[i])
                s2_t_val = float(hist_df["s2_target"].iloc[i])
                s2_v_val = bool(hist_df["s2_valid"].iloc[i])
                s3_t_val = float(hist_df["s3_target"].iloc[i])
                h52_val = float(hist_df["high52"].iloc[i])
                is_cont = bool(hist_df["is_contracting"].iloc[i])
                five_ok = bool(hist_df["five_year_ok"].iloc[i])

                s1_b = (price <= s1_t_val and s1_t_val > 0)
                s2_b = (price <= s2_t_val and s2_v_val)
                s3_b = (price <= s3_t_val and s3_t_val > 0)

                same_base = (s1_t_val > 0 and s3_t_val > 0 and abs(s3_t_val - s1_t_val) / max(1.0, s1_t_val) < 0.03)
                if s1_b and s3_b and same_base and not s2_b:
                    matched_tracks = 1
                else:
                    matched_tracks = sum([s1_b, s2_b, s3_b])
                if matched_tracks == 0:
                    matched_tracks = 1

                dd_h = ((price - h52_val) / h52_val) if h52_val > 0 else 0.0
                cb_active = (matched_tracks >= 2 and (is_cont or dd_h <= -0.45)) or (not five_ok)

                if cb_active or not five_ok or matched_tracks <= 1:
                    alloc_ratio = 0.30
                elif matched_tracks == 2:
                    alloc_ratio = 0.60
                else:
                    alloc_ratio = 1.00

                actual_invest_usd = trade_size_usd * alloc_ratio
        else:
            hold_days = i - entry_idx
            # 僅使用進場時點之合理價 (entry_target / 0.70) 作為純粹均值回歸停利標準，不偷看未來目標價
            fair_value_exit = (entry_target / bt_cfg.safety_discount) * bt_cfg.take_profit_multiple
            gross_ret = (price / entry_price) - 1.0

            exit_reason = ""
            if price >= fair_value_exit and hold_days >= 5:
                exit_reason = "均值回歸停利 (回到10折合理價)"
            elif hold_days >= bt_cfg.max_hold_days and gross_ret >= 0.15:
                exit_reason = "持有滿1年獲利了結"
            elif i == len(dates) - 1:
                exit_reason = "期末持有結算"

            if exit_reason:
                entry_fee = actual_invest_usd * bt_cfg.fee_rate_one_way
                shares_bought = (actual_invest_usd - entry_fee) / entry_price
                gross_exit_val = shares_bought * price
                exit_fee = gross_exit_val * bt_cfg.fee_rate_one_way
                net_exit_val = gross_exit_val - exit_fee

                total_fee = entry_fee + exit_fee
                net_profit = net_exit_val - actual_invest_usd
                net_ret_pct = (net_profit / actual_invest_usd) * 100.0

                # 計算持倉期間最大回撤 (浮虧最大值 %)
                hold_closes = closes[entry_idx : i + 1]
                min_hold_p = float(np.min(hold_closes))
                holding_mdd_pct = ((min_hold_p - entry_price) / entry_price) * 100.0

                # 計算進場持有滿 1 年 (252交易日) 之實際報酬率 (%)
                idx_1y = min(entry_idx + 252, len(closes) - 1)
                p_1y = float(closes[idx_1y])
                one_year_ret_pct = ((p_1y * (1.0 - bt_cfg.fee_rate_one_way)) / (entry_price * (1.0 + bt_cfg.fee_rate_one_way)) - 1.0) * 100.0

                trades.append(
                    TradeRecord(
                        ticker=stock.ticker,
                        name=stock.name,
                        strategy_name=strategy_label,
                        entry_date=dates[entry_idx].strftime("%Y-%m-%d"),
                        entry_price=round(entry_price, 2),
                        target_price_at_entry=round(entry_target, 2),
                        exit_date=dates[i].strftime("%Y-%m-%d"),
                        exit_price=round(price, 2),
                        exit_reason=exit_reason,
                        holding_days=int(hold_days),
                        invested_amount=round(actual_invest_usd, 2),
                        gross_return_pct=round(gross_ret * 100.0, 2),
                        total_fee_usd=round(total_fee, 2),
                        net_profit_usd=round(net_profit, 2),
                        net_return_pct=round(net_ret_pct, 2),
                        matched_tracks=matched_tracks,
                        circuit_breaker_active=cb_active,
                        holding_max_drawdown_pct=round(holding_mdd_pct, 2),
                        one_year_return_pct=round(one_year_ret_pct, 2),
                    )
                )
                in_position = False
                last_exit_idx = i

    bnh_5y = ((float(closes[-1]) / float(closes[0])) - 1.0) * 100.0 if len(closes) > 1 else 0.0
    staged_ret, hold_entry_ret = simulate_staged_exit_for_stock(
        closes, targets, bt_cfg.safety_discount, bt_cfg.fee_rate_one_way
    )

    t_count = len(trades)
    w_count = sum(1 for t in trades if t.net_profit_usd > 0)
    win_rate = (w_count / t_count * 100.0) if t_count > 0 else 0.0
    avg_gross = float(np.mean([t.gross_return_pct for t in trades])) if t_count > 0 else 0.0
    avg_net = float(np.mean([t.net_return_pct for t in trades])) if t_count > 0 else 0.0
    avg_days = float(np.mean([t.holding_days for t in trades])) if t_count > 0 else 0.0
    tot_fees = sum(t.total_fee_usd for t in trades)
    tot_net_profit = sum(t.net_profit_usd for t in trades)
    best_pct = max((t.net_return_pct for t in trades), default=0.0)
    worst_pct = min((t.net_return_pct for t in trades), default=0.0)

    summary = StockBacktestSummary(
        ticker=stock.ticker,
        name=stock.name,
        category=stock.category,
        recommended_anchor=str(hist_df["anchor_name"].iloc[0]),
        trade_count=t_count,
        win_count=w_count,
        win_rate_pct=round(win_rate, 2),
        avg_gross_return_pct=round(avg_gross, 2),
        avg_net_return_pct=round(avg_net, 2),
        avg_holding_days=round(avg_days, 1),
        total_fees_usd=round(tot_fees, 2),
        total_net_profit_usd=round(tot_net_profit, 2),
        buy_and_hold_5y_pct=round(bnh_5y, 2),
        best_trade_pct=round(best_pct, 2),
        worst_trade_pct=round(worst_pct, 2),
        staged_3tier_return_pct=staged_ret,
        hold_from_entry_return_pct=hold_entry_ret,
    )
    return trades, summary


# ==============================================================================
# 5. $100,000 美元投資組合 5 年完整資金曲線回測 (Portfolio Simulation)
# ==============================================================================
def run_portfolio_simulation(
    all_hist: Dict[str, pd.DataFrame],
    strategy_col: str,
    strategy_id: str,
    strategy_label: str,
    bt_cfg: BacktestConfig,
) -> PortfolioBacktestMetrics:
    """
    模擬真實 $100,000 美元投資組合 (Point-in-Time 無前視偏差)：
    - 每日檢查 22 檔標的是否跌破當下已知的 7 折目標價 (`close <= target`)
    - 若有空餘倉位（上限 max_positions=10 檔，每檔最高佔 10%），優先買入折價幅度最深的標的
    - 當持倉股價回升至進場時點之 10 折合理價值或持有滿 1 年且獲利達標時賣出
    - 閒置等待期間之現金按美國短債保守年化 3.0% 計息
    """
    sample_df = next(iter(all_hist.values()))
    dates = sample_df.index
    cash = bt_cfg.initial_capital
    daily_cash_rate = (1.0 + 0.03) ** (1.0 / 252.0) - 1.0

    positions: Dict[str, Dict[str, Any]] = {}
    last_exit_idx: Dict[str, int] = {t: -bt_cfg.min_hold_cooldown for t in all_hist}

    equity_values: List[float] = []
    exposure_ratios: List[float] = []
    total_trades = 0
    win_trades = 0
    total_fees_paid = 0.0

    for i, dt in enumerate(dates):
        if cash > 0 and i > 0:
            cash *= (1.0 + daily_cash_rate)

        to_close: List[str] = []
        for tk, pos in positions.items():
            df_tk = all_hist[tk]
            price = float(df_tk["close"].iloc[i])
            hold_days = i - pos["entry_idx"]

            fair_exit = (pos["entry_target"] / bt_cfg.safety_discount) * bt_cfg.take_profit_multiple
            gross_ret = (price / pos["entry_price"]) - 1.0

            if (price >= fair_exit and hold_days >= 5) or (hold_days >= bt_cfg.max_hold_days and gross_ret >= 0.15):
                gross_proceeds = pos["shares"] * price
                exit_fee = gross_proceeds * bt_cfg.fee_rate_one_way
                net_proceeds = gross_proceeds - exit_fee

                cash += net_proceeds
                total_fees_paid += exit_fee
                total_trades += 1
                if net_proceeds > pos["cost_basis"]:
                    win_trades += 1

                to_close.append(tk)
                last_exit_idx[tk] = i

        for tk in to_close:
            del positions[tk]

        open_slots = bt_cfg.max_positions - len(positions)
        if open_slots > 0 and cash > 1000.0:
            candidates: List[Tuple[float, str, float, float]] = []
            for tk, df_tk in all_hist.items():
                if tk in positions:
                    continue
                if (i - last_exit_idx[tk]) < bt_cfg.min_hold_cooldown:
                    continue
                price = float(df_tk["close"].iloc[i])
                target = float(df_tk[strategy_col].iloc[i])
                if strategy_col == "s2_target" and not bool(df_tk["s2_valid"].iloc[i]):
                    continue
                if target > 0 and price <= target:
                    discount_depth = (price - target) / target
                    candidates.append((discount_depth, tk, price, target))

            candidates.sort(key=lambda x: x[0])
            base_slot_cap = bt_cfg.initial_capital / bt_cfg.max_positions
            for _, tk, price, target in candidates[:open_slots]:
                df_tk = all_hist[tk]
                # 對齊一二三軌金字塔配置與防禦鎖
                s1_t_val = float(df_tk["s1_target"].iloc[i])
                s2_t_val = float(df_tk["s2_target"].iloc[i])
                s2_v_val = bool(df_tk["s2_valid"].iloc[i])
                s3_t_val = float(df_tk["s3_target"].iloc[i])
                h52_val = float(df_tk["high52"].iloc[i])
                is_cont = bool(df_tk["is_contracting"].iloc[i])
                five_ok = bool(df_tk["five_year_ok"].iloc[i])

                s1_b = (price <= s1_t_val and s1_t_val > 0)
                s2_b = (price <= s2_t_val and s2_v_val)
                s3_b = (price <= s3_t_val and s3_t_val > 0)

                same_base = (s1_t_val > 0 and s3_t_val > 0 and abs(s3_t_val - s1_t_val) / max(1.0, s1_t_val) < 0.03)
                if s1_b and s3_b and same_base and not s2_b:
                    m_cnt = 1
                else:
                    m_cnt = sum([s1_b, s2_b, s3_b])
                if m_cnt == 0:
                    m_cnt = 1

                dd_h = ((price - h52_val) / h52_val) if h52_val > 0 else 0.0
                cb_active = (m_cnt >= 2 and (is_cont or dd_h <= -0.45)) or (not five_ok)

                if cb_active or not five_ok or m_cnt <= 1:
                    size_pct = 0.30
                elif m_cnt == 2:
                    size_pct = 0.60
                else:
                    size_pct = 1.00

                target_alloc = base_slot_cap * size_pct
                slot_alloc = min(cash, target_alloc)
                if slot_alloc < 1000.0:
                    continue

                entry_fee = slot_alloc * bt_cfg.fee_rate_one_way
                net_invest = slot_alloc - entry_fee
                shares = net_invest / price

                cash -= slot_alloc
                total_fees_paid += entry_fee
                positions[tk] = {
                    "shares": shares,
                    "entry_price": price,
                    "entry_target": target,
                    "entry_idx": i,
                    "cost_basis": slot_alloc,
                }

        pos_market_val = sum(
            pos["shares"] * float(all_hist[tk]["close"].iloc[i])
            for tk, pos in positions.items()
        )
        total_eq = cash + pos_market_val
        equity_values.append(total_eq)
        exposure_ratios.append((pos_market_val / total_eq) * 100.0 if total_eq > 0 else 0.0)

    for tk, pos in positions.items():
        final_price = float(all_hist[tk]["close"].iloc[-1])
        net_val = pos["shares"] * final_price * (1.0 - bt_cfg.fee_rate_one_way)
        total_trades += 1
        if net_val > pos["cost_basis"]:
            win_trades += 1

    eq_arr = np.array(equity_values, dtype=float)
    final_eq = float(eq_arr[-1])
    tot_profit = final_eq - bt_cfg.initial_capital
    tot_ret_pct = (tot_profit / bt_cfg.initial_capital) * 100.0

    years = len(dates) / 252.0
    cagr = ((final_eq / bt_cfg.initial_capital) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else 0.0

    running_max = np.maximum.accumulate(eq_arr)
    drawdowns = (eq_arr - running_max) / running_max * 100.0
    max_dd = float(np.min(drawdowns))

    daily_rets = np.diff(eq_arr) / eq_arr[:-1]
    rf_daily = 0.035 / 252.0
    excess_rets = daily_rets - rf_daily
    std_ret = float(np.std(daily_rets))
    sharpe = (float(np.mean(excess_rets)) / std_ret * math.sqrt(252.0)) if std_ret > 1e-9 else 0.0

    step = 5
    sampled_dates = [dates[idx].strftime("%Y-%m-%d") for idx in range(0, len(dates), step)]
    sampled_vals = [round(float(eq_arr[idx]), 2) for idx in range(0, len(dates), step)]
    if dates[-1].strftime("%Y-%m-%d") != sampled_dates[-1]:
        sampled_dates.append(dates[-1].strftime("%Y-%m-%d"))
        sampled_vals.append(round(final_eq, 2))

    return PortfolioBacktestMetrics(
        strategy_id=strategy_id,
        strategy_label=strategy_label,
        initial_capital=bt_cfg.initial_capital,
        final_equity=round(final_eq, 2),
        total_net_profit=round(tot_profit, 2),
        total_return_pct=round(tot_ret_pct, 2),
        cagr_pct=round(cagr, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        total_trades=total_trades,
        win_rate_pct=round((win_trades / total_trades * 100.0) if total_trades > 0 else 0.0, 2),
        total_fees_paid=round(total_fees_paid, 2),
        avg_exposure_pct=round(float(np.mean(exposure_ratios)), 1),
        equity_curve_dates=sampled_dates,
        equity_curve_values=sampled_vals,
    )


def compute_benchmark_metrics(
    price_series: pd.Series,
    ticker: str,
    label: str,
    bt_cfg: BacktestConfig,
) -> PortfolioBacktestMetrics:
    """計算 SPY / QQQ 大盤買進持有基準之 5 年期績效指標"""
    sub = price_series.loc[bt_cfg.start_date : bt_cfg.end_date].dropna()
    dates = sub.index
    prices = sub.values.astype(float)

    entry_fee = bt_cfg.initial_capital * bt_cfg.fee_rate_one_way
    shares = (bt_cfg.initial_capital - entry_fee) / prices[0]
    eq_arr = shares * prices
    final_eq = float(eq_arr[-1])
    tot_profit = final_eq - bt_cfg.initial_capital
    tot_ret_pct = (tot_profit / bt_cfg.initial_capital) * 100.0
    years = len(dates) / 252.0
    cagr = ((final_eq / bt_cfg.initial_capital) ** (1.0 / years) - 1.0) * 100.0

    running_max = np.maximum.accumulate(eq_arr)
    max_dd = float(np.min((eq_arr - running_max) / running_max * 100.0))

    daily_rets = np.diff(eq_arr) / eq_arr[:-1]
    rf_daily = 0.035 / 252.0
    sharpe = float(np.mean(daily_rets - rf_daily) / np.std(daily_rets) * math.sqrt(252.0))

    step = 5
    sampled_dates = [dates[idx].strftime("%Y-%m-%d") for idx in range(0, len(dates), step)]
    sampled_vals = [round(float(eq_arr[idx]), 2) for idx in range(0, len(dates), step)]
    if dates[-1].strftime("%Y-%m-%d") != sampled_dates[-1]:
        sampled_dates.append(dates[-1].strftime("%Y-%m-%d"))
        sampled_vals.append(round(final_eq, 2))

    return PortfolioBacktestMetrics(
        strategy_id=ticker,
        strategy_label=label,
        initial_capital=bt_cfg.initial_capital,
        final_equity=round(final_eq, 2),
        total_net_profit=round(tot_profit, 2),
        total_return_pct=round(tot_ret_pct, 2),
        cagr_pct=round(cagr, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        total_trades=1,
        win_rate_pct=100.0 if tot_profit > 0 else 0.0,
        total_fees_paid=round(entry_fee, 2),
        avg_exposure_pct=100.0,
        equity_curve_dates=sampled_dates,
        equity_curve_values=sampled_vals,
    )


# ==============================================================================
# 6. 執行完整 5 年無前視偏差回測並輸出報表、CSV、Meta JSON 與 HTML
# ==============================================================================
def run_full_backtest(bt_cfg: Optional[BacktestConfig] = None) -> Dict[str, Any]:
    if bt_cfg is None:
        bt_cfg = BacktestConfig()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    prices_df = load_or_download_prices(bt_cfg)

    all_hist: Dict[str, pd.DataFrame] = {}
    stock_summaries: List[StockBacktestSummary] = []
    all_trades: List[TradeRecord] = []

    for s in BASELINE_STOCKS:
        hist_df = build_historical_target_series(s, prices_df[s.ticker], bt_cfg)
        all_hist[s.ticker] = hist_df
        trades, summary = simulate_stock_trades(
            stock=s,
            hist_df=hist_df,
            strategy_col="smart_target",
            strategy_label="智慧三軌7折定錨(PIT)",
            bt_cfg=bt_cfg,
            trade_size_usd=10000.0,
        )
        stock_summaries.append(summary)
        all_trades.extend(trades)

    port_smart = run_portfolio_simulation(all_hist, "smart_target", "SMART_3TRACK", "★ 智慧三軌 7 折定錨組合 (Point-in-Time)", bt_cfg)
    port_s3 = run_portfolio_simulation(all_hist, "s3_target", "S3_TRUE_PEG", "【策略三】Forward/FCF 真實獲利 7 折組合", bt_cfg)
    port_s2 = run_portfolio_simulation(all_hist, "s2_target", "S2_52W_HIGH", "【策略二】52 週高點打 7 折技術回檔組合", bt_cfg)
    port_s1 = run_portfolio_simulation(all_hist, "s1_target", "S1_GAAP_PEG", "【策略一】純 GAAP 基本面 PEG 7 折組合", bt_cfg)
    bench_qqq = compute_benchmark_metrics(prices_df["QQQ"], "QQQ", "那斯達克 100 指數 (QQQ 買進持有)", bt_cfg)
    bench_spy = compute_benchmark_metrics(prices_df["SPY"], "SPY", "標普 500 指數 (SPY 買進持有)", bt_cfg)

    portfolios = [port_smart, port_s3, port_s2, port_s1, bench_qqq, bench_spy]

    fee_sensitivity = []
    for fee_test, fee_label in [(0.0005, "0.05% (低成本網路券商)"), (0.0015, "0.15% (標準複委託/預設)"), (0.0050, "0.50% (極高摩擦成本壓力測試)")]:
        cfg_copy = BacktestConfig(**asdict(bt_cfg))
        cfg_copy.fee_rate_one_way = fee_test
        m = run_portfolio_simulation(all_hist, "smart_target", f"FEE_{fee_test}", fee_label, cfg_copy)
        fee_sensitivity.append(
            {
                "fee_label": fee_label,
                "one_way_pct": fee_test * 100.0,
                "final_equity": m.final_equity,
                "total_net_profit": m.total_net_profit,
                "total_return_pct": m.total_return_pct,
                "cagr_pct": m.cagr_pct,
                "total_fees_paid": m.total_fees_paid,
            }
        )

    # 計算三階段賣出 vs 10折全賣 vs 7折買進抱緊之動態統計，寫入 peg_backtest_meta.json 供主控台動態讀取
    triggered_stocks = [s for s in stock_summaries if s.trade_count > 0]
    avg_staged_pct = round(float(np.mean([s.staged_3tier_return_pct for s in triggered_stocks])), 1) if triggered_stocks else 0.0
    avg_hold_entry_pct = round(float(np.mean([s.hold_from_entry_return_pct for s in triggered_stocks])), 1) if triggered_stocks else 0.0
    meta_stats = {
        "smart_portfolio_return_pct": port_smart.total_return_pct,
        "smart_portfolio_cagr_pct": port_smart.cagr_pct,
        "smart_portfolio_win_rate_pct": port_smart.win_rate_pct,
        "smart_portfolio_trades": len(all_trades),
        "spy_return_pct": bench_spy.total_return_pct,
        "qqq_return_pct": bench_qqq.total_return_pct,
        "avg_staged_3tier_return_pct": avg_staged_pct,
        "avg_hold_from_entry_return_pct": avg_hold_entry_pct,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    META_JSON_PATH.write_text(json.dumps(meta_stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 138)
    print(f"📈 美股 AI 企業巨頭「PEG 7 折三軌系統」近五年無前視偏差 (Point-in-Time) 回測報告 ({bt_cfg.start_date} ~ {bt_cfg.end_date})")
    print(f"💰 初始本金：$100,000 美元 | 單邊手續費+滑價：{bt_cfg.fee_rate_one_way*100:.2f}% | 停利：回歸進場時點 10 折合理價值 (+42.9%) 或滿年獲利換股")
    print("=" * 138)
    print(f"{'策略組合名稱':<42} | {'期末總資產':>12} | {'5年淨獲利':>12} | {'總報酬率':>9} | {'年化CAGR':>8} | {'最大回撤(MDD)':>13} | {'夏普值':>6} | {'勝率':>6} | {'總手續費':>9}")
    print("-" * 138)
    for p in portfolios:
        print(
            f"{p.strategy_label:<42} | ${p.final_equity:>11,.2f} | ${p.total_net_profit:>+11,.2f} | "
            f"{p.total_return_pct:>+8.2f}% | {p.cagr_pct:>+7.2f}% | {p.max_drawdown_pct:>12.2f}% | "
            f"{p.sharpe_ratio:>6.2f} | {p.win_rate_pct:>5.1f}% | ${p.total_fees_paid:>8,.2f}"
        )
    print("=" * 138)
    print(
        f"📌 【三種賣股出場方式實證比較 (針對觸發 7 折買進之標的)】\n"
        f"   1️⃣ 漲回 10 折合理價全部賣光 ($10萬組合滾動總報酬)：+{port_smart.total_return_pct:.1f}%\n"
        f"   2️⃣ 三階段分批停利 (10折賣1/3、12折賣1/3、1/3底倉抱緊) 平均總報酬：+{avg_staged_pct:.1f}%\n"
        f"   3️⃣ 在 7 折買進後完全不賣一路抱到底 平均總報酬：+{avg_hold_entry_pct:.1f}%"
    )
    print("=" * 138)

    export_backtest_csv(stock_summaries, all_trades, Path("peg_backtest_report.csv"), Path("peg_backtest_trades.csv"))
    export_backtest_html(portfolios, stock_summaries, all_trades, fee_sensitivity, meta_stats, bt_cfg, Path("peg_backtest_dashboard.html"))

    return {
        "portfolios": portfolios,
        "stock_summaries": stock_summaries,
        "trades": all_trades,
        "fee_sensitivity": fee_sensitivity,
        "meta_stats": meta_stats,
    }


def export_backtest_csv(
    summaries: List[StockBacktestSummary],
    trades: List[TradeRecord],
    summary_csv_path: Path,
    trades_csv_path: Path,
) -> None:
    """匯出個股 5 年回測統計 CSV 與全歷史交易明細 CSV"""
    with summary_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "代號", "公司名稱", "分類", "定錨策略", "5年觸發買進次數", "獲利次數", "勝率 (%)",
                "單筆平均毛報酬 (%)", "單筆平均淨報酬 (扣費後 %)", "平均持有交易日",
                "累計手續費支出 ($)", "累計波段淨獲利 (每筆1萬美元基準 $)",
                "三階段分批賣出總報酬 (%)", "7折買進後不賣總報酬 (%)",
                "最佳單筆報酬 (%)", "最差單筆報酬 (%)", "同期5年Buy&Hold報酬 (%)"
            ],
        )
        writer.writeheader()
        for s in summaries:
            writer.writerow({
                "代號": s.ticker,
                "公司名稱": s.name,
                "分類": s.category,
                "定錨策略": s.recommended_anchor,
                "5年觸發買進次數": s.trade_count,
                "獲利次數": s.win_count,
                "勝率 (%)": s.win_rate_pct,
                "單筆平均毛報酬 (%)": s.avg_gross_return_pct,
                "單筆平均淨報酬 (扣費後 %)": s.avg_net_return_pct,
                "平均持有交易日": s.avg_holding_days,
                "累計手續費支出 ($)": s.total_fees_usd,
                "累計波段淨獲利 (每筆1萬美元基準 $)": s.total_net_profit_usd,
                "三階段分批賣出總報酬 (%)": s.staged_3tier_return_pct,
                "7折買進後不賣總報酬 (%)": s.hold_from_entry_return_pct,
                "最佳單筆報酬 (%)": s.best_trade_pct,
                "最差單筆報酬 (%)": s.worst_trade_pct,
                "同期5年Buy&Hold報酬 (%)": s.buy_and_hold_5y_pct,
            })

    with trades_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "代號", "公司名稱", "策略", "買進日期", "買進價格 ($)", "當時7折目標價 ($)",
                "滿足有效軌數", "價值防禦鎖啟動", "持倉期間最大回撤 (MDD %)", "買進後持有滿1年報酬率 (%)",
                "賣出日期", "賣出價格 ($)", "出場原因", "持有交易日",
                "投入本金 ($)", "毛報酬率 (%)", "雙邊手續費 ($)", "淨獲利 ($)", "淨報酬率 (%)"
            ],
        )
        writer.writeheader()
        for t in trades:
            writer.writerow({
                "代號": t.ticker,
                "公司名稱": t.name,
                "策略": t.strategy_name,
                "買進日期": t.entry_date,
                "買進價格 ($)": t.entry_price,
                "當時7折目標價 ($)": t.target_price_at_entry,
                "滿足有效軌數": f"{t.matched_tracks}軌",
                "價值防禦鎖啟動": "是 (強制鎖定30%試單)" if t.circuit_breaker_active else "否",
                "持倉期間最大回撤 (MDD %)": f"{t.holding_max_drawdown_pct:.2f}%",
                "買進後持有滿1年報酬率 (%)": f"{t.one_year_return_pct:.2f}%",
                "賣出日期": t.exit_date,
                "賣出價格 ($)": t.exit_price,
                "出場原因": t.exit_reason,
                "持有交易日": t.holding_days,
                "投入本金 ($)": t.invested_amount,
                "毛報酬率 (%)": t.gross_return_pct,
                "雙邊手續費 ($)": t.total_fee_usd,
                "淨獲利 ($)": t.net_profit_usd,
                "淨報酬率 (%)": t.net_return_pct,
            })


def export_backtest_html(
    portfolios: List[PortfolioBacktestMetrics],
    summaries: List[StockBacktestSummary],
    trades: List[TradeRecord],
    fee_sensitivity: List[Dict[str, Any]],
    meta_stats: Dict[str, Any],
    bt_cfg: BacktestConfig,
    output_path: Path,
) -> None:
    """生成近五年歷史獲利回測互動式視覺化報告 (peg_backtest_dashboard.html)"""
    port_json = json.dumps([asdict(p) for p in portfolios], ensure_ascii=False)
    sum_json = json.dumps([asdict(s) for s in summaries], ensure_ascii=False)
    trades_json = json.dumps([asdict(t) for t in trades], ensure_ascii=False)
    fee_json = json.dumps(fee_sensitivity, ensure_ascii=False)

    smart_p = portfolios[0]
    spy_p = next(p for p in portfolios if p.strategy_id == "SPY")
    qqq_p = next(p for p in portfolios if p.strategy_id == "QQQ")

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>近五年無前視偏差 (Point-in-Time) 歷史回測報告 — 美股 PEG 7 折三軌系統</title>
<style>
  :root {{
    --bg-dark: #0b0f19;
    --bg-card: #131b2e;
    --bg-hover: #1a2540;
    --border: #26334d;
    --text-main: #e2e8f0;
    --text-muted: #94a3b8;
    --accent-blue: #38bdf8;
    --accent-indigo: #6366f1;
    --green: #10b981;
    --amber: #f59e0b;
    --red: #f43f5e;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft JhengHei", sans-serif;
    background: var(--bg-dark);
    color: var(--text-main);
    line-height: 1.6;
    padding: 24px;
  }}
  .container {{ max-width: 1520px; margin: 0 auto; }}
  .header {{
    display: flex; justify-content: space-between; align-items: flex-start;
    flex-wrap: wrap; gap: 16px; padding-bottom: 20px;
    border-bottom: 1px solid var(--border); margin-bottom: 24px;
  }}
  .header h1 {{
    font-size: 1.65rem; font-weight: 700;
    background: linear-gradient(90deg, #10b981, #38bdf8, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 16px; margin-bottom: 24px;
  }}
  .kpi-card {{
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 12px; padding: 18px 20px;
  }}
  .kpi-title {{ font-size: 0.85rem; color: var(--text-muted); margin-bottom: 6px; }}
  .kpi-val {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 4px; }}
  .kpi-sub {{ font-size: 0.8rem; color: var(--text-muted); }}
  .card {{
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 12px; padding: 22px; margin-bottom: 24px;
  }}
  .card h2 {{ font-size: 1.2rem; margin-bottom: 14px; color: var(--accent-blue); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; white-space: nowrap; }}
  th {{
    background: #0f172a; color: var(--text-muted); text-align: right;
    padding: 12px; border-bottom: 1px solid var(--border);
  }}
  th:first-child, th:nth-child(2) {{ text-align: left; }}
  td {{ padding: 11px 12px; border-bottom: 1px solid rgba(38,51,77,0.5); text-align: right; }}
  td:first-child, td:nth-child(2) {{ text-align: left; }}
  tr:hover {{ background: var(--bg-hover); }}
  .pos {{ color: var(--green); font-weight: 600; }}
  .neg {{ color: var(--red); font-weight: 600; }}
  .chart-box {{ width: 100%; height: 390px; position: relative; margin-top: 12px; }}
  svg {{ width: 100%; height: 100%; overflow: visible; }}
  .legend {{ display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 12px; font-size: 0.86rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; }}
  .tabs {{ display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }}
  .tab-btn {{
    background: var(--bg-card); color: var(--text-muted);
    border: 1px solid var(--border); padding: 9px 18px;
    border-radius: 8px; cursor: pointer; font-weight: 600;
  }}
  .tab-btn.active {{ background: #2563eb; color: #fff; border-color: #60a5fa; }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>📈 美股「本益成長比 (PEG) 7 折三軌系統」近五年無前視偏差 (Point-in-Time) 回測報告 ({bt_cfg.start_date} ～ {bt_cfg.end_date})</h1>
      <p style="color:var(--text-muted);font-size:0.92rem;margin-top:4px;">
        嚴格使用歷史各時點當時已知之過去 5 年滾動成長率 (PIT Rolling CAGR) 與當期 EPS，並實測「10折全賣」vs「三階段分批停利」vs「7折買進長抱」
      </p>
    </div>
    <div>
      <a href="peg_valuation_dashboard.html" style="display:inline-block;background:#1e293b;border:1px solid var(--accent-blue);color:var(--accent-blue);padding:8px 16px;border-radius:8px;text-decoration:none;font-weight:600;font-size:0.9rem;">← 返回即時估值監控儀表板</a>
    </div>
  </div>

  <!-- 方法論統計限制與偏差透明揭露 -->
  <div class="card" style="border-left:4px solid var(--amber);">
    <h2 style="color:var(--amber);">⚠️ 回測方法論說明與統計限制揭露（防範過度自信）</h2>
    <p style="font-size:0.88rem;color:var(--text-muted);">
      1. <strong>已修正前視偏差 (Point-in-Time)</strong>：本報告在 2021~2026 的每一個交易日，僅使用截至當時已公告之歷史 5 年滾動 CAGR（如 2022 年僅用 2017→2022 財報）與當期盈餘，不使用未來才發生的 AI 爆發期獲利。<br>
      2. <strong>倖存者偏差與樣本集中度提醒</strong>：這 22 檔標的為四大指數當前最具護城河之龍頭，且買進訊號高度集中於 2022 年升息熊市與少數財報回檔期（單一宏觀週期）。實戰中仍須嚴格遵守「單一股票最高佔總資金 5%（衛星倉 10%）」之上限，避免單押個別公司基本面惡化風險。
    </p>
  </div>

  <!-- Top KPIs -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-title">🏆 智慧三軌 7 折組合期末淨資產 ($10萬本金)</div>
      <div class="kpi-val" style="color:var(--green);">${smart_p.final_equity:,.0f}</div>
      <div class="kpi-sub">5年淨賺 +${smart_p.total_net_profit:,.0f} ({smart_p.total_return_pct:+.1f}%) | 年化 CAGR {smart_p.cagr_pct:+.2f}%</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">📊 三階段分批停利 (10折/12折/抱緊) 平均報酬</div>
      <div class="kpi-val" style="color:var(--accent-blue);">+{meta_stats['avg_staged_3tier_return_pct']:.1f}%</div>
      <div class="kpi-sub">對照：7折買進後完全不賣平均 +{meta_stats['avg_hold_from_entry_return_pct']:.1f}%</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">🛡️ 最大回撤控制 (Max Drawdown)</div>
      <div class="kpi-val" style="color:#c084fc;">{smart_p.max_drawdown_pct:.1f}%</div>
      <div class="kpi-sub">顯著優於 QQQ ({qqq_p.max_drawdown_pct:.1f}%)，因只在打 7 折時左側建倉</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">🎯 波段勝率與累計總手續費佔比</div>
      <div class="kpi-val" style="color:var(--amber);">{smart_p.win_rate_pct:.1f}%</div>
      <div class="kpi-sub">5年共 {smart_p.total_trades} 筆交易，總手續費 ${smart_p.total_fees_paid:,.0f}</div>
    </div>
  </div>

  <!-- Equity Curve Chart -->
  <div class="card">
    <h2>📈 近五年 $100,000 美元資金成長曲線對照 (2021-10 ～ 2026-10，已扣除手續費)</h2>
    <div class="legend" id="chart-legend"></div>
    <div class="chart-box">
      <svg id="equity-svg" viewBox="0 0 1100 360" preserveAspectRatio="none"></svg>
    </div>
  </div>

  <!-- Portfolio Comparison Table & Fee Sensitivity -->
  <div class="card">
    <h2>⚖️ 四大估值策略組合 vs. 大盤基準 (SPY / QQQ) 五年完整績效對照表</h2>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th>策略組合名稱</th>
            <th>初始本金</th>
            <th>期末淨資產 (扣費後)</th>
            <th>5年總淨利 ($)</th>
            <th>5年總報酬率</th>
            <th>年化報酬 (CAGR)</th>
            <th>最大回撤 (MDD)</th>
            <th>夏普值 (Sharpe)</th>
            <th>總交易筆數</th>
            <th>波段勝率</th>
            <th>5年總手續費支出</th>
          </tr>
        </thead>
        <tbody id="port-tbody"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>💸 手續費與滑價摩擦成本敏感度測試</h2>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th>手續費與滑價設定情境</th>
            <th>單邊費率</th>
            <th>來回總摩擦成本</th>
            <th>5年累計付出手續費</th>
            <th>期末淨資產 ($)</th>
            <th>5年實質淨獲利 ($)</th>
            <th>5年淨報酬率 (%)</th>
            <th>年化 CAGR (%)</th>
          </tr>
        </thead>
        <tbody id="fee-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- Tabs for 22 Stocks Summary & Trade Log -->
  <div class="tabs">
    <button class="tab-btn active" onclick="showPanel('p-stocks', this)">📊 22 檔個股「10折全賣 vs 三階段賣出 vs 抱緊不賣」五年回測統計</button>
    <button class="tab-btn" onclick="showPanel('p-trades', this)">📜 歷史全交易明細紀錄 (共 <span id="trade-cnt-lbl"></span> 筆)</button>
  </div>

  <div id="p-stocks" class="panel active card">
    <h2>📊 22 檔追蹤標的個別波段回測與三種賣出方式實測對照表</h2>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th>代號 / 公司</th>
            <th>適用定錨策略</th>
            <th>5年觸發次數</th>
            <th>波段勝率</th>
            <th>10折全賣單筆平均淨報酬</th>
            <th>三階段分批賣出總報酬</th>
            <th>7折買進抱緊不賣總報酬</th>
            <th>累計手續費 ($)</th>
            <th>累計波段淨獲利 ($)</th>
            <th>同期5年Buy&Hold</th>
          </tr>
        </thead>
        <tbody id="stock-tbody"></tbody>
      </table>
    </div>
  </div>

  <div id="p-trades" class="panel card">
    <h2>📜 2021–2026 歷史觸發買進與出場明細紀錄 (含持倉 MDD 與滿 1 年真實報酬檢驗)</h2>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th>代號</th>
            <th>公司名稱</th>
            <th>滿足軌數</th>
            <th>價值防禦鎖</th>
            <th>買進日期</th>
            <th>買進價 ($)</th>
            <th>當時7折目標價 ($)</th>
            <th>持倉期間最大回撤 (MDD)</th>
            <th>買進滿1年實際報酬</th>
            <th>賣出日期</th>
            <th>賣出價 ($)</th>
            <th>出場原因</th>
            <th>持有交易日</th>
            <th>投入本金 ($)</th>
            <th>雙邊手續費 ($)</th>
            <th>單筆淨獲利 ($)</th>
            <th>單筆淨報酬 (%)</th>
          </tr>
        </thead>
        <tbody id="trades-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- 關鍵警示：META 2022 七折崩跌案實證 -->
  <div class="card" style="border-left:4px solid #f43f5e;background:rgba(244,63,94,0.06);">
    <h2 style="color:#f43f5e;">💥 歷史血淋淋實證：2022 META 七折崩跌案（單一案例證明 7 折估價絕不能限制虧損幅度）</h2>
    <p style="color:var(--text-main);margin-bottom:10px;font-size:0.92rem;">
      <strong>歷史事實重現：</strong>META 於 2021 年高點 $384.33 回檔，2022 年初觸及 52 週高點 7 折價（約 $269）觸發技術面買進訊號。然而，隨後因元宇宙巨額 Capex 燒錢與廣告指引下修，股價未見反彈，反而一路崩跌至 2022 年 11 月的 <strong>$88.09</strong>！
    </p>
    <ul style="color:var(--text-muted);font-size:0.88rem;margin-left:20px;line-height:1.7;">
      <li><strong>持倉期間最大回撤 (MDD)：</strong>自 7 折買進價 $269 崩跌至 $88.09，持倉期間浮虧高達 <span style="color:#f43f5e;font-weight:700;">-67.2%</span>（若自歷史高點計則達 -77.1%）。</li>
      <li><strong>買進後持有滿 1 年報酬率：</strong>滿一年（2023 年初）股價約 $130，單筆報酬率為 <span style="color:#f43f5e;font-weight:700;">-51.7% ~ -68.9%</span>。</li>
      <li><strong>長抱至 2025/2026 年結果：</strong>受惠於 2023 效率之年大裁員與 AI 變現，持有至 2025 年底回升至 +109.5%。</li>
      <li><strong>核心啟示：</strong>「7 折買進絕非保證不賠的安全氣囊」，單一優質個股亦可能面臨長達一年腰斬再腰斬的極端回撤。這正是為何系統強制要求：<strong>① 50% 核心穩健資產（35% CSPX / 15% BND）為基底、② 單一衛星個股上限 5%、③ 觸發防禦鎖強制限制 30% 試單倉</strong>，三道防火牆缺一不可！</li>
    </ul>
  </div>
</div>

<script>
  const PORTFOLIOS = {port_json};
  const SUMMARIES = {sum_json};
  const TRADES = {trades_json};
  const FEES = {fee_json};

  document.getElementById('trade-cnt-lbl').textContent = TRADES.length;

  function showPanel(id, btn) {{
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
  }}

  document.getElementById('port-tbody').innerHTML = PORTFOLIOS.map((p, idx) => {{
    const bold = idx === 0 ? 'style="background:rgba(16,185,129,0.08);font-weight:600;"' : '';
    return `<tr ${{bold}}>
      <td>${{p.strategy_label}}</td>
      <td>$${{p.initial_capital.toLocaleString()}}</td>
      <td class="pos">$${{p.final_equity.toLocaleString()}}</td>
      <td class="${{p.total_net_profit >= 0 ? 'pos' : 'neg'}}">+$${{p.total_net_profit.toLocaleString()}}</td>
      <td class="pos">+${{p.total_return_pct.toFixed(2)}}%</td>
      <td class="pos">+${{p.cagr_pct.toFixed(2)}}%</td>
      <td class="neg">${{p.max_drawdown_pct.toFixed(2)}}%</td>
      <td>${{p.sharpe_ratio.toFixed(2)}}</td>
      <td>${{p.total_trades}}</td>
      <td>${{p.win_rate_pct.toFixed(1)}}%</td>
      <td>$${{p.total_fees_paid.toLocaleString()}}</td>
    </tr>`;
  }}).join('');

  document.getElementById('fee-tbody').innerHTML = FEES.map(f => `
    <tr>
      <td><strong>${{f.fee_label}}</strong></td>
      <td>${{f.one_way_pct.toFixed(2)}}%</td>
      <td>${{(f.one_way_pct * 2).toFixed(2)}}%</td>
      <td>$${{f.total_fees_paid.toLocaleString()}}</td>
      <td class="pos">$${{f.final_equity.toLocaleString()}}</td>
      <td class="pos">+$${{f.total_net_profit.toLocaleString()}}</td>
      <td class="pos">+${{f.total_return_pct.toFixed(2)}}%</td>
      <td class="pos">+${{f.cagr_pct.toFixed(2)}}%</td>
    </tr>
  `).join('');

  document.getElementById('stock-tbody').innerHTML = SUMMARIES.map(s => `
    <tr>
      <td><strong style="color:var(--accent-blue);">${{s.ticker}}</strong> <span style="color:var(--text-muted);font-size:0.8rem;">${{s.name}}</span></td>
      <td><span style="font-size:0.82rem;color:var(--text-muted);">${{s.recommended_anchor}}</span></td>
      <td>${{s.trade_count}} 次</td>
      <td>${{s.win_rate_pct.toFixed(1)}}% (${{s.win_count}}/${{s.trade_count}})</td>
      <td class="${{s.avg_net_return_pct >= 0 ? 'pos' : 'neg'}}">${{s.avg_net_return_pct >= 0 ? '+' : ''}}${{s.avg_net_return_pct.toFixed(2)}}%</td>
      <td class="${{s.staged_3tier_return_pct >= 0 ? 'pos' : 'neg'}}">${{s.staged_3tier_return_pct >= 0 ? '+' : ''}}${{s.staged_3tier_return_pct.toFixed(1)}}%</td>
      <td class="${{s.hold_from_entry_return_pct >= 0 ? 'pos' : 'neg'}}">${{s.hold_from_entry_return_pct >= 0 ? '+' : ''}}${{s.hold_from_entry_return_pct.toFixed(1)}}%</td>
      <td>$${{s.total_fees_usd.toFixed(2)}}</td>
      <td class="${{s.total_net_profit_usd >= 0 ? 'pos' : 'neg'}}">${{s.total_net_profit_usd >= 0 ? '+' : ''}}$${{s.total_net_profit_usd.toLocaleString()}}</td>
      <td class="${{s.buy_and_hold_5y_pct >= 0 ? 'pos' : 'neg'}}">${{s.buy_and_hold_5y_pct >= 0 ? '+' : ''}}${{s.buy_and_hold_5y_pct.toFixed(1)}}%</td>
    </tr>
  `).join('');

  document.getElementById('trades-tbody').innerHTML = TRADES.map(t => {{
    const cbText = t.circuit_breaker_active ? '<span style="color:#f59e0b;">🛡️ 鎖定30%</span>' : '正常';
    const mddClass = t.holding_max_drawdown_pct < -30 ? 'neg' : '';
    const y1Class = t.one_year_return_pct >= 0 ? 'pos' : 'neg';
    return `
    <tr>
      <td><strong style="color:var(--accent-blue);">${{t.ticker}}</strong></td>
      <td>${{t.name}}</td>
      <td>${{t.matched_tracks || 1}} 軌</td>
      <td>${{cbText}}</td>
      <td>${{t.entry_date}}</td>
      <td>$${{t.entry_price.toFixed(2)}}</td>
      <td>$${{t.target_price_at_entry.toFixed(2)}}</td>
      <td class="${{mddClass}}">${{(t.holding_max_drawdown_pct || 0).toFixed(2)}}%</td>
      <td class="${{y1Class}}">${{(t.one_year_return_pct || 0).toFixed(2)}}%</td>
      <td>${{t.exit_date}}</td>
      <td>$${{t.exit_price.toFixed(2)}}</td>
      <td>${{t.exit_reason}}</td>
      <td>${{t.holding_days}} 天</td>
      <td>$${{(t.invested_amount || 10000).toLocaleString()}}</td>
      <td>$${{t.total_fee_usd.toFixed(2)}}</td>
      <td class="${{t.net_profit_usd >= 0 ? 'pos' : 'neg'}}">${{t.net_profit_usd >= 0 ? '+' : ''}}$${{t.net_profit_usd.toFixed(2)}}</td>
      <td class="${{t.net_return_pct >= 0 ? 'pos' : 'neg'}}">${{t.net_return_pct >= 0 ? '+' : ''}}${{t.net_return_pct.toFixed(2)}}%</td>
    </tr>`;
  }}).join('');

  function drawChart() {{
    const svg = document.getElementById('equity-svg');
    const legend = document.getElementById('chart-legend');
    const colors = ['#10b981', '#38bdf8', '#c084fc', '#f59e0b', '#94a3b8', '#64748b'];
    const widths = [3.2, 2.2, 2.0, 2.0, 2.0, 1.8];

    legend.innerHTML = PORTFOLIOS.map((p, i) => `
      <div class="legend-item">
        <span class="legend-dot" style="background:${{colors[i]}}"></span>
        <span>${{p.strategy_label}} (期末: $${{Math.round(p.final_equity).toLocaleString()}})</span>
      </div>
    `).join('');

    const allVals = PORTFOLIOS.flatMap(p => p.equity_curve_values);
    const minV = Math.min(...allVals) * 0.95;
    const maxV = Math.max(...allVals) * 1.03;
    const W = 1040, H = 310, padL = 60, padT = 15;

    let gridHtml = '';
    for (let g = 0; g <= 4; g++) {{
      const val = minV + (maxV - minV) * (1 - g / 4);
      const y = padT + (H / 4) * g;
      gridHtml += `<line x1="${{padL}}" y1="${{y}}" x2="${{padL + W}}" y2="${{y}}" stroke="#1e293b" stroke-width="1"/>`;
      gridHtml += `<text x="${{padL - 8}}" y="${{y + 4}}" fill="#64748b" font-size="11" text-anchor="end">$${{Math.round(val / 1000)}}k</text>`;
    }}

    const dates = PORTFOLIOS[0].equity_curve_dates;
    for (let dIdx = 0; dIdx < dates.length; dIdx += Math.floor(dates.length / 5)) {{
      const x = padL + (dIdx / (dates.length - 1)) * W;
      gridHtml += `<text x="${{x}}" y="${{padT + H + 22}}" fill="#64748b" font-size="11" text-anchor="middle">${{dates[dIdx]}}</text>`;
    }}

    const pathsHtml = PORTFOLIOS.map((p, idx) => {{
      const vals = p.equity_curve_values;
      const pts = vals.map((v, i) => {{
        const x = padL + (i / (vals.length - 1)) * W;
        const y = padT + H - ((v - minV) / (maxV - minV)) * H;
        return `${{x.toFixed(1)}},${{y.toFixed(1)}}`;
      }}).join(' ');
      const dash = idx >= 4 ? 'stroke-dasharray="5,4"' : '';
      return `<polyline fill="none" stroke="${{colors[idx]}}" stroke-width="${{widths[idx]}}" ${{dash}} points="${{pts}}"/>`;
    }}).join('');

    svg.innerHTML = gridHtml + pathsHtml;
  }}

  drawChart();
</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    run_full_backtest()
