# 오버워치 스크림 브리핑 추출기

오버워치 스크림 영상에서 코치/선수 브리핑을 자동 추출하고,
검토할수록 정확해지는 학습형 분석 도구입니다.

## 파이프라인

```
YouTube URL
  -> yt-dlp              오디오 추출
  -> faster-whisper      음성 인식 (large-v3 / CUDA 가속)
     [STT 캐시 저장 - 재실행 시 STT 생략]
  -> 환각 필터           연속 중복 세그먼트 제거
  -> Claude Sonnet       전체 세그먼트 태그 분류
  -> output/PLAYER/      TXT + JSON + 검토용 CSV 저장

엑셀에서 틀린 태그만 수정
  -> review.py apply     수정 내용을 examples.json 에 누적
  -> 다음 분석부터 자동 반영 (회차마다 정확도 향상)
```

## 시작하기

### 1. 설치

```
install.bat 더블클릭
```

ffmpeg가 없으면:
```
winget install ffmpeg
```

### 2. API 키 설정

`.env.example` 을 `.env` 로 복사 후 Anthropic API 키 입력:
```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### 3. 실행

```bash
# 대화형 선수 선택
python extractor.py "https://www.youtube.com/watch?v=..."

# 선수 직접 지정
python extractor.py "URL" --player TEAM
python extractor.py "URL" --player HANBIN

# 모델 지정 (기본: large-v3)
python extractor.py "URL" --player TEAM --model large-v3
```

## 태그 종류

| 태그 | 설명 | 예시 |
|------|------|------|
| `focus` | 포커싱/체력 | "겐지 겐지 잡아!", "Ana 피 1" |
| `ult_check` | 궁체크 | "상대 루시우 궁 있을 거야" |
| `ult_strat` | 궁극기 전략 | "자리야 궁 박고 라인하르트 연계" |
| `position` | 포지션 | "Ana 2층 고지 유지" |
| `tempo` | 방향성 | "지금은 버텨, 저쪽이 들어오게 해" |
| `미분류` | 감탄사, 잡담, 리액션 | (브리핑 아닌 발화 전부) |

## 학습 사이클

```
1회차  AI가 씨앗 예시(10개) 기반으로 태그 분류
       -> output/PLAYER/*_review.csv 저장
       -> 엑셀에서 틀린 태그만 "수정 태그" 칸에 입력

       python review.py apply "output/PLAYER/파일명_review.csv"
       -> examples.json 에 누적

2회차~ 팀 실제 데이터가 프롬프트에 자동 삽입
       -> 팀 말투, 줄임말, 영웅 별명까지 반영
       -> 반복할수록 정확도 향상
```

## 주요 명령어

```bash
# 학습 데이터 현황
python review.py stats
python review.py stats --player HANBIN

# 학습 데이터 초기화
python review.py reset

# 모델 비교 (첫 5분, small vs medium)
python extractor.py --compare-models "URL"
```

## 출력 파일

```
output/
  TEAM/
    영상제목_날짜.txt          최종 브리핑 기록
    영상제목_날짜.json         구조화 데이터
    영상제목_날짜_review.csv   엑셀 검토용
  HANBIN/
    ...
```

## Whisper 모델

| 모델 | VRAM | RTX 3080 기준 (2시간) | 비고 |
|------|------|----------------------|------|
| `medium` | ~5GB | ~3분 | 한국어 인식률 낮음 |
| `large-v3` | ~10GB | **~7분** | **기본값, 권장** |

GPU 없을 시 `int8` 자동 전환 (large-v3 기준 ~50분 소요).

## 파일 구조

```
.
|- extractor.py        메인 분석 스크립트
|- learning.py         학습 데이터 관리 & 프롬프트 빌더
|- review.py           검토 결과 반영 스크립트
|- examples.json       누적 학습 데이터 (자동 생성)
|- .env                API 키 (직접 작성)
|- .env.example        API 키 템플릿
|- install.bat         최초 1회 패키지 설치
|- run.bat             메뉴형 실행
|- cache/              STT 캐시 (URL + 모델별 분리)
|- output/             결과 저장 폴더
```

## 의존성

```bash
pip install faster-whisper yt-dlp anthropic rich psutil python-dotenv
pip install torch --index-url https://download.pytorch.org/whl/cu124
```