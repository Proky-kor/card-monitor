@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [오류] 먼저 설치.bat 을 실행하세요.
    pause
    exit /b 1
)

echo ========================================
echo  카드 상품 모니터링 대시보드 서버
echo  브라우저에서 접속: http://localhost:8001/
echo  (같은 사내망 다른 PC: http://이서버IP:8001/)
echo  이 창을 닫으면 서버가 종료됩니다.
echo ========================================
echo.
.venv\Scripts\python.exe main.py --mode serve
pause
