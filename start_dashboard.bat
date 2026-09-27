@echo off
title Shopee Affiliate Automation - Dashboard
set "PATH=%LOCALAPPDATA%\Programs\Python\Python313;%LOCALAPPDATA%\Programs\Python\Python313\Scripts;C:\nvm4w\nodejs;%PATH%"
echo Dang khoi dong Backend va Web Dashboard...
echo Truy cap tai: http://localhost:8000
python api_server.py
pause
