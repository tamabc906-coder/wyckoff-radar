@echo off
rem Chay job sau phien tren may nay (ghi file, khong push). Tham so: --dry-run | --force | (bo --no-push de push that)
cd /d "%~dp0"
if "%~1"=="" (
  venv\Scripts\python -m job.run_daily --no-push
) else (
  venv\Scripts\python -m job.run_daily %*
)
