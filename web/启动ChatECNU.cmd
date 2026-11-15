@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 请先安装Python 3.11或更新版本，并勾选加入PATH。
  pause
  exit /b 1
)
python -X utf8 launch_chatecnu.py --port 8765
pause
