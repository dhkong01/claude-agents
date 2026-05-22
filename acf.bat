@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0tools\acf_predictor"
pip install -r requirements.txt -q 2>nul
python main.py %*
