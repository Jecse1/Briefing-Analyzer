# 오버워치 스크림 브리핑 추출기

오버워치 스크림 영상에서 브리핑을 자동 추출하고, 검토할수록 정확해지는 학습형 도구.
**기준 영상 길이: 2시간 (모든 예상 소요 시간, 청크 분할, 진행률 계산 2시간 기준)**

---

## 프로젝트 구조

```
브리핑 분석기/
├── CLAUDE.md          ← 지금 이 파일
├── extractor.py       메인 분석 스크립트 (YouTube → faster-whisper → Claude → 결과 저장)
├── learning.py        학습 데이터 관리 & 프롬프트 빌더
├── review.py          검토 결과를 examples.json 에 반영
├── examples.json      누적 학습 데이터 (player 필드 포함, 없으면 자동 생성)
├── .env               ANTHROPIC_API_KEY 저장
├── install.bat        최초 1회 패키지 설치
├── run.bat            메뉴형 실행 스크립트
├── cache/             STT 캐시 (URL 해시 기반, 재실행 시 STT 생략)
└── output/
    ├── TEAM/          팀 전체 영상 결과
    │   ├── *.txt
    │   ├── *.json
    │   └── *_review.csv
    └── HANBIN/        선수별 결과 폴더
        ├── *.txt
        ├── *.json
        └── *_review.csv
```

---

## 등록 선수 목록

`extractor.py` 상단 `REGISTERED_PLAYERS` 리스트에서 관리:

```python
REGISTERED_PLAYERS = [
    "HANBIN",
    # 선수 추가: "이름",
]
```

새 선수 추가 시 `output/이름/` 폴더가 자동 생성됨.

---

## 핵심 명령어

### 영상 분석 (대화형 선수 선택)
```bash
python extractor.py "https://www.youtube.com/watch?v=..."
```
실행 시 자동으로 묻습니다:
```
이 영상은 팀 전체 영상인가요, 특정 선수 영상인가요?
[1] TEAM  [2] 선수 직접 입력
등록 선수: HANBIN
```

### 영상 분석 (선수 직접 지정)
```bash
python extractor.py "URL" --player HANBIN
python extractor.py "URL" --player TEAM
python extractor.py "URL" --player HANBIN --model large-v3
```

- `--model`: `tiny` / `base` / `medium` / `large-v2` / `large-v3`(기본)
- `--player`: `TEAM` 또는 선수 이름 (없으면 대화형 선택)

### 모델 비교 (첫 5분, small vs medium)
```bash
python extractor.py --compare-models "URL"
```

### 검토 결과 학습 반영
```bash
python review.py apply "output/HANBIN/파일명_review.csv"
python review.py apply "output/TEAM/파일명_review.csv"
# 폴더 이름에서 선수명 자동 감지
```

### 학습 데이터 현황
```bash
python review.py stats              # 전체 통계 + 선수별 분포
python review.py stats --player HANBIN  # HANBIN 통계만
python review.py stats --player TEAM
```

### 학습 데이터 초기화
```bash
python review.py reset
```

---

## 2시간 영상 기준 예상 소요 시간 (RTX 3080 GPU)

| 단계 | 모델 | 예상 시간 |
|------|------|-----------|
| 오디오 다운로드 | — | ~1~2분 |
| faster-whisper STT | tiny | ~1~2분 |
| faster-whisper STT | medium | ~5~7분 |
| faster-whisper STT | large-v3 (기본) | **~7~9분** |
| Claude 분석 | — | ~2분 |
| **총계** | large-v3 | **~10~12분** |

GPU 미사용(CPU) 시 compute_type=int8 자동 전환, large-v3: ~40~60분 소요.

---

## 진행률 표시 구성

실행 중 터미널에 표시되는 항목:

```
─────────── 단계 2/5: Whisper(large-v3) 음성 인식 ───────────
  전체 진행: [████░░░░░░░░░░░░░░░░] 20%  경과 01:23 / 남은 예상 05:40
  CPU 45%  RAM 26.7/66.2GB  │  GPU[0] RTX 3080 VRAM 4.7/10.7GB

  STT  [████████░░░░░░░░░░░░░░░░░░░░░░░░░░] 21%  경과 00:56 / 예상 02:45  CUDA

  [완료] STT — 01:52 소요  |  312개 세그먼트  실제RTF 0.06x  CUDA
```

| 항목 | 내용 |
|------|------|
| 단계 헤더 | `단계 N/5: 단계명` |
| 전체 진행바 | 20칸 블록 + % + 경과/예상 남은 시간 |
| 시스템 자원 | CPU%, RAM, GPU VRAM 실시간 |
| Whisper 진행 | 추정 % + 경과/예상 STT 소요 + CUDA/CPU |
| 완료 메시지 | `[완료] 단계명 — 소요시간 / 세부 정보` |
| 최종 요약 | 총 소요 / 단계별 소요 / 브리핑 수 / 대상 |

---

## 브리핑 태그 5종

| 태그 | 설명 | 감지 패턴 |
|------|------|-----------|
| `focus` | 포커싱/체력 | 영웅 이름 반복, "OO 잡아", "피 1" |
| `ult_check` | 궁체크 | 소강상태에서 상대 궁 예측·공유 |
| `ult_strat` | 궁극기 전략 | 아군 궁 사용 순서·타이밍 지시 |
| `position` | 포지션 | 자리 지시 |
| `tempo` | 방향성 | 선템포 진입 vs 수비 대기 결정 |

브리핑이 아닌 발화(감탄사, 잡담, 리액션 등)는 `미분류` 태그로 저장됨.

---

## 학습 구조

```
영상 분석
  → STT 캐시 확인 (cache/ 폴더, URL 해시 기반)
  → faster-whisper large-v3, float16(CUDA) / int8(CPU) 로 전체 세그먼트 추출
  → learning.py 가 examples.json 에서 태그별 best 예시 선별
  → Claude 프롬프트에 few-shot 삽입
  → Claude가 전체 세그먼트에 태그 분류 (브리핑 5종 + 미분류)
  → output/PLAYER/ 에 txt + json + _review.csv 저장

엑셀에서 틀린 태그만 수정
  → review.py apply 실행
  → examples.json 누적 (player 필드 포함)

다음 분석부터 자동 반영 (회차마다 정확도 향상)
```

---

## 환경 변수

`.env` 파일:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 의존성

| 패키지 | 역할 |
|--------|------|
| `faster-whisper` | STT (float16 CUDA / int8 CPU 자동 전환, RTX 3080 권장) |
| `yt-dlp` | YouTube 오디오 추출 |
| `anthropic` | Claude API (claude-sonnet-4-6) |
| `torch` (CUDA 버전) | faster-whisper GPU 가속 |
| `ffmpeg` | 오디오 변환 (시스템 PATH 필요) |
| `rich` | 진행률 표시 UI |
| `psutil` | CPU/RAM 모니터링 |
| `python-dotenv` | .env 로드 |

CUDA PyTorch 설치 (RTX 30 시리즈):
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install faster-whisper
```

---

## 자주 하는 작업

> "HANBIN 영상 분석해줘"
→ `python extractor.py "URL" --player HANBIN`

> "팀 영상 large-v3 모델로 분석해줘"
→ `python extractor.py "URL" --player TEAM --model large-v3`

> "HANBIN output 폴더에서 최근 CSV 학습 반영"
→ output/HANBIN/ 에서 최신 *_review.csv 찾아서 `python review.py apply` 실행

> "HANBIN 학습 데이터 몇 개야?"
→ `python review.py stats --player HANBIN`

> "전체 학습 데이터 현황"
→ `python review.py stats`

## 개발 로드맵

### 1단계 - 현재 (완료)
- YouTube URL → 오디오 추출 (yt-dlp)
- 음성 인식 (faster-whisper large-v3, CUDA 가속)
- STT 캐시 기능 (모델별 분리 저장)
- 브리핑 추출 + 태그 분류 (Claude Sonnet)
- 전체 세그먼트 저장 후 태그 분류 (미분류 포함)
- 선수별 output 폴더 분리 (--player 옵션)
- TEAM / 선수 선택 프로세스
- 검토 CSV + 코멘트 학습 누적 (examples.json)
- 진행률 UI / 시스템 리소스 표시
- Cowork output 폴더 관리 + 브리핑 분석 의견

### 2단계 - 중기 목표
인게임 사운드가 섞인 영상도 처리 가능하게
- noisereduce로 배경음 감쇄
- 음성 주파수 대역 필터링 (100~8000Hz)
- extractor.py transcribe() 앞단에 전처리 추가
- 예상 정확도 향상: 현재 대비 +15~20%

### 3단계 - 장기 목표
완전 자동화 파이프라인
- Demucs (Meta AI)로 인게임 사운드 완전 분리
- pyannote.audio로 선수별 음성 자동 구분
- 전체 스크림 영상 하나로 5명 동시 분석
- 선수 목소리 샘플 등록 후 자동 매핑
- 예상 정확도 60~70% (한타 중 동시 발화 구간 제외)

### 알려진 문제 및 현재 상태
- 타임스탬프 오차 2~3초: vad_filter 기반 허용 범위로 간주
  (세그먼트 병합 제거로 10초 오차는 해결 완료)
- 인게임 사운드 섞인 영상: 2단계에서 해결 예정

### 샘플 데이터
- temp_audio.mp3: 인게임 사운드 + 브리핑 혼합 샘플
  → 2단계/3단계 개발 시 테스트 파일로 활용

### 현재 선수 목록
- TEAM: 팀 전체 영상
- HANBIN: 개인 녹음 영상