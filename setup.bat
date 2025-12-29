@echo off
chcp 65001 >nul
setlocal

echo =======================================================
echo  Float Ref セットアップ
echo =======================================================
echo.

REM --- 1. Pythonの確認 ---
echo [確認中] Pythonの確認...
python --version >nul 2>&1

if %errorlevel% neq 0 (
    echo.
    echo [!] Pythonが見つかりませんでした。
    echo.
    echo ブラウザでPythonのダウンロードページを開きます。
    echo インストーラーをダウンロードして実行してください。
    echo.
    echo ※重要：インストール画面で「Add Python to PATH」に
    echo   チェックを入れてからインストールしてください。
    echo.
    timeout /t 3 >nul
    start https://www.python.org/downloads/
    echo インストール完了後、この画面を閉じて再実行してください。
    pause
    exit /b
)

echo [OK] Pythonはインストール済みです。
echo.

REM --- 2. PyQt6ライブラリの確認 ---
echo [確認中] ライブラリ(PyQt6)の確認...

REM ★修正: pipではなく、直接importできるかで判定（警告による誤作動を防止）
python -c "import PyQt6" >nul 2>&1

if %errorlevel% equ 0 (
    goto :ALREADY_INSTALLED
)

REM --- 3. インストール処理 ---
:INSTALL_START
echo [!] PyQt6のインストールを開始します...
echo     (インターネット接続が必要です)

python -m pip install PyQt6

if %errorlevel% neq 0 (
    echo.
    echo [エラー] インストールに失敗しました。
    echo ネットワーク接続を確認してください。
    pause
    exit /b
)
echo [OK] インストールが完了しました。
goto :FINISH

REM --- 4. すでにインストール済みの場合 ---
:ALREADY_INSTALLED
echo [OK] 必要なライブラリはすでにインストールされています。

REM --- 5. 完了案内 ---
:FINISH
echo.
echo =======================================================
echo  準備完了
echo =======================================================
echo.
echo 必要な環境はすべて整いました。
echo.
echo フォルダ内の float_ref.pyw をダブルクリックして
echo アプリを起動してください。
echo.
pause