@echo off
title Shopee Affiliate Automation - Khoi chay BE va FE
chcp 65001 >nul

echo ========================================================
echo   KHOI CHAY HE THONG SHOPEE AFFILIATE (BACKEND + FRONTEND)
echo ========================================================
echo.

echo [1/2] Dang khoi dong Backend API (FastAPI - Port 8000)...
start "Backend - FastAPI Server (Port 8000)" cmd /k "python api_server.py"

echo [2/2] Dang khoi dong Frontend UI (Angular - Port 4200)...
start "Frontend - Angular Dev Server (Port 4200)" cmd /k "cd frontend && npm start"

echo.
echo ========================================================
echo   Backend API:   http://localhost:8000
echo   Frontend UI:   http://localhost:4200
echo.
echo   Dang cho 5 giay de mo trinh duyet...
echo ========================================================

timeout /t 5 >nul
start http://localhost:4200
