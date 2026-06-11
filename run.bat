@echo off
echo ========================================
echo   澡堂手牌管理系统 - 启动脚本
echo ========================================
echo.

echo [1/3] 检查 Python 环境...
python --version
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo.
echo [2/3] 安装依赖包...
pip install -r requirements.txt
if errorlevel 1 (
    echo 警告: 依赖安装可能存在问题，继续尝试启动...
)

echo.
echo [3/3] 启动应用服务器...
echo 服务器地址: http://localhost:8080
echo 默认账号: admin / admin123
echo 按 Ctrl+C 停止服务器
echo.

python app.py

pause
