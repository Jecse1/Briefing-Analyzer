"""
review.py — 검토 결과를 학습 데이터베이스에 반영
-------------------------------------------------
분석 후 엑셀에서 수정한 CSV를 읽어 examples.json 에 누적.
폴더 구조에서 선수명 자동 감지: output/HANBIN/파일.csv → player=HANBIN
"""

import sys
import csv
import json
import argparse
from pathlib import Path
from learning import (
    TAG_NAMES, add_example, get_stats, load_examples, save_examples
)


def _detect_player(csv_path: Path) -> str:
    """output/PLAYER/파일.csv 구조에서 선수명 추출. 없으면 'TEAM'."""
    parts = csv_path.resolve().parts
    try:
        output_idx = next(i for i, p in enumerate(parts) if p.lower() == "output")
        player_dir = parts[output_idx + 1]
        return player_dir
    except (StopIteration, IndexError):
        return "TEAM"


def review_csv(csv_path: Path, player_override: str | None = None):
    """CSV 검토 결과를 examples.json 에 반영."""
    if not csv_path.exists():
        print(f"[오류] 파일을 찾을 수 없습니다: {csv_path}")
        sys.exit(1)

    player = player_override or _detect_player(csv_path)
    print(f"\n  대상: {player}  ({csv_path.name})")

    added = confirmed = skipped = 0

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text      = row.get("브리핑 내용", "").strip()
            ai_tag    = row.get("AI 태그", "").strip()
            fixed_tag = row.get("수정 태그(비워두면 AI 태그 사용)", "").strip()

            if not text:
                skipped += 1
                continue

            final_tag = fixed_tag if fixed_tag in TAG_NAMES else ai_tag
            if final_tag not in TAG_NAMES:
                skipped += 1
                continue

            add_example(text, final_tag, confirmed=True, player=player)

            if fixed_tag in TAG_NAMES:
                confirmed += 1
            else:
                added += 1

    print(f"\n  학습 데이터 업데이트 완료")
    print(f"  - AI 분류 확정: {added}개")
    print(f"  - 사람이 수정:  {confirmed}개")
    print(f"  - 건너뜀:       {skipped}개")


def show_stats(player_filter: str | None = None):
    """현재 학습 데이터 통계 출력. player_filter가 있으면 해당 선수만."""
    all_stats  = get_stats()
    filt_stats = get_stats(player=player_filter) if player_filter else all_stats

    header = f"학습 데이터 현황" + (f" [{player_filter}]" if player_filter else " [전체]")
    print(f"\n  ─── {header} {'─'*(40-len(header))}")
    print(f"  총 예시:   {filt_stats['total']}개"
          + (f"  (전체 {all_stats['total']}개 중)" if player_filter else ""))
    print(f"  검토 완료: {filt_stats['confirmed']}개")
    print()

    for tag, name in TAG_NAMES.items():
        d       = filt_stats["by_tag"].get(tag, {})
        total   = d.get("total", 0)
        conf    = d.get("confirmed", 0)
        bar_len = min(conf, 20)
        bar     = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {name:<12} [{bar}] {conf:>3}/{total}")

    # 선수별 분포 (전체 조회 시)
    if not player_filter:
        examples = load_examples()
        player_counts: dict[str, int] = {}
        for ex in examples:
            p = ex.get("player", "TEAM")
            player_counts[p] = player_counts.get(p, 0) + 1
        if player_counts:
            print()
            print("  ─── 선수별 데이터 ──────────────────────────")
            for p, cnt in sorted(player_counts.items(), key=lambda x: -x[1]):
                print(f"  {p:<12} {cnt:>4}개")

    print("  " + "─" * 45)


def reset_to_seed():
    from learning import SEED_EXAMPLES
    save_examples(SEED_EXAMPLES)
    print("  학습 데이터가 초기 상태로 리셋되었습니다.")


def main():
    parser = argparse.ArgumentParser(description="브리핑 검토 & 학습 반영")
    sub = parser.add_subparsers(dest="cmd")

    p_apply = sub.add_parser("apply", help="CSV 검토 결과를 학습 데이터에 반영")
    p_apply.add_argument("csv", help="검토 완료된 CSV 파일 경로")
    p_apply.add_argument("--player", default=None,
                         help="선수명 강제 지정 (없으면 폴더에서 자동 감지)")

    p_stats = sub.add_parser("stats", help="학습 데이터 통계 출력")
    p_stats.add_argument("--player", default=None, help="특정 선수 통계만 표시")

    sub.add_parser("reset", help="학습 데이터 초기화")

    args = parser.parse_args()

    print("=" * 60)
    print("  브리핑 학습 관리자")
    print("=" * 60)

    if args.cmd == "apply":
        review_csv(Path(args.csv), player_override=args.player)
        show_stats()

    elif args.cmd == "stats":
        show_stats(player_filter=args.player)

    elif args.cmd == "reset":
        confirm = input("  학습 데이터를 초기화하시겠습니까? (y/N): ")
        if confirm.lower() == "y":
            reset_to_seed()
        else:
            print("  취소되었습니다.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
