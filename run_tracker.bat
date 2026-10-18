@echo off
chcp 65001 >nul
echo ============================================================================
echo 🚀 美股三大指數與 AI 企業巨頭「本益成長比 (PEG) 7 折三軌監控與五年回測系統」
echo ============================================================================
set PYTHON_EXE=C:\Users\weichen\AppData\Local\Python\bin\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)
"%PYTHON_EXE%" "%~dp0us_ai_peg_tracker.py" %*
"%PYTHON_EXE%" "%~dp0peg_backtester.py"
start "" "%~dp0peg_valuation_dashboard.html"
start "" "%~dp0peg_backtest_dashboard.html"
pause
