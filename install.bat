@echo off
rem Tao venv va cai thu vien. Chay mot lan tu thu muc wyckoff-radar.
cd /d "%~dp0"
if not exist venv (
  py -3.12 -m venv venv || python -m venv venv
)
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Xong. Tai lich su:  venv\Scripts\python -m scripts.fetch_history
echo Chay test:          venv\Scripts\python -m pytest -q
echo Do 11 nam:          venv\Scripts\python -m scripts.measure --md
