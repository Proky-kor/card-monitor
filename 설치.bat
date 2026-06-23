@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo  카드사 상품 모니터링 - 설치
echo ========================================
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo [오류] uv 가 설치되어 있지 않습니다. 담당자에게 문의하세요.
    pause
    exit /b 1
)

echo [1/2] 가상환경 생성...
uv venv --python 3.12
if errorlevel 1 (
    echo [오류] 가상환경 생성 실패.
    pause
    exit /b 1
)

echo [2/2] 라이브러리 설치... (인터넷 필요, 회사망 --native-tls)
uv pip install --native-tls -r requirements.txt
if errorlevel 1 (
    echo [오류] 라이브러리 설치 실패 - 인터넷/프록시 확인.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  설치 완료!
echo  1) 카드수집_실행.bat 으로 데이터 수집
echo  2) 서버_실행.bat 으로 대시보드 시작
echo ========================================
pause
