@echo off
:: 포트폴리오 파이프라인 일일 자동 실행
:: 매일 오전 7시 Windows Task Scheduler로 실행
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "PYTHON=C:\Python314\python.exe"
set "LOG=%SCRIPT_DIR%logs\daily_%date:~0,4%%date:~5,2%%date:~8,2%.log"

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

echo [%date% %time%] 파이프라인 시작 >> "%LOG%"
"%PYTHON%" "%SCRIPT_DIR%run_pipeline.py" >> "%LOG%" 2>&1
echo [%date% %time%] 파이프라인 완료 >> "%LOG%"
