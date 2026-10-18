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
    run_tracker,
)
from peg_backtester import BacktestConfig, run_full_backtest


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


def test_five_year_backtest_engine():
    """驗證近五年歷史回測引擎扣除手續費後之完整性與合理性"""
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

    # 驗證智慧三軌與策略三在扣除 0.15% 單邊手續費後，均顯著創造正報酬並擊敗 SPY 大盤
    assert smart_p.final_equity > spy_p.final_equity
    assert s3_p.final_equity > spy_p.final_equity
    assert smart_p.total_fees_paid > 0
