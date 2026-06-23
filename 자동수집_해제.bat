@echo off
chcp 65001 >nul
set "TASK=CardMonitor_Collect"
schtasks /delete /tn "%TASK%" /f
if errorlevel 1 (
    echo [안내] 등록된 자동 수집이 없거나 삭제 실패.
) else (
    echo 자동 수집 등록을 해제했습니다.
)
pause
