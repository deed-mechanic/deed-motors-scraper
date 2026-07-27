#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index.html <-> テンプレート 同期チェック・同期ツール

build_html.py はテンプレート + price_db.json から index.html (または
bilingual.html) を毎日自動生成する。テンプレートと生成物のうち
「PRICE_DBブロック」と「更新バッジ」以外の部分は本来常に一致しているべき。

  check : 2ファイルを比較し、差分があれば diff を表示して非ゼロ終了する
  sync  : index.html 側の内容をテンプレート側へコピーする（更新バッジは自動除去）
"""
import re
import sys
import argparse
import difflib
from pathlib import Path

BADGE_RE = re.compile(
    r'(?:<span style="font-size:10px;color:#888;margin-left:8px;">.*?</span>)+'
)


def strip_dynamic(html: str) -> str:
    """PRICE_DBブロックと更新バッジを取り除く（テンプレート側はバッジ0個・
    index.html側は最新1個が正しい状態なので、比較のためにどちらも除去する）"""
    start = html.find("const PRICE_DB = {")
    if start != -1:
        end = html.find("};", start)
        if end != -1:
            html = html[:start] + "__PRICE_DB__" + html[end + 2:]
    html = BADGE_RE.sub("", html)
    return html


def strip_badges(html: str) -> str:
    return BADGE_RE.sub("", html)


def cmd_check(index_path: str, template_path: str) -> int:
    index_html = Path(index_path).read_text(encoding="utf-8")
    template_html = Path(template_path).read_text(encoding="utf-8")

    a = strip_dynamic(index_html)
    b = strip_dynamic(template_html)

    if a == b:
        print(f"OK: {index_path} と {template_path} は同期されています")
        return 0

    print(f"NG: {index_path} と {template_path} に差分があります（PRICE_DB・更新バッジを除く）")
    diff = difflib.unified_diff(
        a.splitlines(), b.splitlines(),
        fromfile=index_path, tofile=template_path, lineterm="",
    )
    for line in list(diff)[:200]:
        print(line)
    print(f"\n次を実行して同期してください: python scripts/sync_template.py sync --index {index_path} --template {template_path}")
    return 1


def cmd_sync(index_path: str, template_path: str) -> int:
    html = Path(index_path).read_text(encoding="utf-8")
    html = strip_badges(html)
    Path(template_path).write_text(html, encoding="utf-8")
    print(f"同期完了: {index_path} -> {template_path}（更新バッジは除去済み）")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["check", "sync"])
    parser.add_argument("--index", default="index.html")
    parser.add_argument("--template", default="templates/deed_motors_PC_v3_template.html")
    args = parser.parse_args()

    if args.mode == "check":
        sys.exit(cmd_check(args.index, args.template))
    else:
        sys.exit(cmd_sync(args.index, args.template))


if __name__ == "__main__":
    main()
