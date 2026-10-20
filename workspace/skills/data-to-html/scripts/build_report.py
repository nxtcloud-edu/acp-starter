#!/usr/bin/env python3
"""여러 md·csv 파일의 요약(JSON)을 검사하고 HTML 리포트로 조립한다.

흐름
----
1. 파일 읽기·요약은 AI(상위 에이전트)가 한다. 아래 스키마의 JSON을 만든다.
2. 이 스크립트는 그 JSON을 **검사만** 한 뒤, 통과하면 HTML 파일로 저장한다.
3. 항목 누락·추가, 자료형 오류, 표의 열/칸 수 불일치가 있으면
   **저장하지 않고** 무엇이 틀렸는지 알려 준다.

고정 스키마
-----------
{
  "제목": "문자열",
  "생성일": "YYYY-MM-DD 문자열 또는 null",
  "TL;DR": ["문자열", "문자열", "문자열"],   # 불렛 3개 고정, 리포트 최상단에 표시
  "문서 요약 목록": [
    {"파일": "문자열", "요약": ["문자열", "..."]},
    ...
  ],
  "표 목록": [
    {
      "제목": "문자열",
      "출처": "문자열",
      "열": ["문자열", "..."],
      "행": [["문자열", "..."], ...]   # 각 행의 칸 수 == 열 수
    },
    ...
  ]
}

- 자료에 없는 내용은 넣지 않는다. 애매한 값은 "확인 필요"로 남긴다(AI 측 규칙).
- 표의 각 행 칸 수는 열 수와 반드시 같아야 한다.

사용법
------
    python3 build_report.py --in 요약.json --out 리포트.html
    cat 요약.json | python3 build_report.py --out 리포트.html
    python3 build_report.py --in 요약.json --check-only

종료 코드
---------
    0  검사 통과(저장 또는 --check-only)
    1  검사 실패(저장 안 함)
    2  입력 오류(JSON 파싱 실패, 파일 없음 등)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date

TOP_FIELDS = ["제목", "생성일", "TL;DR", "문서 요약 목록", "표 목록"]
DOC_FIELDS = ["파일", "요약"]
TABLE_FIELDS = ["제목", "출처", "열", "행"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_str_list(v: object) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def validate(data: object) -> list[str]:
    """검사해서 오류 메시지 목록을 돌려준다. 빈 목록이면 통과."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"최상위 값이 객체(dict)가 아닙니다: {type(data).__name__}"]

    keys = set(data.keys())
    expected = set(TOP_FIELDS)
    for missing in [f for f in TOP_FIELDS if f not in keys]:
        errors.append(f"항목 누락: '{missing}'")
    for extra in sorted(keys - expected):
        errors.append(f"알 수 없는 항목(추가됨): '{extra}'")

    # 제목
    if "제목" in data and not isinstance(data["제목"], str):
        errors.append(f"'제목' 자료형 오류: 문자열이어야 하는데 {type(data['제목']).__name__}")

    # 생성일: YYYY-MM-DD 또는 null
    if "생성일" in data:
        v = data["생성일"]
        if v is None:
            pass
        elif not isinstance(v, str):
            errors.append(f"'생성일' 자료형 오류: 문자열 또는 null 이어야 하는데 {type(v).__name__}")
        elif not _DATE_RE.match(v):
            errors.append(f"'생성일' 형식 오류: 'YYYY-MM-DD' 가 아닙니다 -> {v!r}")
        else:
            try:
                date.fromisoformat(v)
            except ValueError:
                errors.append(f"'생성일' 이 실제 존재하지 않는 날짜입니다 -> {v!r}")

    # TL;DR: 문자열 3개로 된 목록(불렛 3개 고정)
    if "TL;DR" in data:
        v = data["TL;DR"]
        if not _is_str_list(v):
            errors.append("'TL;DR' 자료형 오류: 문자열 목록이어야 함")
        elif len(v) != 3:
            errors.append(f"'TL;DR' 개수 오류: 불렛 3개여야 하는데 {len(v)}개")

    # 문서 요약 목록
    if "문서 요약 목록" in data:
        v = data["문서 요약 목록"]
        if not isinstance(v, list):
            errors.append(f"'문서 요약 목록' 자료형 오류: 목록이어야 하는데 {type(v).__name__}")
        else:
            for i, doc in enumerate(v):
                if not isinstance(doc, dict):
                    errors.append(f"'문서 요약 목록'[{i}] 가 객체(dict)가 아닙니다: {type(doc).__name__}")
                    continue
                dkeys = set(doc.keys())
                for m in [f for f in DOC_FIELDS if f not in dkeys]:
                    errors.append(f"'문서 요약 목록'[{i}] 항목 누락: '{m}'")
                for e in sorted(dkeys - set(DOC_FIELDS)):
                    errors.append(f"'문서 요약 목록'[{i}] 알 수 없는 항목: '{e}'")
                if "파일" in doc and not isinstance(doc["파일"], str):
                    errors.append(f"'문서 요약 목록'[{i}].파일 자료형 오류: 문자열이어야 함")
                if "요약" in doc and not _is_str_list(doc["요약"]):
                    errors.append(f"'문서 요약 목록'[{i}].요약 자료형 오류: 문자열 목록이어야 함")

    # 표 목록
    if "표 목록" in data:
        v = data["표 목록"]
        if not isinstance(v, list):
            errors.append(f"'표 목록' 자료형 오류: 목록이어야 하는데 {type(v).__name__}")
        else:
            for i, tbl in enumerate(v):
                if not isinstance(tbl, dict):
                    errors.append(f"'표 목록'[{i}] 가 객체(dict)가 아닙니다: {type(tbl).__name__}")
                    continue
                tkeys = set(tbl.keys())
                for m in [f for f in TABLE_FIELDS if f not in tkeys]:
                    errors.append(f"'표 목록'[{i}] 항목 누락: '{m}'")
                for e in sorted(tkeys - set(TABLE_FIELDS)):
                    errors.append(f"'표 목록'[{i}] 알 수 없는 항목: '{e}'")
                if "제목" in tbl and not isinstance(tbl["제목"], str):
                    errors.append(f"'표 목록'[{i}].제목 자료형 오류: 문자열이어야 함")
                if "출처" in tbl and not isinstance(tbl["출처"], str):
                    errors.append(f"'표 목록'[{i}].출처 자료형 오류: 문자열이어야 함")

                cols_ok = _is_str_list(tbl.get("열"))
                if "열" in tbl and not cols_ok:
                    errors.append(f"'표 목록'[{i}].열 자료형 오류: 문자열 목록이어야 함")

                rows = tbl.get("행")
                if "행" in tbl:
                    if not isinstance(rows, list):
                        errors.append(f"'표 목록'[{i}].행 자료형 오류: 목록이어야 함")
                    else:
                        ncol = len(tbl["열"]) if cols_ok else None
                        for r, row in enumerate(rows):
                            if not _is_str_list(row):
                                errors.append(f"'표 목록'[{i}].행[{r}] 자료형 오류: 문자열 목록이어야 함")
                                continue
                            if ncol is not None and len(row) != ncol:
                                errors.append(
                                    f"'표 목록'[{i}].행[{r}] 칸 수 불일치: "
                                    f"열 {ncol}개인데 칸 {len(row)}개"
                                )

    return errors


def canonical(data: dict) -> dict:
    out = {f: data[f] for f in TOP_FIELDS}
    out["문서 요약 목록"] = [{f: d[f] for f in DOC_FIELDS} for d in data["문서 요약 목록"]]
    out["표 목록"] = [{f: t[f] for f in TABLE_FIELDS} for t in data["표 목록"]]
    return out


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def build_html(data: dict) -> str:
    title = _esc(data["제목"])
    created = data["생성일"]
    created_txt = _esc(created) if created else "확인 필요"

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="ko"><head><meta charset="utf-8">')
    parts.append(f"<title>{title}</title>")
    parts.append(
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.6;color:#222}"
        "h1{border-bottom:2px solid #333;padding-bottom:.3rem}"
        "h2{margin-top:2rem;color:#1a4d8f}"
        ".meta{color:#666;font-size:.9rem}"
        ".tldr{margin:1.2rem 0 1.6rem;padding:1rem 1.2rem;background:#eef4ff;"
        "color:#1a2b45;border:1px solid #b9d0f5;border-left:5px solid #1a4d8f;border-radius:6px}"
        ".tldr h2{margin:0 0 .5rem;color:#1a4d8f;font-size:1.1rem}"
        ".tldr ul{margin:0;padding-left:1.2rem}"
        ".tldr li{margin:.25rem 0}"
        ".doc{margin:1rem 0;padding:.8rem 1rem;background:#f6f8fa;border-radius:6px}"
        ".doc .file{font-weight:600}"
        "table{border-collapse:collapse;width:100%;margin:.8rem 0}"
        "th,td{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.95rem}"
        "th{background:#eef2f7}"
        "caption{text-align:left;font-weight:600;margin-bottom:.3rem}"
        ".src{color:#888;font-size:.85rem;font-weight:400}"
        "</style></head><body>"
    )
    parts.append(f"<h1>{title}</h1>")
    parts.append(f'<p class="meta">생성일: {created_txt}</p>')

    # TL;DR (가장 먼저, 불렛 3개)
    parts.append('<div class="tldr">')
    parts.append("<h2>TL;DR</h2>")
    parts.append("<ul>")
    for line in data["TL;DR"]:
        parts.append(f"<li>{_esc(line)}</li>")
    parts.append("</ul>")
    parts.append("</div>")

    # 문서 요약
    parts.append("<h2>문서 요약</h2>")
    if data["문서 요약 목록"]:
        for doc in data["문서 요약 목록"]:
            parts.append('<div class="doc">')
            parts.append(f'<div class="file">{_esc(doc["파일"])}</div>')
            if doc["요약"]:
                parts.append("<ul>")
                for line in doc["요약"]:
                    parts.append(f"<li>{_esc(line)}</li>")
                parts.append("</ul>")
            else:
                parts.append("<p class='meta'>(요약 없음)</p>")
            parts.append("</div>")
    else:
        parts.append("<p class='meta'>(문서 요약 없음)</p>")

    # 표
    parts.append("<h2>표</h2>")
    if data["표 목록"]:
        for tbl in data["표 목록"]:
            parts.append("<table>")
            cap = _esc(tbl["제목"])
            src = _esc(tbl["출처"])
            parts.append(f'<caption>{cap} <span class="src">(출처: {src})</span></caption>')
            parts.append("<thead><tr>")
            for col in tbl["열"]:
                parts.append(f"<th>{_esc(col)}</th>")
            parts.append("</tr></thead><tbody>")
            for row in tbl["행"]:
                parts.append("<tr>")
                for cell in row:
                    parts.append(f"<td>{_esc(cell)}</td>")
                parts.append("</tr>")
            parts.append("</tbody></table>")
    else:
        parts.append("<p class='meta'>(표 없음)</p>")

    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


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
    parser = argparse.ArgumentParser(description="요약 JSON 검사 후 HTML 리포트 조립")
    parser.add_argument("--in", dest="in_path", help="입력 요약 JSON 경로 (없으면 stdin)")
    parser.add_argument("--out", dest="out_path", help="저장할 HTML 경로")
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
        return 0

    try:
        with open(args.out_path, "w", encoding="utf-8") as fh:
            fh.write(build_html(result))
    except OSError as exc:
        print(f"[저장 오류] 파일을 쓸 수 없습니다: {exc}", file=sys.stderr)
        return 2

    print(f"[검사 통과] HTML 저장 완료 -> {args.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
