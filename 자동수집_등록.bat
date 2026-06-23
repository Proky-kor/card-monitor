@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo  카드 모니터링 - 자동 수집 등록 (Windows 작업 스케줄러)
echo ========================================
echo.
echo 매일 지정한 시각에 자동으로 모든 카드사를 점검하고,
echo 신규 상품이 생기면 Teams로 알림을 보냅니다.
echo (이 PC가 그 시각에 켜져 있어야 합니다.)
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [오류] 먼저 설치.bat 을 실행하세요.
    pause
    exit /b 1
)

set "RUNTIME=09:00"
set /p "RUNTIME=수집 시각 입력 (HH:MM, 기본 09:00): "
if "%RUNTIME%"=="" set "RUNTIME=09:00"

set "TASK=CardMonitor_Collect"
rem 기존 등록 제거 후 재등록
schtasks /query /tn "%TASK%" >nul 2>&1 && schtasks /delete /tn "%TASK%" /f >nul 2>&1

schtasks /create /f /tn "%TASK%" /tr "\"%~dp0카드수집_실행.bat\" auto" /sc DAILY /st %RUNTIME%
if errorlevel 1 (
    echo.
    echo [오류] 등록 실패. 이 창을 "관리자 권한으로 실행" 후 다시 시도하세요.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  등록 완료! 매일 %RUNTIME% 에 자동 수집됩니다.
echo  - 신규 상품 발생 시 Teams 알림 (.env 에 CARD_TEAMS_WEBHOOK_URL 설정 시)
echo  - 결과는 웹대시보드(서버_실행.bat)에서 확인
echo  - 해제하려면 자동수집_해제.bat 실행
echo ========================================
pause
