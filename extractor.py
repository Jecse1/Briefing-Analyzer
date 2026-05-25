"""
extractor.py — 오버워치 스크림 브리핑 추출기
--------------------------------------------
YouTube URL → 오디오 추출 → Whisper STT → Claude 분석 → 결과 저장
기본 대상 영상 길이: 2시간 기준 최적화
"""

import os, sys, json, time, re, threading, subprocess, argparse, hashlib
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Windows 터미널 UTF-8 강제
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# ── 선택적 표시 의존성 ─────────────────────────────────────────
try:
    import psutil
    psutil.cpu_percent(interval=None)
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    from rich.console import Console
    from rich.progress import (
        Progress, BarColumn, TextColumn, TimeElapsedColumn,
        SpinnerColumn, TaskProgressColumn, MofNCompleteColumn,
    )
    from rich.live import Live
    from rich.table import Table
    HAS_RICH = True
    console = Console(force_terminal=True, highlight=False)
except ImportError:
    HAS_RICH = False
    console = None

# ── 의존성 체크 ───────────────────────────────────────────────
def check_dependencies():
    missing = []
    for pkg, name in [("yt_dlp", "yt-dlp"), ("faster_whisper", "faster-whisper"),
                      ("anthropic", "anthropic"), ("torch", "torch")]:
        try: __import__(pkg)
        except ImportError: missing.append(name)
    if missing:
        _print(f"[red]오류[/red] 패키지 미설치: {', '.join(missing)}")
        _print("      install.bat 을 먼저 실행해주세요.")
        sys.exit(1)

check_dependencies()

import yt_dlp
from faster_whisper import WhisperModel
import torch
import anthropic
from learning import TAG_NAMES, build_system_prompt, get_stats

# whisper 내부 tqdm 비활성화 (우리 Live display와 충돌 방지)
try:
    import tqdm as _t
    _orig_tqdm = _t.tqdm
    class _SilentTqdm(_orig_tqdm):
        def __init__(self, *a, **kw):
            kw['disable'] = True
            super().__init__(*a, **kw)
    _t.tqdm = _SilentTqdm
except Exception:
    pass

# ── 선수 목록 & 폴더 구조 ──────────────────────────────────────
REGISTERED_PLAYERS = [
    "HANBIN",
    # 선수 추가: "이름",
]

OUTPUT_BASE = Path("output")
for _d in ["TEAM"] + REGISTERED_PLAYERS:
    (OUTPUT_BASE / _d).mkdir(parents=True, exist_ok=True)

AUDIO_PATH = Path("temp_audio.mp3")
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
INITIAL_PROMPT = """
오버워치 탱커: 디바, D.VA, 매트릭스, 부스터, 미사일, 자폭, 메카호출, 도미나, Domina, 방벽배열, 판옵티콘, 둠피스트, Doomfist, Doom, 펀치, 슬램, 파워블락, 미티어, 해저드, Hazard, 스파이크가드, 덤벼들기, 가시벽, 다운포어, 정커퀸, Junker Queen, JQ, Queen, 나이프, 샤웃, 카네지, 램페지, 마우가, Mauga, 돌파, 케이지, 오리사, Orisa, 재블린, 포티파이, 스핀, 서지, 라마트라, Rammatra, 공허방벽, 네메시스, 볼텍스, 절멸, 라인하르트, Reinhardt, Rein, 망치, 방벽, 돌진, 화염강타, 대지분쇄, 쉐터, 로드호그, Roadhog, Hog, 갈고리, 숨돌리기, 돼재앙, 시그마, Sigma, Sig, 그래스프, 플럭스, 자탄, 윈스턴, Winston, Monkey, 점프팩, 버블, 프라이멀, 레킹볼, Ball, Hamster, 파일드라이버, 마인필드, 자리야, Zarya, 개인버블, 그랩

오버워치 딜러: 안란, Anran, 맹염질주, 춤추는불꽃, 불사조승천, 애쉬, Ashe, 다이너마이트, 코치건, 바스티온, Bastion, 수색모드, 강습모드, 네이드, 캐논, 캐서디, Cassidy, Cass, 연사, 자력수류탄, 석양, 하이눈, 에코, Echo, 점착폭탄, 복제, 엠레, Emre, 사이버파편, 프레야, Freja, 퀵대시, 상승기류, 올가미사격, 겐지, Genji, 질풍참, 대시, 디플랙트, 용검, 블레이드, 한조, Hanzo, 음파화살, 소나, 폭풍화살, 스톰, 용의일격, 드래곤, 정크랫, Junk, Junkrat, 충격지뢰, 컨커션, 강철덫, 트랩, 타이어, 메이, Mei, 아이스블락, 빙벽, 눈보라, 파라, Pharah, 젯팩, 충격탄, 바라지, 리퍼, Reaper, 망령화, 그림자밟기, 블로썸, 소전, Sojourn, 파워슬라이드, 분열사격, 오버클럭, 솔저76, Soldier, 헬릭스, 질주, 스프린트, 생체장, 바이저, 솜브라, Sombra, 해킹, 인비즈, EMP, 시메트라, Sym, Symmetra, 감시포탑, 순간이동기, 광자방벽, 토르비욘, Torb, Torbjorn, 포탑, 과부하, 초고열용광로, 트레이서, Tracer, 블링크, 리콜, 펄스폭탄, 펄스, 벤처, Venture, 잠복, 드릴돌진, 지각충격, 위도우메이커, Widow, Widowmaker, 맹독지뢰, 적외선투시, 벤데타, Vendetta, 소용돌이질주, 갈라내는칼날

오버워치 서포터: 라이프위버, Lifeweaver, Weaver, 연꽃단상, 플랫폼, 구원의손길, 생명의나무, 트리, 루시우, Lucio, 밀쳐내기, 분위기전환, 엠프, 비트, 소리방벽, 메르시, Mercy, 공격력강화, 수호천사, GA, 부활, 레즈, 발키리, 모이라, Moira, 소멸, 페이드, 생체구슬, 오브, 융화, 바티스트, Baptiste, Bap, 이모탈, 증폭매트릭스, 윈도우, 브리기테, Brigitte, Brig, 방패밀치기, 채찍질, 플레일, 랠리, 아나, Ana, 수면총, 슬립, 생체수류탄, 힐밴, 나노, 뽕, 키리코, Kiriko, 정화의방울, 방울, 여우길, 길, 젠야타, Zenyatta, Zen, 화합, 불화, 마크, 초월, 일리아리, Illari, 궤도광선, 궤도, 주노, Juno, 하이퍼링, 링, 미즈키, Mizuki, 치유삿갓, 결계성역

궁극기 별칭: 비트, 나노, 뽕, 자탄, 석양, 펄스, 길, 키츠네, 윈도우, 랠리, 타이어, 망치, 자폭, 리필, 오버클럭, 궤도, 아쎄이투하, 블로썸, 드래곤, 바라지, 케이지

게임 용어: 궁체크, 궁극기, 한타, 포커싱, 포지션, 딜각, 양각, 템포, 턴, 리그룹, 플랭킹, 포킹, 피킹, 변수, 밸류, 베이팅, 러쉬, 사이드, 본대, 앵커, 홀딩, 리테이크, 투멘딜, 라인전, 궁분배, 이니시, 전진수비, 훼이크, 이속, 어그로, 딜교환

체력 용어: 피1, 개피, 딸피, 반피, 힐밴, 힐, 케어, 태그드, 바디샷, 헤드샷

위치 용어: 고지대, 하이그라운드, 2층, 3층, 오른쪽, 왼쪽, 정면, 골목, 아치, 입구, 캣워크, 발코니, 터널, 거점, 화물, 리스폰

선수 이름: 치요, 한빈
"""

MERGE_GAP_SEC = 1.5
MERGE_MAX_SEC = 10.0

# 모델/장치별 RTF (처리시간 / 오디오길이) — 2시간 영상 기준 측정값
# RTX 3080 기준: medium 실측 ~0.06x
RTF_ESTIMATE = {
    ("tiny",     "cuda"): 0.01, ("tiny",     "cpu"): 0.10,
    ("base",     "cuda"): 0.02, ("base",     "cpu"): 0.25,
    ("small",    "cuda"): 0.03, ("small",    "cpu"): 0.50,
    ("medium",   "cuda"): 0.04, ("medium",   "cpu"): 1.20,
    ("large",    "cuda"): 0.06, ("large",    "cpu"): 3.00,
    ("large-v2", "cuda"): 0.06, ("large-v2", "cpu"): 3.00,
    ("large-v3", "cuda"): 0.06, ("large-v3", "cpu"): 3.00,
}

# 2시간 기준 단계별 예상 소요 (초) — GPU medium 기준
STAGE_EST_2H = {
    "다운로드": 90,      # ~100MB 오디오, 50MB/s
    "STT":      432,    # 7200s * 0.06 RTF (faster-whisper large-v3)
    "병합":     2,
    "Claude":   120,    # 약 10 청크 × 12초
    "저장":     2,
}

# 전체 진행률 비중
STAGE_WEIGHTS = [0.08, 0.62, 0.02, 0.25, 0.03]
STAGE_NAMES   = ["다운로드", "STT", "병합", "Claude", "저장"]


# ── 타이머 ────────────────────────────────────────────────────
class Timer:
    def __init__(self):
        self.total_t0  = time.time()
        self.stage_t0  = time.time()
        self.completed: dict[str, float] = {}
        self.est_total: float = sum(STAGE_EST_2H.values())

    def start_stage(self):
        self.stage_t0 = time.time()

    def end_stage(self, name: str) -> float:
        e = time.time() - self.stage_t0
        self.completed[name] = e
        return e

    def elapsed(self) -> float:
        return time.time() - self.total_t0

    def overall_pct(self, stage_idx: int, within_pct: float = 0.0) -> float:
        done = sum(STAGE_WEIGHTS[:stage_idx])
        cur  = STAGE_WEIGHTS[stage_idx] * min(within_pct, 100) / 100
        return min(99.0, (done + cur) * 100)

    def est_remaining(self, stage_idx: int, within_pct: float = 0.0) -> float:
        overall = self.overall_pct(stage_idx, within_pct) / 100
        if overall <= 0:
            return self.est_total
        elapsed = self.elapsed()
        total_est = elapsed / overall
        return max(0, total_est - elapsed)


TIMER = Timer()


# ── STT 캐시 ──────────────────────────────────────────────────
def _cache_path(url: str, model_size: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{key}_{model_size}.json"


def _load_cache(url: str, model_size: str):
    p = _cache_path(url, model_size)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data["segments"], data["audio_dur"]


def _save_cache(url: str, model_size: str, segments: list, audio_dur: float):
    p = _cache_path(url, model_size)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"url": url, "model": model_size, "segments": segments,
                   "audio_dur": audio_dur, "saved_at": datetime.now().isoformat()},
                  f, ensure_ascii=False, indent=2)


# ── 공통 출력 유틸 ────────────────────────────────────────────
def _print(msg: str, **kwargs):
    if console:
        console.print(msg, **kwargs)
    else:
        print(re.sub(r'\[/?[a-zA-Z0-9_# ]*\]', '', msg))

def fmt_time(sec: float) -> str:
    m, s = divmod(int(max(0, sec)), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def get_sys_stats() -> str:
    parts = []
    if HAS_PSUTIL:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        parts.append(f"CPU [bold cyan]{cpu:.0f}%[/bold cyan]  "
                     f"RAM [bold cyan]{mem.used/1e9:.1f}/{mem.total/1e9:.1f}GB[/bold cyan]")
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            rsv   = torch.cuda.memory_reserved(i) / 1e9
            total = torch.cuda.get_device_properties(i).total_memory / 1e9
            name  = torch.cuda.get_device_properties(i).name
            parts.append(f"GPU[{i}] [bold cyan]{name}[/bold cyan] "
                         f"VRAM [bold cyan]{rsv:.1f}/{total:.1f}GB[/bold cyan]")
    return "  │  ".join(parts) if parts else "[dim]모니터링 없음 (pip install psutil)[/dim]"

def overall_bar_str(stage_idx: int, within_pct: float = 0.0) -> str:
    pct = TIMER.overall_pct(stage_idx, within_pct)
    filled = int(20 * pct / 100)
    bar = "█" * filled + "░" * (20 - filled)
    elapsed  = fmt_time(TIMER.elapsed())
    remaining = fmt_time(TIMER.est_remaining(stage_idx, within_pct))
    return (f"[bold]{bar}[/bold] [cyan]{pct:.0f}%[/cyan]  "
            f"경과 [cyan]{elapsed}[/cyan] / 남은 예상 [dim]{remaining}[/dim]")

def stage_header(stage_idx: int, name: str):
    n, total = stage_idx + 1, len(STAGE_NAMES)
    TIMER.start_stage()
    _print("")
    if console:
        console.rule(f"[bold cyan]단계 {n}/{total}: {name}[/bold cyan]")
    else:
        print(f"\n{'─'*60}\n  [{n}/{total}단계] {name}\n{'─'*60}")
    _print(f"  전체 진행: {overall_bar_str(stage_idx)}")
    _print(f"  {get_sys_stats()}")

def stage_done(stage_idx: int, extra: str = ""):
    name    = STAGE_NAMES[stage_idx]
    elapsed = TIMER.end_stage(name)
    _print(f"  [green][완료][/green] {name} — [cyan]{fmt_time(elapsed)}[/cyan] 소요{extra}")

def make_progress(**kwargs) -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("  [cyan]{task.description}"),
        BarColumn(bar_width=36),
        TaskProgressColumn(),
        TextColumn(" [dim]{task.fields[extra]}[/dim]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
        **kwargs,
    )


# ── CUDA 진단 ─────────────────────────────────────────────────
def diagnose_cuda() -> str:
    _print("")
    _print(f"  PyTorch [bold]{torch.__version__}[/bold]  "
           f"CUDA: [bold]{torch.version.cuda or '없음 (CPU 전용)'}[/bold]")

    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            p = torch.cuda.get_device_properties(i)
            _print(f"  [green]OK CUDA 사용 가능[/green]  "
                   f"GPU[{i}] [bold]{p.name}[/bold]  {p.total_memory/1e9:.1f}GB")
        return "cuda"

    _print("  [red]CUDA 사용 불가[/red] — 원인 분석 중...")
    if torch.version.cuda is None:
        _print("  [red]원인: CPU 전용 PyTorch 설치됨[/red]")
        _print("  [yellow]수정: pip install torch --index-url "
               "https://download.pytorch.org/whl/cu124[/yellow]")
        _print("  [dim]→ CPU로 실행 (GPU 대비 5~15배 느림)[/dim]")
        return "cpu"

    try:
        r = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            _print("  [green]OK nvidia-smi 감지됨[/green]")
            for line in r.stdout.splitlines():
                if "CUDA Version" in line or "Driver Version" in line:
                    _print(f"    {line.strip()}")
            _print(f"  [yellow]→ PyTorch CUDA {torch.version.cuda} / 드라이버 버전 불일치 가능성[/yellow]")
            _print("    https://pytorch.org/get-started/locally/ 에서 재설치")
        else:
            _print("  [red]nvidia-smi 실패[/red] — 드라이버 미설치 또는 GPU 없음")
    except FileNotFoundError:
        _print("  [red]nvidia-smi 없음[/red] — NVIDIA GPU 없거나 드라이버 미설치")

    _print("  [dim]→ CPU로 실행합니다[/dim]")
    return "cpu"


# ── 선수 선택 ─────────────────────────────────────────────────
def select_player(player_arg: str | None) -> str:
    """Returns 'TEAM' or player name (uppercase)."""
    if player_arg:
        return player_arg.upper()

    _print("\n  이 영상은 팀 전체 영상인가요, 특정 선수 영상인가요?")
    _print("  [1] TEAM  [2] 선수 직접 입력")
    if REGISTERED_PLAYERS:
        _print(f"  등록 선수: [cyan]{', '.join(REGISTERED_PLAYERS)}[/cyan]")

    try:
        choice = input("\n  선택 (1/2, 기본 1): ").strip()
    except (EOFError, KeyboardInterrupt):
        return "TEAM"

    if choice == "2":
        try:
            name = input("  선수 이름: ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            return "TEAM"
        return name if name else "TEAM"
    return "TEAM"


# ── 1단계: YouTube 오디오 추출 ────────────────────────────────
def download_audio(url: str) -> tuple[Path, str]:
    stage_header(0, "YouTube 오디오 추출")

    dl_state = {"pct": 0.0, "speed": "", "size": ""}

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            down  = d.get("downloaded_bytes", 0)
            spd   = d.get("speed") or 0
            dl_state["pct"]   = min(99.9, down / total * 100) if total else 0
            dl_state["speed"] = f"{spd/1e6:.1f}MB/s" if spd else "─"
            dl_state["size"]  = (f"{down/1e6:.1f}/{total/1e6:.1f}MB"
                                  if total else f"{down/1e6:.1f}MB")
        elif d["status"] == "finished":
            dl_state["pct"] = 100.0

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(AUDIO_PATH.with_suffix("")),
        "postprocessors": [{"key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3", "preferredquality": "192"}],
        "quiet": True, "no_warnings": True, "noprogress": True,
        "progress_hooks": [hook],
    }

    title_holder: list[str] = []
    error_holder: list[Exception] = []

    def _dl():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title_holder.append(info.get("title", "unknown"))
        except Exception as e:
            error_holder.append(e)

    thread = threading.Thread(target=_dl, daemon=True)
    thread.start()

    if HAS_RICH:
        with make_progress() as prog:
            task = prog.add_task("오디오 다운로드", total=100.0, extra="")
            while thread.is_alive():
                pct   = dl_state["pct"]
                extra = f"{dl_state['speed']}  {dl_state['size']}"
                prog.update(task, completed=pct, extra=extra)
                time.sleep(0.1)
            prog.update(task, completed=100.0, extra="ffmpeg 변환 중...")
    thread.join()

    if error_holder:
        raise error_holder[0]

    title = title_holder[0] if title_holder else "unknown"
    stage_done(0, f"  |  영상: {title}")
    return AUDIO_PATH, title


# ── 2단계: Whisper STT ────────────────────────────────────────
def transcribe(audio_path: Path, model_size: str = "large-v3", url: str = "") -> tuple[list[dict], float]:
    stage_header(1, f"Whisper({model_size}) 음성 인식")

    if url:
        cached = _load_cache(url, model_size)
        if cached is not None:
            raw, audio_dur = cached
            stage_done(1, f"  |  [캐시 사용] STT 건너뜀  {len(raw)}개 세그먼트  {fmt_time(audio_dur)}")
            return raw, audio_dur

    device = diagnose_cuda()
    compute_type = "float16" if device == "cuda" else "int8"
    _print(f"\n  모델: [bold cyan]faster-whisper {model_size}[/bold cyan]  "
           f"장치: [bold cyan]{device.upper()}[/bold cyan]  "
           f"연산: [bold cyan]{compute_type}[/bold cyan]")

    t_load = time.time()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    _print(f"  [green]OK[/green] 모델 로드  [dim]({time.time()-t_load:.1f}초)[/dim]")

    state: dict = {"result": None, "error": None, "audio_dur": 0.0}
    t_stt = time.time()

    def _run():
        try:
            segs_gen, info = model.transcribe(
                str(audio_path), language=None, task="transcribe", beam_size=5,
                initial_prompt=INITIAL_PROMPT,
            )
            state["audio_dur"] = info.duration
            state["result"] = [
                {"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segs_gen
            ]
        except Exception as e:
            state["error"] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # audio_dur 확보 대기 (최대 30초, info.duration은 transcribe 시작 직후 사용 가능)
    t_wait = time.time()
    while state["audio_dur"] == 0.0 and thread.is_alive() and time.time() - t_wait < 30:
        time.sleep(0.3)
    audio_dur = state["audio_dur"] if state["audio_dur"] > 0 else 7200.0

    rtf = RTF_ESTIMATE.get((model_size, device), 0.06)
    est_stt = audio_dur * rtf
    TIMER.est_total = (TIMER.completed.get("다운로드", STAGE_EST_2H["다운로드"])
                       + est_stt + STAGE_EST_2H["병합"]
                       + STAGE_EST_2H["Claude"] + STAGE_EST_2H["저장"])

    _print(f"  오디오 길이: [bold cyan]{fmt_time(audio_dur)}[/bold cyan]  │  "
           f"STT 예상: [dim]~{fmt_time(est_stt)} ({device.upper()} {compute_type} RTF≈{rtf})[/dim]")

    if HAS_RICH:
        with Live(console=console, refresh_per_second=2) as live:
            while thread.is_alive():
                elapsed_stt = time.time() - t_stt
                stt_pct = min(95.0, elapsed_stt / est_stt * 100) if est_stt > 0 else 0
                within_overall = stt_pct / 100 * 100
                overall_pct = TIMER.overall_pct(1, within_overall)

                bar_w = 36
                filled = int(bar_w * stt_pct / 100)
                stt_bar = "█" * filled + "░" * (bar_w - filled)

                o_filled = int(20 * overall_pct / 100)
                o_bar = "█" * o_filled + "░" * (20 - o_filled)

                remaining = TIMER.est_remaining(1, within_overall)

                tbl = Table.grid(padding=(0, 0))
                tbl.add_row(
                    f"  [bold]전체[/bold]  [{o_bar}] [cyan]{overall_pct:.0f}%[/cyan]  "
                    f"경과 [cyan]{fmt_time(TIMER.elapsed())}[/cyan]  "
                    f"남은 예상 [dim]{fmt_time(remaining)}[/dim]"
                )
                tbl.add_row(f"  [dim]{get_sys_stats()}[/dim]")
                tbl.add_row(
                    f"  [cyan]STT[/cyan]  [{stt_bar}] [bold]{stt_pct:.0f}%[/bold] (예상)  "
                    f"경과 [cyan]{fmt_time(elapsed_stt)}[/cyan] / "
                    f"예상 [dim]{fmt_time(est_stt)}[/dim]  "
                    f"[dim]{device.upper()} {compute_type}[/dim]"
                )
                live.update(tbl)
                time.sleep(0.5)
    thread.join()

    if state["error"]:
        raise state["error"]

    raw = state["result"]
    audio_dur = state["audio_dur"] if state["audio_dur"] > 0 else audio_dur

    elapsed_stt = time.time() - t_stt
    actual_rtf = elapsed_stt / audio_dur if audio_dur > 0 else 0
    if url:
        _save_cache(url, model_size, raw, audio_dur)
    stage_done(1, f"  |  {len(raw)}개 세그먼트  실제RTF {actual_rtf:.2f}x  {device.upper()}")
    return raw, audio_dur


# ── 3단계: 세그먼트 병합 (타임스탬프 정확도를 위해 병합 없이 passthrough) ──────
# ── 환각 필터 설정 ────────────────────────────────────────────
_HERO_NAMES = {
    "아나", "루시우", "라마트라", "시그마", "소주", "자리야", "겐지",
    "트레이서", "위도우", "파라", "디바", "윈스턴", "라인하르트",
    "오리사", "키리코", "모이라", "젠야타", "바티스트", "에코",
    "캐서디", "솔저", "리퍼", "한조", "메이", "해저드", "프레야",
    "킬이", "몽키", "크레아",
}
_FOCUS_KEYWORDS = {"피 1", "반피", "잡아"}


def _is_protected(text: str) -> bool:
    t = text.strip()
    return any(h in t for h in _HERO_NAMES) or any(k in t for k in _FOCUS_KEYWORDS)


def filter_hallucinations(segments: list[dict]) -> list[dict]:
    """연속 동일 텍스트(환각) 제거. 히어로 이름·포커싱 키워드 포함 시 보존."""
    if not segments:
        return []
    result = [segments[0].copy()]
    removed = 0
    for seg in segments[1:]:
        if seg["text"] == result[-1]["text"] and not _is_protected(seg["text"]):
            removed += 1
        else:
            result.append(seg.copy())
    if removed:
        _print(f"  [dim]환각 필터: {removed}개 중복 세그먼트 제거[/dim]")
    return result


def merge_segments(raw: list[dict]) -> list[dict]:
    stage_header(2, "세그먼트 처리")
    if not raw:
        stage_done(2)
        return []
    stage_done(2, f"  |  {len(raw)}개 세그먼트 (병합 없음 — 타임스탬프 정확)")
    return [s.copy() for s in raw]


def _hms(sec: float) -> str:
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── 4단계: Claude 태그 분류 ──────────────────────────────────
def analyze_with_claude(segments: list[dict], api_key: str) -> list[dict]:
    stage_header(3, "Claude 태그 분류")

    stats = get_stats()
    _print(f"  학습 데이터: {stats['total']}개  (검토 완료 {stats['confirmed']}개)")

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt()

    # 청크별로 (입력텍스트, 해당_세그먼트_리스트) 묶음 생성
    MAX_CHARS = 5000
    MAX_SEGS_PER_CHUNK = 50
    chunk_items: list[tuple[str, list[dict]]] = []
    cur_lines: list[str] = []
    cur_segs: list[dict] = []
    cur_len = 0
    for s in segments:
        line = f"[{_hms(s['start'])}] {s['text']}"
        if (cur_len + len(line) > MAX_CHARS or len(cur_lines) >= MAX_SEGS_PER_CHUNK) and cur_lines:
            chunk_items.append(("\n".join(cur_lines), cur_segs[:]))
            cur_lines, cur_segs, cur_len = [], [], 0
        cur_lines.append(line)
        cur_segs.append(s)
        cur_len += len(line)
    if cur_lines:
        chunk_items.append(("\n".join(cur_lines), cur_segs[:]))

    _print(f"  [dim]{len(chunk_items)}개 청크  │  {get_sys_stats()}[/dim]")
    all_segments: list[dict] = []

    def _parse_and_map(raw_text: str, chunk_segs: list[dict]) -> list[dict]:
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        tagged = json.loads(raw_text)
        # time → text 역매핑 (동일 초 충돌 시 첫 번째 우선)
        time_map = {_hms(s["start"]): s["text"] for s in reversed(chunk_segs)}
        for item in tagged:
            item["text"] = time_map.get(item.get("time", ""), "")
        return tagged

    if HAS_RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("  [cyan]{task.description}"),
            BarColumn(bar_width=36),
            MofNCompleteColumn(),
            TextColumn(" [dim]{task.fields[extra]}[/dim]"),
            TimeElapsedColumn(),
            console=console,
        ) as prog:
            task = prog.add_task("청크 분석", total=len(chunk_items), extra="")
            for i, (chunk_text, chunk_segs) in enumerate(chunk_items, 1):
                prog.update(task, extra=f"청크 {i}/{len(chunk_items)} 전송 중...")
                msg = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": chunk_text}],
                )
                raw_text = msg.content[0].text.strip()
                try:
                    tagged = _parse_and_map(raw_text, chunk_segs)
                    all_segments.extend(tagged)
                except json.JSONDecodeError:
                    _print(f"\n  [yellow]경고: 청크 {i} 파싱 실패[/yellow]")
                briefing_cnt = sum(1 for s in all_segments if s.get("tag") != "미분류")
                prog.update(task, extra=f"청크 {i} 완료 — 전체 {len(all_segments)}개 (브리핑 {briefing_cnt}개)")
                prog.advance(task)
    else:
        for i, (chunk_text, chunk_segs) in enumerate(chunk_items, 1):
            print(f"  청크 {i}/{len(chunk_items)}...", end="\r", flush=True)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": chunk_text}],
            )
            raw_text = msg.content[0].text.strip()
            try:
                tagged = _parse_and_map(raw_text, chunk_segs)
                all_segments.extend(tagged)
            except json.JSONDecodeError:
                print(f"\n  경고: 청크 {i} 파싱 실패")

    briefing_cnt = sum(1 for s in all_segments if s.get("tag") != "미분류")
    unclassified_cnt = len(all_segments) - briefing_cnt
    stage_done(3, f"  |  전체 {len(all_segments)}개 (브리핑 {briefing_cnt}개 / 미분류 {unclassified_cnt}개)")
    return all_segments


# ── 5단계: 결과 저장 ──────────────────────────────────────────
def save_results(briefings: list[dict], title: str,
                 player: str) -> tuple[Path, Path, Path]:
    stage_header(4, "결과 저장")

    out_dir = OUTPUT_BASE / player
    out_dir.mkdir(parents=True, exist_ok=True)

    safe = "".join(c for c in title if c.isalnum() or c in " _-")[:50].strip()
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{safe}_{ts}" if safe else ts

    txt_path  = out_dir / f"{base}.txt"
    json_path = out_dir / f"{base}.json"
    csv_path  = out_dir / f"{base}_review.csv"

    briefing_cnt = sum(1 for b in briefings if b.get("tag") != "미분류")
    unclassified_cnt = len(briefings) - briefing_cnt

    def _write_all():
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"스크림 브리핑 기록\n영상: {title}\n")
            f.write(f"대상: {player}\n")
            f.write(f"추출일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"전체 세그먼트: {len(briefings)}개  (브리핑 {briefing_cnt}개 / 미분류 {unclassified_cnt}개)\n{'='*60}\n\n")
            for b in briefings:
                label = TAG_NAMES.get(b.get("tag", "미분류"), "미분류")
                f.write(f"[{b['time']}] ({label})\n{b['text']}\n\n")
        yield 1, "TXT 저장"

        review_data = [{**b, "confirmed": False, "corrected_tag": "", "player": player}
                       for b in briefings]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(review_data, f, ensure_ascii=False, indent=2)
        yield 2, "JSON 저장"

        with open(csv_path, "w", encoding="utf-8-sig") as f:
            f.write("타임스탬프,AI 태그,수정 태그(비워두면 AI 태그 사용),브리핑 내용\n")
            for b in briefings:
                text_esc = b["text"].replace('"', '""')
                f.write(f'{b["time"]},{b.get("tag","focus")},,"{text_esc}"\n')
        yield 3, "CSV 저장"

    if HAS_RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("  [cyan]{task.description}"),
            BarColumn(bar_width=36),
            MofNCompleteColumn(),
            TextColumn(" [dim]{task.fields[extra]}[/dim]"),
            TimeElapsedColumn(),
            console=console,
        ) as prog:
            task = prog.add_task("파일 저장", total=3, extra="")
            for step, msg in _write_all():
                prog.update(task, completed=step, extra=msg)
    else:
        for _ in _write_all():
            pass

    stage_done(4, f"  |  {out_dir}")
    return txt_path, json_path, csv_path



# ── 모델 비교 테스트 ──────────────────────────────────────────
def compare_models(url: str):
    """small / medium 두 모델로 첫 5분 구간 비교."""
    if console:
        console.rule("[bold cyan]Whisper 모델 비교 테스트[/bold cyan]")
    _print("  small / medium 비교  │  구간: 처음 5분")

    audio_path, title = download_audio(url)

    device = diagnose_cuda()
    CLIP_SEC = 300
    _print(f"  구간: [cyan]{fmt_time(CLIP_SEC)}[/cyan]  │  장치: [cyan]{device.upper()}[/cyan]")

    results: dict = {}
    for msize in ["small", "medium"]:
        if console:
            console.rule(f"[dim]{msize} 모델[/dim]")
        _print(f"  {msize} 로딩...")
        model = WhisperModel(msize, device=device,
                             compute_type="float16" if device == "cuda" else "int8")
        t0 = time.time()
        segs_gen, info = model.transcribe(
            str(audio_path), language=None, task="transcribe", beam_size=5,
            clip_timestamps=f"0,{CLIP_SEC}",
            initial_prompt=INITIAL_PROMPT,
        )
        elapsed = time.time() - t0
        segs = [{"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segs_gen if s.start < CLIP_SEC]
        actual_dur = min(info.duration, float(CLIP_SEC))
        results[msize] = {"segs": segs, "elapsed": elapsed, "dur": actual_dur}
        rtf = elapsed / actual_dur if actual_dur > 0 else 0
        _print(f"  [green][완료][/green] {msize} — {fmt_time(elapsed)}  "
               f"{len(segs)}개 세그먼트  RTF {rtf:.2f}x")
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    if audio_path.exists():
        audio_path.unlink()

    s_segs = results["small"]["segs"]
    m_segs = results["medium"]["segs"]
    s_time = results["small"]["elapsed"]
    m_time = results["medium"]["elapsed"]
    actual_dur = results["medium"].get("dur", float(CLIP_SEC))

    if console:
        console.rule("[bold green]비교 결과[/bold green]")

    _print(f"  영상: [bold]{title[:55]}[/bold]")
    _print(f"  구간: 처음 {fmt_time(actual_dur)}")
    _print("")
    _print("  [bold]── 속도 ──[/bold]")
    _print(f"    small  : [cyan]{fmt_time(s_time)}[/cyan]  (RTF {actual_dur / s_time:.1f}x 실시간)")
    _print(f"    medium : [cyan]{fmt_time(m_time)}[/cyan]  (RTF {actual_dur / m_time:.1f}x 실시간)")
    _print(f"    → medium이 small보다 [yellow]{m_time / s_time:.1f}배[/yellow] 느림")
    _print("")
    _print(f"  [bold]── 세그먼트 수 ──[/bold]")
    _print(f"    small  : {len(s_segs)}개")
    _print(f"    medium : {len(m_segs)}개")
    _print("")
    _print("  [bold]── 인식 결과 비교 ──[/bold]")

    # 타임스탬프 기준으로 두 모델 세그먼트 매칭
    MATCH_GAP = 3.0
    all_segs = [(s, "small") for s in s_segs] + [(s, "medium") for s in m_segs]
    all_segs.sort(key=lambda x: x[0]["start"])
    used: set = set()
    pairs: list = []

    for i, (seg_a, model_a) in enumerate(all_segs):
        if i in used:
            continue
        matched = None
        for j, (seg_b, model_b) in enumerate(all_segs):
            if j in used or j == i or model_b == model_a:
                continue
            if abs(seg_b["start"] - seg_a["start"]) <= MATCH_GAP:
                matched = (j, seg_b, model_b)
                break
        if matched:
            j, seg_b, model_b = matched
            used.add(i)
            used.add(j)
            if model_a == "small":
                pairs.append({"time": seg_a["start"],
                               "small": seg_a["text"], "medium": seg_b["text"]})
            else:
                pairs.append({"time": seg_a["start"],
                               "small": seg_b["text"], "medium": seg_a["text"]})
        else:
            pairs.append({"time": seg_a["start"], model_a: seg_a["text"]})

    pairs.sort(key=lambda x: x["time"])
    same_cnt = diff_cnt = 0

    for pair in pairs:
        ts = _hms(pair["time"])
        s_txt = pair.get("small", "─")
        m_txt = pair.get("medium", "─")
        is_same = (s_txt == m_txt and s_txt != "─")
        same_cnt += int(is_same)
        if not is_same and "small" in pair and "medium" in pair:
            diff_cnt += 1
        _print(f"  [{ts}]")
        _print(f"    small : {s_txt}")
        suffix = "  [dim]✓ 동일[/dim]" if is_same else ""
        _print(f"    medium: {m_txt}{suffix}")
        _print("")

    if console:
        console.rule()
    total = same_cnt + diff_cnt
    _print("  [bold]── 요약 ──[/bold]")
    if total > 0:
        _print(f"    동일: {same_cnt}개 / 차이: {diff_cnt}개  "
               f"(일치율 {same_cnt / total * 100:.0f}%)")
    _print(f"    small 단독 세그먼트 : {sum(1 for p in pairs if 'medium' not in p)}개")
    _print(f"    medium 단독 세그먼트: {sum(1 for p in pairs if 'small' not in p)}개")


# ── 메인 ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="오버워치 스크림 브리핑 추출기")
    parser.add_argument("url", nargs="?", default=None)
    parser.add_argument("--model", default="large-v3",
                        choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"])
    parser.add_argument("--player", default=None,
                        help="저장 대상 (TEAM 또는 선수 이름). 없으면 대화형 선택.")
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_API_KEY", ""))
    parser.add_argument("--compare-models", metavar="URL", dest="compare_models",
                        default=None, help="small/medium 모델 비교 테스트 (처음 5분)")
    args = parser.parse_args()

    if args.compare_models:
        compare_models(args.compare_models)
        sys.exit(0)

    if not args.url:
        parser.error("URL이 필요합니다. 사용법: python extractor.py <URL>")

    if not args.api_key:
        _print("[red]오류[/red]: ANTHROPIC_API_KEY가 없습니다. .env 파일을 확인해주세요.")
        sys.exit(1)

    if console:
        console.rule("[bold cyan]오버워치 스크림 브리핑 추출기[/bold cyan]")
        _print(f"  [dim]모델: {args.model}  │  2시간 영상 기준 총 예상 소요: "
               f"~{fmt_time(sum(STAGE_EST_2H.values()))}[/dim]")
    else:
        print("=" * 60)
        print("  오버워치 스크림 브리핑 추출기")
        print("=" * 60)

    # 선수 선택 (--player 없으면 대화형)
    player = select_player(args.player)
    _print(f"  저장 대상: [bold cyan]{player}[/bold cyan]  "
           f"→  [dim]output/{player}/[/dim]")

    try:
        audio_path, title = download_audio(args.url)

        raw_segs, audio_dur = transcribe(audio_path, model_size=args.model, url=args.url)

        merged = merge_segments(raw_segs)
        merged = filter_hallucinations(merged)

        briefings = analyze_with_claude(merged, api_key=args.api_key)

        txt_path, _, csv_path = save_results(briefings, title, player)

        if AUDIO_PATH.exists():
            AUDIO_PATH.unlink()

        # ── 최종 요약 ──────────────────────────────────────────
        total_elapsed = TIMER.elapsed()
        if console:
            console.rule("[bold green]완료[/bold green]")
        else:
            print("\n" + "=" * 60)

        briefing_cnt = sum(1 for b in briefings if b.get("tag") != "미분류")
        _print(f"\n  총 소요시간: [bold cyan]{fmt_time(total_elapsed)}[/bold cyan]  │  "
               f"대상: [bold]{player}[/bold]  │  전체 {len(briefings)}개 (브리핑 [bold]{briefing_cnt}개[/bold])")
        _print("\n  단계별 소요:")
        for name, sec in TIMER.completed.items():
            _print(f"    {name:<8}  [cyan]{fmt_time(sec)}[/cyan]")
        _print(f"\n  결과: [bold]{txt_path}[/bold]")
        _print(f"  검토: [bold]{csv_path}[/bold]  [dim]← 엑셀 수정 후 review.py apply 실행[/dim]")

    except KeyboardInterrupt:
        _print("\n[yellow]중단[/yellow]: 취소되었습니다.")
        if AUDIO_PATH.exists(): AUDIO_PATH.unlink()
        sys.exit(0)
    except Exception as e:
        _print(f"\n[red]오류[/red]: {e}")
        if AUDIO_PATH.exists(): AUDIO_PATH.unlink()
        raise


if __name__ == "__main__":
    main()
