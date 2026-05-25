@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: .env 로드
if exist .env (
    for /f "tokens=1,2 delims==" %%A in (.env) do set %%A=%%B
)

:MENU
cls
echo ============================================================
echo   오버워치 스크림 브리핑 추출기
echo ============================================================
echo.
echo   [1] 영상 분석 시작
echo   [2] 검토 결과 학습 반영
echo   [3] 학습 데이터 현황 (전체)
echo   [4] 학습 데이터 현황 (선수별)
echo   [5] 종료
echo.
set /p CHOICE="선택 (1-5): "

if "%CHOICE%"=="1" goto ANALYZE
if "%CHOICE%"=="2" goto REVIEW
if "%CHOICE%"=="3" goto STATS_ALL
if "%CHOICE%"=="4" goto STATS_PLAYER
if "%CHOICE%"=="5" exit /b 0
goto MENU


:ANALYZE
cls
echo ============================================================
echo   영상 분석 시작
echo ============================================================
echo.
set /p URL="YouTube URL 입력: "
if "%URL%"=="" (echo URL을 입력해주세요. & pause & goto MENU)

echo.
echo ------------------------------------------------------------
echo   대상 선택
echo ------------------------------------------------------------
echo.
echo   등록 선수: HANBIN
echo.
echo   [1] TEAM  (팀 전체 영상)
echo   [2] HANBIN
echo   [3] 직접 입력
echo.
set /p PLAYER_CHOICE="선택 (기본 1): "

if "%PLAYER_CHOICE%"=="1" set PLAYER=TEAM
if "%PLAYER_CHOICE%"=="2" set PLAYER=HANBIN
if "%PLAYER_CHOICE%"=="3" (
    set /p PLAYER="선수 이름 입력: "
    if "!PLAYER!"=="" set PLAYER=TEAM
)
if not defined PLAYER set PLAYER=TEAM

echo.
echo ------------------------------------------------------------
echo   Whisper 모델 선택
echo   ※ 2시간 영상 기준 예상 소요 시간 (RTX 3080 GPU 기준)
echo ------------------------------------------------------------
echo.
echo   [1] tiny    약 2~3분   (정확도 낮음)
echo   [2] base    약 4~5분
echo   [3] medium  약 9~11분  (권장)
echo   [4] large   약 20~25분 (최고 정확도)
echo.
set /p MC="선택 (기본값 3): "
set MODEL=medium
if "%MC%"=="1" set MODEL=tiny
if "%MC%"=="2" set MODEL=base
if "%MC%"=="4" set MODEL=large

echo.
echo  대상: %PLAYER%  모델: %MODEL%
echo  분석을 시작합니다...
echo.

python extractor.py "%URL%" --model %MODEL% --player %PLAYER%

echo.
echo ============================================================
if errorlevel 1 (
    echo   [오류] 분석 중 문제가 발생했습니다.
) else (
    echo   분석 완료!
    echo   output\%PLAYER%\ 폴더에 결과가 저장되었습니다.
    echo   엑셀로 _review.csv 열어서 틀린 태그만 수정한 뒤
    echo   [2]번으로 학습 반영하세요.
)
echo ============================================================
pause
set PLAYER=
set MODEL=
goto MENU


:REVIEW
cls
echo ============================================================
echo   검토 결과 학습 반영
echo ============================================================
echo.
echo   output\TEAM\    — 팀 전체 영상 검토 파일
echo   output\HANBIN\  — HANBIN 검토 파일
echo.
echo   예시: output\HANBIN\영상제목_20250526_review.csv
echo.
set /p CSV="CSV 파일 경로: "
if "%CSV%"=="" (echo 경로를 입력해주세요. & pause & goto MENU)

python review.py apply "%CSV%"
pause
goto MENU


:STATS_ALL
cls
echo ============================================================
echo   학습 데이터 현황 (전체)
echo ============================================================
python review.py stats
pause
goto MENU


:STATS_PLAYER
cls
echo ============================================================
echo   학습 데이터 현황 (선수별)
echo ============================================================
echo.
echo   등록 선수: HANBIN  /  TEAM
echo.
set /p PLAYER_STAT="조회할 선수명 (예: HANBIN): "
if "%PLAYER_STAT%"=="" (
    python review.py stats
) else (
    python review.py stats --player %PLAYER_STAT%
)
set PLAYER_STAT=
pause
goto MENU
