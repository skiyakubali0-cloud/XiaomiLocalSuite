#!/bin/sh
# Only starts the local Tk interface; does not install packages or contact phones.
cd "$(dirname "$0")" || exit 1
export TK_SILENCE_DEPRECATION=1
for gui_python in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.11 /usr/local/bin/python3 python3 /usr/bin/python3; do
  if "$gui_python" -c 'import sys, tkinter; assert sys.version_info >= (3, 9); assert sys.platform != "darwin" or tkinter.TkVersion >= 8.6' >/dev/null 2>&1; then
    exec "$gui_python" gui.py
  fi
done
printf '%s\n' '未找到带Tk8.6+的Python 3.9+。Mac可安装Homebrew的python-tk@3.13，再双击此文件。' '按回车退出。'
read gui_answer
exit 1
