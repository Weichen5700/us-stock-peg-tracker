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
from peg_backtester import BacktestConfig, HISTORICAL_PIT_EPS_DB, run_full_backtest


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


def test_point_in_time_causal_eps_and_five_year_backtest():
    """驗證近五年歷史回測引擎採用無前視偏差 (Point-in-Time) 滾動 EPS/CAGR 與三段式分批停利驗證"""
    assert len(HISTORICAL_PIT_EPS_DB) == 22
    assert HISTORICAL_PIT_EPS_DB["NVDA"][2021][0] < HISTORICAL_PIT_EPS_DB["NVDA"][2025][0]

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

    assert smart_p.final_equity > spy_p.final_equity
    assert s3_p.final_equity > spy_p.final_equity
    assert smart_p.total_fees_paid > 0
    assert any(s.staged_3tier_return_pct > 0 for s in summaries if s.trade_count > 0)


