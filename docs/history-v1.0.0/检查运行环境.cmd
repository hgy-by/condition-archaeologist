@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
python -X utf8 "condition-archaeologist\scripts\self_check.py" --out "reports\local-self-check.json"
if errorlevel 1 (
  echo 检查未通过。请把窗口中的提示或报告交给 Codex 处理。
) else (
  echo 检查完成。报告保存在 reports\local-self-check.json。
  echo 数学分析请在 Codex 聊天中调用 $condition-archaeologist。
)
pause
