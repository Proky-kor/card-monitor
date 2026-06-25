@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [오류] 먼저 설치.bat 을 실행하세요.
    pause
    exit /b 1
)

echo ========================================
echo  카드사 상품 수집 시작...
echo ========================================
.venv\Scripts\python.exe main.py --mode collect

echo.
echo  정적 대시보드 갱신(dist/index.html)...
.venv\Scripts\python.exe main.py --mode export

echo.
echo  [git] push cards.db to GitHub (CI deploy)...
git add -f storage/cards.db
git commit -m "chore: update card state (local collect)" || echo   (no changes to commit)
git pull --no-rebase --no-edit -X ours origin main || echo   (pull skipped)
git push origin main || echo   (push failed - check network/credential)

rem 작업 스케줄러로 자동 실행할 때는 인자 auto 를 주면 창이 멈추지 않습니다.
rem   예) 카드수집_실행.bat auto
if /i not "%~1"=="auto" pause
