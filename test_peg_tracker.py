#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美股「本益成長比 (PEG) 7 折三軌監控系統」與「近五年歷史獲利回測引擎」自動化單元測試
驗證規格書 (peg_tracker_spec.md) 之所有數學公式、邊界條件、22 檔基準標的驗算與 5 年回測邏輯。
"""

from us_ai_peg_tracker import (
    BASELINE_STOCKS,
    ValuationConfig,
    analyze_stock,
    calculate_cagr,
    evaluate_signal,
    fetch_live_stock_metrics,
    load_stock_universe,
    run_tracker,
)
from peg_backtester import (
    BacktestConfig,
    HISTORICAL_PIT_EPS_DB,
    build_historical_target_series,
    run_full_backtest,
)


def test_cagr_formula_matches_spec():
    """驗證規格書 3.2 節與第 4 節之歷史年均複合成長率 (CAGR) 計算精準度"""
    cagr_googl = calculate_cagr(2.96, 10.91, 5)
    assert round(cagr_googl, 2) == 29.81

    cagr_nvda = calculate_cagr(0.16, 4.06, 5)
    assert round(cagr_nvda, 2) == 90.93

    cagr_pltr = calculate_cagr(0.09, 0.69, 2)
    assert abs(cagr_pltr - 176.69) < 0.25


def test_servicenow_three_track_example():
    """
    驗證規格書 3.3 節之實證案例：NOW (ServiceNow)
    - GAAP TTM EPS = $1.60, CAGR = 69.72% (封頂 45.0 倍，打 7 折為 31.5 倍)
    - 策略一 7 折目標價 = $1.60 * 45 * 0.70 = $50.40
    - 策略二 7 折目標價 = $192.97 * 0.70 = $135.08
    - 策略三 7 折目標價 (Forward EPS $4.18) = $4.18 * 45 * 0.70 = $131.67
    """
    cfg = ValuationConfig(safety_discount=0.70, max_pe_cap=45.0, min_cagr_floor=5.0, near_target_threshold=0.10)
    now_stock = next(s for s in BASELINE_STOCKS if s.ticker == "NOW")
    metrics = fetch_live_stock_metrics(now_stock, use_offline=True)
    res = analyze_stock(now_stock, metrics, cfg)

    assert res.capped_pe == 45.0
    assert res.discounted_pe == 31.5
    assert res.s1_target_price == 50.40
    assert res.s2_target_price == 135.08
    assert res.s3_target_price == 131.67
    assert res.s2_backtest_valid is True


def test_track_1_3_deduplication_when_identical():
    """驗證當策略一與策略三因獲利基數相同（差距 < 3%）同時觸發買進且策略二未觸發時，自動去重算作 1 軌"""
    cfg = ValuationConfig()
    googl = next(s for s in BASELINE_STOCKS if s.ticker == "GOOGL")
    metrics = {
        "price": 180.0,
        "high52": 240.0,  # s2_target = 168.0 < 180.0 (WAIT)
        "low52": 150.0,
        "ttm_eps": 10.91,
        "forward_eps": 10.91,  # 與 GAAP 完全相同
        "fcf_per_share": 9.50,
        "data_source": "HYBRID (即時報價 + 備援:Forward_EPS)",
        "fallback_fields": ["Forward_EPS"],
    }
    res = analyze_stock(googl, metrics, cfg)
    assert res.s1_signal == "BUY"
    assert res.s3_signal == "BUY"
    assert res.s2_signal != "BUY"
    assert res.matched_tracks_count == 1
    assert "同源獲利" in res.overall_signal


def test_fundamental_circuit_breaker():
    """驗證價值陷阱防禦鎖：當觸發 >=2 軌買進，但當期 EPS 較基準衰退超過 20% 或自高點深跌超過 45% 時，強制限制在 30% 試單倉"""
    cfg = ValuationConfig()
    adbe = next(s for s in BASELINE_STOCKS if s.ticker == "ADBE")
    metrics = {
        "price": 100.0,
        "high52": 250.0,  # 深跌 -60% (<= -45%)
        "low52": 95.0,
        "ttm_eps": 11.0,  # 較 2025 基準 16.01 衰退 > 20%
        "forward_eps": 20.5,
        "fcf_per_share": 20.0,
        "data_source": "LIVE",
        "fallback_fields": [],
    }
    res = analyze_stock(adbe, metrics, cfg)
    assert res.matched_tracks_count >= 2
    assert res.circuit_breaker_triggered is True
    assert "30%" in res.alloc_pct_suggestion
    assert "防禦鎖" in res.overall_signal


def test_load_stock_universe_does_not_mutate_baseline():
    """驗證載入 watchlist_config.json 不會變動全域 BASELINE_STOCKS 常數物件"""
    orig_nvda = next(s for s in BASELINE_STOCKS if s.ticker == "NVDA")
    universe = load_stock_universe()
    loaded_nvda = next(s for s in universe if s.ticker == "NVDA")
    assert orig_nvda is not loaded_nvda


def test_all_22_stocks_offline_execution():
    """驗證全部 22 檔追蹤標的在離線備援模式下可完整計算且無任何缺漏"""
    cfg = ValuationConfig()
    results = run_tracker(cfg=cfg, use_offline=True)
    assert len(results) == 22


def test_signal_threshold_logic():
    """驗證 BUY / NEAR (+10% 內) / WAIT 燈號判定邏輯"""
    sig_buy, diff_buy = evaluate_signal(95.0, 100.0, 0.10)
    assert sig_buy == "BUY"
    assert round(diff_buy, 2) == -5.00

    sig_near, diff_near = evaluate_signal(108.0, 100.0, 0.10)
    assert sig_near == "NEAR"
    assert round(diff_near, 2) == 8.00

    sig_wait, diff_wait = evaluate_signal(115.0, 100.0, 0.10)
    assert sig_wait == "WAIT"
    assert round(diff_wait, 2) == 15.00


def test_negative_eps_and_loss_lockout():
    """驗證當標的每股盈餘或現金流為虧損時，目標價強制歸零且觸發虧損禁買防禦"""
    cfg = ValuationConfig()
    stock = next(s for s in BASELINE_STOCKS if s.ticker == "PLTR")
    # 模擬當期 GAAP TTM EPS 為負數，且真實現金流亦為負數
    metrics = {
        "price": 25.0,
        "high52": 40.0,
        "low52": 15.0,
        "ttm_eps": -0.50,
        "forward_eps": -0.10,
        "fcf_per_share": -0.80,
        "data_source": "LIVE",
        "fallback_fields": [],
    }
    res = analyze_stock(stock, metrics, cfg)
    assert res.s1_target_price == 0.0
    assert res.s1_signal == "WAIT"
    assert res.s3_target_price == 0.0
    assert res.s3_signal == "WAIT"
    assert res.matched_tracks_count == 0
    assert "⛔ 虧損禁買" in res.overall_signal
    assert "0%" in res.alloc_pct_suggestion


def test_five_year_consecutive_profit_check():
    """驗證彼得林區五年連續獲利檢驗：PLTR 與 PANW 存在虧損年度，策略一禁用且倉位限制 30%"""
    cfg = ValuationConfig()
    pltr = next(s for s in BASELINE_STOCKS if s.ticker == "PLTR")
    metrics = fetch_live_stock_metrics(pltr, use_offline=True)
    res = analyze_stock(pltr, metrics, cfg)

    assert res.five_year_profitable is False
    assert len(res.loss_years) > 0
    assert res.s1_target_price == 0.0  # 策略一強制停用
    assert res.s1_signal == "WAIT"
    if res.matched_tracks_count > 0:
        assert "30%" in res.alloc_pct_suggestion


def test_sec_edgar_override_valuation():
    """驗證當提供 SEC EDGAR 官方 10-K 資料時，系統會直接重算 CAGR 與目標價"""
    cfg = ValuationConfig()
    googl = next(s for s in BASELINE_STOCKS if s.ticker == "GOOGL")
    metrics = fetch_live_stock_metrics(googl, use_offline=True)
    # 提供官方 10-K 數據 (例如最新 FY2025 EPS 為 12.00，基準年 FY2020 為 2.96)
    metrics["sec_edgar_eps"] = {2020: 2.96, 2025: 12.00}

    res = analyze_stock(googl, metrics, cfg)
    expected_cagr = calculate_cagr(2.96, 12.00, 5)
    assert res.sec_eps_applied is True
    assert round(res.cagr_pct, 2) == round(expected_cagr, 2)
    assert any("SEC EDGAR 官方 10-K 年報數據直接參與估價" in note for note in res.diagnostic_notes)


def test_point_in_time_step_function_no_lookahead():
    """驗證歷史目標價序列嚴格採用階梯函數前向填充，在 3 月 15 日公告日前只能使用前一年度財報"""
    import pandas as pd
    import datetime
    bt_cfg = BacktestConfig()
    nvda = next(s for s in BASELINE_STOCKS if s.ticker == "NVDA")

    # 建立橫跨 2022-03-01 至 2022-03-31 的模擬價格序列
    test_dates = pd.date_range("2022-03-01", "2022-03-31", freq="B")
    test_prices = pd.Series(100.0, index=test_dates)

    hist_df = build_historical_target_series(nvda, test_prices, bt_cfg)
    
    # 2022-03-14（公告日前一天）：只能讀取 2020 年財報 (公告於 2021-03-15)
    eps_before = hist_df.loc["2022-03-14", "gaap_eps"]
    # 2022-03-15（公告日當天）：正式生效 2021 年財報 (2021+1, 03-15)
    eps_after = hist_df.loc["2022-03-15", "gaap_eps"]

    assert eps_before == HISTORICAL_PIT_EPS_DB["NVDA"][2020][0]
    assert eps_after == HISTORICAL_PIT_EPS_DB["NVDA"][2021][0]
    assert eps_after > eps_before  # 階梯躍升，無任何平滑插值洩漏


def test_point_in_time_causal_eps_and_five_year_backtest():
    """驗證近五年歷史回測引擎採用無前視偏差 (Point-in-Time) 階梯滾動與誠實績效評估"""
    assert len(HISTORICAL_PIT_EPS_DB) == 22
    assert HISTORICAL_PIT_EPS_DB["NVDA"][2021][0] < HISTORICAL_PIT_EPS_DB["NVDA"][2025][0]
    # 驗證真實虧損負值保留
    assert HISTORICAL_PIT_EPS_DB["AMZN"][2022][0] < 0
    assert HISTORICAL_PIT_EPS_DB["PLTR"][2020][0] < 0
    assert HISTORICAL_PIT_EPS_DB["PANW"][2020][0] < 0

    bt_cfg = BacktestConfig()
    res = run_full_backtest(bt_cfg)
    portfolios = res["portfolios"]
    summaries = res["stock_summaries"]
    fee_sens = res["fee_sensitivity"]

    assert len(portfolios) == 6
    assert len(summaries) == 22
    assert len(fee_sens) == 3

    smart_p = portfolios[0]
    s3_p = portfolios[1]
    spy_p = next(p for p in portfolios if p.strategy_id == "SPY")
    qqq_p = next(p for p in portfolios if p.strategy_id == "QQQ")

    # 驗證風險調整後報酬：智能組合夏普值優於大盤
    assert smart_p.sharpe_ratio > spy_p.sharpe_ratio
    assert smart_p.sharpe_ratio > qqq_p.sharpe_ratio
    # 驗證最大回撤控制：智能組合回撤顯著優於大盤
    assert abs(smart_p.max_drawdown_pct) < abs(spy_p.max_drawdown_pct)
    assert abs(smart_p.max_drawdown_pct) < abs(qqq_p.max_drawdown_pct)
    # 驗證勝率穩定
    assert smart_p.win_rate_pct >= 80.0
    assert smart_p.total_fees_paid > 0
    # 驗證三階段停利與抱緊不賣之超額報酬
    assert any(s.staged_3tier_return_pct > 100.0 for s in summaries if s.trade_count > 0)
    assert any(s.hold_from_entry_return_pct > 150.0 for s in summaries if s.trade_count > 0)

    # 驗證 META 2022 年案例之持倉回撤與防禦鎖（實證七折買進後仍可能腰斬，防禦鎖砍除 70% 風險暴露）
    meta_trades = [t for t in res["trades"] if t.ticker == "META"]
    assert len(meta_trades) > 0
    meta_t = meta_trades[0]
    assert meta_t.holding_max_drawdown_pct < -50.0  # 自 $190 跌至 $88.09 浮虧達 -53.7% (若採策略二自 $269 進場則深達 -67.2%)
    assert meta_t.circuit_breaker_active is True    # 驗證價值陷阱防禦鎖成功啟動
    assert meta_t.invested_amount == 3000.0         # 驗證倉位強制由滿額 100% ($10,000) 鎖死為 30% 試探單 ($3,000)





