"""
learning.py — 브리핑 학습 데이터베이스
--------------------------------------
- examples.json 에 누적된 검토 데이터를 관리
- 분석 시 태그별 최적 예시를 자동 선별해 프롬프트에 삽입
"""

import json
import random
from pathlib import Path
from datetime import datetime

EXAMPLES_PATH = Path("examples.json")

TAG_NAMES = {
    "focus":     "포커싱/체력",
    "ult_check": "궁체크",
    "ult_strat": "궁극기 전략",
    "position":  "포지션",
    "tempo":     "방향성",
    "미분류":    "미분류",
}

# few-shot 예시에는 브리핑 태그만 사용 (미분류 제외)
BRIEFING_TAGS = {k for k in TAG_NAMES if k != "미분류"}

# ── 씨앗 예시 (최초 실행 시 사용, 이후 팀 데이터로 교체됨) ──────
SEED_EXAMPLES = [
    {"text": "겐지 겐지 겐지! 겐지 잡아! 힐러 나중에!",         "tag": "focus",     "confirmed": True, "used": 0},
    {"text": "Ana 피 1이야! 뒤로 빠져!",                       "tag": "focus",     "confirmed": True, "used": 0},
    {"text": "상대 루시우 궁 있을 거야, 이번에 못 썼으니까.",    "tag": "ult_check", "confirmed": True, "used": 0},
    {"text": "저쪽 아나 궁 없어. 방금 한타에서 썼어.",           "tag": "ult_check", "confirmed": True, "used": 0},
    {"text": "자리야 궁 먼저 박고 라인하르트 궁 연계해.",        "tag": "ult_strat", "confirmed": True, "used": 0},
    {"text": "소주 궁 아껴. 다음 한타 때 써.",                  "tag": "ult_strat", "confirmed": True, "used": 0},
    {"text": "탱커 둘은 왼쪽 박스 뒤로. Ana 2층 고지 유지.",    "tag": "position",  "confirmed": True, "used": 0},
    {"text": "Sigma 오른쪽 코너. 방패 방향 12시 고정.",          "tag": "position",  "confirmed": True, "used": 0},
    {"text": "우리가 먼저 선 진입한다. 상대 세팅 끝나기 전에.", "tag": "tempo",     "confirmed": True, "used": 0},
    {"text": "지금은 버텨. 저쪽이 들어오게 해.",                "tag": "tempo",     "confirmed": True, "used": 0},
]


def load_examples() -> list[dict]:
    """examples.json 로드. 없으면 씨앗 데이터로 초기화."""
    if not EXAMPLES_PATH.exists():
        save_examples(SEED_EXAMPLES)
        return SEED_EXAMPLES.copy()
    with open(EXAMPLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_examples(examples: list[dict]):
    with open(EXAMPLES_PATH, "w", encoding="utf-8") as f:
        json.dump(examples, f, ensure_ascii=False, indent=2)


def add_example(text: str, tag: str, confirmed: bool = False, player: str = "TEAM"):
    """새 예시 추가. 동일 텍스트가 있으면 태그·선수 업데이트."""
    examples = load_examples()
    for ex in examples:
        if ex["text"].strip() == text.strip():
            ex["tag"] = tag
            ex["confirmed"] = confirmed
            ex["player"] = player
            save_examples(examples)
            return
    examples.append({
        "text": text,
        "tag": tag,
        "confirmed": confirmed,
        "player": player,
        "used": 0,
        "added_at": datetime.now().strftime("%Y-%m-%d"),
    })
    save_examples(examples)


def get_stats(player: str | None = None) -> dict:
    """학습 데이터 통계. player 지정 시 해당 선수 데이터만 집계."""
    all_examples = load_examples()
    examples = (
        [e for e in all_examples if e.get("player", "TEAM") == player]
        if player else all_examples
    )
    stats = {"total": len(examples), "confirmed": 0, "by_tag": {}}
    for tag in TAG_NAMES:
        stats["by_tag"][tag] = {"total": 0, "confirmed": 0}
    for ex in examples:
        tag = ex.get("tag", "focus")
        if tag in stats["by_tag"]:
            stats["by_tag"][tag]["total"] += 1
            if ex.get("confirmed"):
                stats["confirmed"] += 1
                stats["by_tag"][tag]["confirmed"] += 1
    return stats


# ── 프롬프트 빌더 ────────────────────────────────────────────
EXAMPLES_PER_TAG = 3   # 태그당 프롬프트에 삽입할 최대 예시 수


def _score(ex: dict) -> float:
    """confirmed 예시 우선, 자주 쓰인 것은 약간 배제해 다양성 확보."""
    base = 2.0 if ex.get("confirmed") else 1.0
    used_penalty = min(ex.get("used", 0) * 0.05, 0.5)
    return base - used_penalty + random.uniform(0, 0.1)


def build_few_shot_block() -> str:
    """태그별로 best 예시를 선별해 few-shot 블록 문자열 반환."""
    examples = load_examples()
    by_tag: dict[str, list] = {tag: [] for tag in BRIEFING_TAGS}
    for ex in examples:
        tag = ex.get("tag")
        if tag in by_tag:
            by_tag[tag].append(ex)

    lines = ["[참고 예시 — 팀 실제 브리핑 데이터]"]
    selected_ids = []

    for tag, exs in by_tag.items():
        if not exs:
            continue
        ranked = sorted(exs, key=_score, reverse=True)[:EXAMPLES_PER_TAG]
        selected_ids.extend(id(ex) for ex in ranked)
        for ex in ranked:
            lines.append(f'  입력: "{ex["text"]}"  →  태그: {tag}')

    # used 카운트 증가
    for ex in examples:
        if id(ex) in selected_ids:
            ex["used"] = ex.get("used", 0) + 1
    save_examples(examples)

    return "\n".join(lines)


def build_system_prompt() -> str:
    few_shot = build_few_shot_block()
    return f"""당신은 e스포츠(오버워치) 스크림 영상 분석 전문가입니다.

입력된 STT 세그먼트 전체에 태그를 붙여 JSON 배열로 반환하세요.
입력된 세그먼트를 단 하나도 빠뜨리지 말고 순서대로 모두 반환하세요.
브리핑이 아닌 발화(감탄사, 잡담, 단순 리액션, 의미 없는 소음 등)는 "미분류" 태그를 사용하세요.

반환 형식 (JSON 배열만, 다른 텍스트 없이):
[
  {{
    "time": "HH:MM:SS",
    "tag": "focus|ult_check|ult_strat|position|tempo|미분류"
  }}
]

태그 기준:
- focus     : 포커싱/체력. 영웅 이름 반복 호명, "OO 잡아", "OO 피 1" 같은 즉각적 대상 지정
- ult_check : 궁체크. 한타 후 소강상태에서 상대 궁극기 보유 현황 예측·공유
- ult_strat : 궁극기 전략. 아군이 어떤 궁을 언제 어떻게 쓸지 지시
- position  : 포지션. 아군이 어느 위치에 자리잡을지 지시
- tempo     : 방향성. 선템포 진입 vs 수비적 대기 중 운영 방향 결정
- 미분류    : 감탄사, 잡담, 단순 리액션, 의미 없는 소음 등 브리핑이 아닌 발화

{few_shot}""".strip()
