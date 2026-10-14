@echo off
REM ============================================================
REM  YTGrab - one-time build. Double-click this file.
REM  It installs what's needed and makes YTGrab.exe you can pin.
REM ============================================================
echo.
echo  Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
echo.
echo  Building YTGrab.exe ...
pyinstaller --onefile --noconsole --name YTGrab --icon ytgrab.ico --add-data "ytgrab.ico;." ytgrab.py
echo.
echo  ============================================================
echo   Done. Your app is here:   dist\YTGrab.exe
echo   Right-click it -^> Pin to taskbar.
echo  ============================================================
echo.
pause
