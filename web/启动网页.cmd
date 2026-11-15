@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 请先安装 Python 3.11 或更新版本，并勾选加入 PATH。
  pause
  exit /b 1
)
echo 条件考古学网页将在 http://127.0.0.1:8765 启动。
echo 请保持此窗口打开，再用浏览器访问上面的地址。
echo 关闭窗口将停止网页服务。
python -X utf8 server.py --port 8765
pause
