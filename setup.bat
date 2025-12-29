@echo off
chcp 65001 > nul
setlocal

echo ========================================================
echo  FloatRef セットアップウィザード
echo ========================================================
echo.

:: 1. Pythonがインストールされているかチェック
python --version >nul 2>&1
if %errorlevel% neq 0 (
    goto InstallPython
)

:: 2. PyQt6がすでにインストールされているかチェック
python -c "import PyQt6" >nul 2>&1
if %errorlevel% equ 0 (
    goto AlreadyInstalled
)

:: 3. まだ入っていない場合：インストールを実行
echo [OK] Pythonを確認しました。
echo 必要なライブラリ(PyQt6)が見つからないため、インストールします...
echo --------------------------------------------------------
python -m pip install PyQt6
echo --------------------------------------------------------
echo.
echo [成功] 準備が整いました！
echo この画面を閉じて、アプリ(float_ref.pyw)を起動してください。
echo.
pause
exit /b

:: ----------------------------------------------------------

:AlreadyInstalled
echo [OK] 必要な環境(Python と PyQt6)はすでにインストールされています。
echo.
echo 何もする必要はありません。
echo そのままアプリ(float_ref.pyw)を起動してください。
echo.
pause
exit /b

:InstallPython
echo [!] Pythonが見つかりませんでした。
echo.
echo このアプリを動かすには「Python」が必要です。
echo Enterキーを押すと、自動的にインストール画面(Microsoft Store)が開きます。
echo.
pause > nul
start ms-windows-store://pdp/?ProductId=9NJMSPC66VHM
echo.
echo ========================================================
echo  【重要：インストール後の手順】
echo.
echo  1. 開いた画面で「入手」または「インストール」を押してください。
echo  2. インストールが完了したら、この黒い画面を閉じてください。
echo  3. もう一度、この「setup.bat」をダブルクリックしてください。
echo ========================================================
echo.
pause
exit /b