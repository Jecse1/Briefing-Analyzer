@echo off
chcp 65001 >nul
echo ============================================================
echo   오버워치 스크림 브리핑 추출기 - 설치
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo        https://www.python.org 에서 설치 후 다시 실행해주세요.
    pause & exit /b 1
)

echo [1/5] pip 업그레이드 중...
python -m pip install --upgrade pip --quiet

echo [2/5] PyTorch (CUDA) 설치 중...
pip install torch --index-url https://download.pytorch.org/whl/cu121 --quiet
if errorlevel 1 (
    echo       CUDA 버전 실패 - CPU 버전으로 재시도...
    pip install torch --quiet
)

echo [3/5] Whisper 설치 중...
pip install openai-whisper --quiet

echo [4/5] yt-dlp 설치 중...
pip install yt-dlp --quiet

echo [5/5] Anthropic SDK 설치 중...
pip install anthropic --quiet

echo.
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [주의] ffmpeg가 없습니다. 아래 명령어로 설치해주세요:
    echo        winget install ffmpeg
    echo        설치 후 터미널을 재시작하세요.
    echo.
) else (
    echo [OK] ffmpeg 감지됨
)

if not exist .env (
    echo.
    echo [설정] Anthropic API 키를 입력해주세요.
    echo        발급: https://console.anthropic.com
    echo.
    set /p APIKEY="API 키 (sk-ant-...): "
    echo ANTHROPIC_API_KEY=%APIKEY%> .env
    echo [OK] .env 저장 완료
) else (
    echo [OK] .env 파일 존재
)

echo.
echo ============================================================
echo   설치 완료!  run.bat 으로 실행하세요.
echo ============================================================
pause
