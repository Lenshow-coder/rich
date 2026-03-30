@echo off
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
python gui.py 2>NUL || py gui.py
pause
