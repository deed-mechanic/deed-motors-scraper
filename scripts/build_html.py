#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, re, sys, argparse, logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_template(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def format_price_db_js(data):
    lines = ["const PRICE_DB = {"]
    items = list(data.items())
    for idx, (key, records) in enumerate(items):
        is_last_key = (idx == len(items) - 1)
        lines.append(f'  "{key}":[')
        for ridx, rec in enumerate(records):
            is_last_rec = (ridx == len(records) - 1)
            line = (
                f'    {{year:{rec["year"]},drive:"{rec["drive"]}",'
                f'mileage:"{rec.get("mileage","不明")}",color:"{rec.get("color","不明")}",'
                f'import_year:{rec["import_year"]},price:{rec["price"]}}}'
            )
            if not is_last_rec:
                line += ","
            lines.append(line)
        lines.append("  ]" + ("," if not is_last_key else ""))
    lines.append("};")
    return "\n".join(lines)

def inject_price_db(html, price_db_js):
    pattern = re.compile(r"const PRICE_DB\s*=\s*\{.*?\};", re.DOTALL)
    match = pattern.search(html)
    if not match:
        log.error("PRICE_DB がHTMLに見つかりません")
        sys.exit(1)
    return html[:match.start()] + price_db_js + html[match.end():]

def merge_with_fallback(new_data, fallback_data):
    merged = {}
    fallback = fallback_data.get("data", {})
    for key in set(list(new_data.keys()) + list(fallback.keys())):
        if key in new_data and len(new_data[key]) >= 2:
            merged[key] = new_data[key]
        elif key in fallback:
            merged[key] = fallback[key]
            log.info(f"  フォールバック: {key}")
    return merged

def build(template_path, db_path, output_path, fallback_path=None):
    log.info("=== ビルド開始 ===")
    db_json     = load_json(db_path)
    new_data    = db_json.get("data", {})
    updated_at  = db_json.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    if fallback_path and Path(fallback_path).exists():
        merged = merge_with_fallback(new_data, load_json(fallback_path))
    else:
        merged = new_data

    total_r = sum(len(v) for v in merged.values())
    total_m = len(merged)
    log.info(f"データ: {total_m}車種 / {total_r}件")

    html = load_template(template_path)
    html = inject_price_db(html, format_price_db_js(merged))

    badge = (
        f'<span style="font-size:10px;color:#888;margin-left:8px;font-weight:400;">'
        f'データ更新: {updated_at} / {total_m}車種 {total_r}件</span>'
    )
    html = html.replace('class="hdr-title">', f'class="hdr-title">{badge}', 1)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"出力: {output_path} ({len(html.encode())//1024} KB)")
    log.info(f"=== 完了 ({updated_at}) ===")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default="templates/deed_motors_PC_v3_template.html")
    parser.add_argument("--db",       default="scripts/price_db.json")
    parser.add_argument("--fallback", default="scripts/price_db_fallback.json")
    parser.add_argument("--out",      default="output/deed_motors_PC_latest.html")
    args = parser.parse_args()

    if not Path(args.template).exists():
        log.error(f"テンプレートが見つかりません: {args.template}")
        sys.exit(1)
    if not Path(args.db).exists():
        log.error(f"DBが見つかりません: {args.db}")
        sys.exit(1)

    build(template_path=args.template, db_path=args.db,
          output_path=args.out,
          fallback_path=args.fallback if Path(args.fallback).exists() else None)
