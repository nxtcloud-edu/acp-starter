#!/usr/bin/env python3
"""메모 사진에서 AI가 읽어 낸 결과(JSON)를 검사하고 파일로 저장한다.

흐름
----
1. 사진은 AI(상위 에이전트)가 읽고, 아래 5개 항목으로 정리한 JSON을 만든다.
2. 이 스크립트는 그 JSON을 **검사만** 한 뒤, 통과하면 파일로 저장한다.
3. 항목 누락·추가, 자료형 오류가 하나라도 있으면 저장하지 않고 오류를 알린다.

고정 스키마
-----------
- 메모 날짜 : "YYYY-MM-DD" 문자열 또는 null
- 끝낸 일   : 문자열 목록 (빈 목록은 [])
- 남은 일   : 문자열 목록 (빈 목록은 [])
- 변경한 내용 : 문자열 목록 (빈 목록은 [])
- 확인할 질문 : 문자열 목록 (빈 목록은 [])

사용법
------
    # stdin 으로 JSON 전달
    cat memo.json | python3 save_memo.py --out 결과.json

    # 파일 경로로 JSON 전달
    python3 save_memo.py --in memo.json --out 결과.json

    # 검사만 하고 저장은 하지 않기
    python3 save_memo.py --in memo.json --check-only

종료 코드
---------
    0  검사 통과(저장 성공 또는 --check-only)
    1  검사 실패(저장 안 함)
    2  입력 오류(JSON 파싱 실패, 파일 없음 등)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date

# 항목 순서까지 고정한다.
FIELDS = ["메모 날짜", "끝낸 일", "남은 일", "변경한 내용", "확인할 질문"]
LIST_FIELDS = ["끝낸 일", "남은 일", "변경한 내용", "확인할 질문"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(data: object) -> list[str]:
    """검사해서 오류 메시지 목록을 돌려준다. 빈 목록이면 통과."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"최상위 값이 객체(dict)가 아닙니다: {type(data).__name__}"]

    keys = set(data.keys())
    expected = set(FIELDS)

    # 항목 누락
    for missing in [f for f in FIELDS if f not in keys]:
        errors.append(f"항목 누락: '{missing}'")
    # 항목 추가(알 수 없는 키)
    for extra in sorted(keys - expected):
        errors.append(f"알 수 없는 항목(추가됨): '{extra}'")

    # 메모 날짜: "YYYY-MM-DD" 문자열 또는 null
    if "메모 날짜" in data:
        v = data["메모 날짜"]
        if v is None:
            pass
        elif not isinstance(v, str):
            errors.append(f"'메모 날짜' 자료형 오류: 문자열 또는 null 이어야 하는데 {type(v).__name__}")
        elif not _DATE_RE.match(v):
            errors.append(f"'메모 날짜' 형식 오류: 'YYYY-MM-DD' 가 아닙니다 -> {v!r}")
        else:
            try:
                date.fromisoformat(v)
            except ValueError:
                errors.append(f"'메모 날짜' 가 실제 존재하지 않는 날짜입니다 -> {v!r}")

    # 나머지: 문자열 목록
    for field in LIST_FIELDS:
        if field not in data:
            continue
        v = data[field]
        if not isinstance(v, list):
            errors.append(f"'{field}' 자료형 오류: 목록(list)이어야 하는데 {type(v).__name__}")
            continue
        for i, item in enumerate(v):
            if not isinstance(item, str):
                errors.append(f"'{field}'[{i}] 자료형 오류: 문자열이어야 하는데 {type(item).__name__}")

    return errors


def canonical(data: dict) -> dict:
    """항목 순서를 FIELDS 순으로 고정해 다시 정리한다(검사 통과 후 호출)."""
    return {f: data[f] for f in FIELDS}


def _load(args) -> object:
    if args.in_path:
        try:
            with open(args.in_path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            print(f"[입력 오류] 파일을 읽을 수 없습니다: {exc}", file=sys.stderr)
            sys.exit(2)
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        print("[입력 오류] 입력이 비어 있습니다.", file=sys.stderr)
        sys.exit(2)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[입력 오류] JSON 파싱 실패: {exc}", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="메모 JSON 검사 후 저장")
    parser.add_argument("--in", dest="in_path", help="입력 JSON 파일 경로 (없으면 stdin)")
    parser.add_argument("--out", dest="out_path", help="저장할 JSON 파일 경로")
    parser.add_argument("--check-only", action="store_true", help="검사만 하고 저장하지 않음")
    args = parser.parse_args(argv)

    data = _load(args)
    errors = validate(data)

    if errors:
        print("[검사 실패] 저장하지 않았습니다. 아래 문제를 고쳐 주세요:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    result = canonical(data)

    if args.check_only or not args.out_path:
        print("[검사 통과] (저장 안 함)")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        with open(args.out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        print(f"[저장 오류] 파일을 쓸 수 없습니다: {exc}", file=sys.stderr)
        return 2

    print(f"[검사 통과] 저장 완료 -> {args.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
