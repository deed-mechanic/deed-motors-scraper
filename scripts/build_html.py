#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, re, sys, argparse, logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--db",       required=True)
    parser.add_argument("--fallback", default="")
    parser.add_argument("--out",      required=True)
    args = parser.parse_args()

    # テンプレート読み込み
    log.info(f"テンプレート: {args.template}")
    html = Path(args.template).read_text(encoding="utf-8")
    log.info(f"テンプレートサイズ: {len(html)} 文字")

    # DB読み込み
    log.info(f"DB: {args.db}")
    db = json.loads(Path(args.db).read_text(encoding="utf-8"))
    data = db.get("data", {})
    updated_at = db.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # フォールバックとマージ
    if args.fallback and Path(args.fallback).exists():
        fb = json.loads(Path(args.fallback).read_text(encoding="utf-8"))
        for k, v in fb.get("data", {}).items():
            if k not in data or len(data[k]) < 2:
                data[k] = v
                log.info(f"  フォールバック使用: {k}")

    total = sum(len(v) for v in data.values())
    log.info(f"データ: {len(data)}車種 / {total}件")

    # PRICE_DB JavaScript生成
    lines = ["const PRICE_DB = {"]
    items = list(data.items())
    for idx, (key, records) in enumerate(items):
        is_last = (idx == len(items) - 1)
        lines.append(f'  "{key}":[')
        for ridx, rec in enumerate(records):
            comma = "" if ridx == len(records)-1 else ","
            wheel_part = f',wheel:"{rec["wheel"]}"' if rec.get("wheel") else ""
            lines.append(
                f'    {{year:{rec["year"]},drive:"{rec["drive"]}",'
                f'mileage:"{rec.get("mileage","不明")}",color:"{rec.get("color","不明")}",'
                f'import_year:{rec["import_year"]},price:{rec["price"]}{wheel_part}}}{comma}'
            )
        lines.append("  ]" + ("" if is_last else ","))
    lines.append("};")
    new_price_db = "\n".join(lines)

    # 置換（文字列検索で確実に）
    marker = "const PRICE_DB = {"
    start = html.find(marker)
    if start == -1:
        log.error("const PRICE_DB が見つかりません！")
        log.error(f"先頭500文字: {html[:500]}")
        sys.exit(1)

    # 「};」の終わりを探す
    end = html.find("};", start)
    if end == -1:
        log.error("PRICE_DB の終端 '};' が見つかりません")
        sys.exit(1)
    end += 2  # 「};」の2文字分を含める

    log.info(f"PRICE_DB位置: {start}〜{end}")
    html = html[:start] + new_price_db + html[end:]

    # PRICE_DB_UPDATED_AT 定数も更新（「同一車種の市場価格調査」カード内の
    # データ更新日時表示用。PRICE_DB本体とは別の定数のため、放置すると
    # ここだけ永久に最初の値のまま固まってしまう）
    updated_at_pattern = re.compile(r'const PRICE_DB_UPDATED_AT = "[^"]*";')
    updated_at_const = f'const PRICE_DB_UPDATED_AT = "UNEGUI.MN実データ {updated_at}";'
    html, n_ua = updated_at_pattern.subn(updated_at_const, html, count=1)
    if n_ua == 0:
        log.warning('PRICE_DB_UPDATED_AT が見つからず更新できませんでした')

    # 更新日時バッジ追加（既存バッジは除去してから1個だけ挿入する＝べき等。
    # そうしないとテンプレートに古いバッジが残っていた場合に無限に積み重なる）
    badge = (
        f'<span style="font-size:10px;color:#888;margin-left:8px;">'
        f'更新: {updated_at} / {len(data)}車種 {total}件</span>'
    )
    badge_pattern = re.compile(
        r'(class="hdr-title">)'
        r'(?:<span style="font-size:10px;color:#888;margin-left:8px;">.*?</span>)*'
    )
    html, n = badge_pattern.subn(lambda m: m.group(1) + badge, html, count=1)
    if n == 0:
        log.warning('class="hdr-title" が見つからずバッジを挿入できませんでした')

    # 出力
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(html, encoding="utf-8")
    log.info(f"出力完了: {args.out} ({len(html)//1024} KB)")

if __name__ == "__main__":
    main()
