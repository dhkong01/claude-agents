@echo off
:: Windows Task Scheduler 등록 — 매일 07:00 포트폴리오 파이프라인 자동 실행
:: 관리자 권한으로 실행하세요
chcp 65001 >nul

set "TASK_NAME=StockPortfolio_Daily"
set "BAT_FILE=%~dp0run_daily.bat"

echo 기존 작업 제거 중...
schtasks /delete /tn "%TASK_NAME%" /f 2>nul

echo 새 작업 등록 중...
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "cmd /c \"%BAT_FILE%\"" ^
  /sc daily ^
  /st 07:00 ^
  /ru "%USERNAME%" ^
  /rl highest ^
  /f

if %errorlevel% == 0 (
    echo.
    echo [성공] 매일 오전 7시 자동 실행 등록 완료
    echo 작업 이름: %TASK_NAME%
    echo 실행 파일: %BAT_FILE%
    echo.
    echo 확인: 작업 스케줄러 열기 ^(taskschd.msc^)
) else (
    echo [오류] 관리자 권한으로 다시 실행하세요
)
pause
