#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3。请安装 Python 3.11 或更高版本后重试。"
  read -r -p "按回车键关闭窗口……"
  exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "需要 Python 3.11 或更高版本。当前版本：$(python3 --version 2>&1)"
  read -r -p "按回车键关闭窗口……"
  exit 1
fi

echo "条件考古学网页：http://127.0.0.1:8765/"
echo "保持此终端窗口打开；按 Control+C 停止服务。"
exec python3 -X utf8 "$PROJECT_ROOT/web/server.py" --port 8765
