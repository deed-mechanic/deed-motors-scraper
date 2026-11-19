#!/usr/bin/env python3
"""メニュー(MODELS_MAP) / 取得対象(TARGETS) / 取得データ(price_db.json) の整合チェック。

使い方: python scripts/check_consistency.py [--db scripts/price_db.json] [--old 前回のprice_db.json]
- メニューにあるが取得対象に無い車種 … 画面で選べるのに常に「対象無し」になる
- 取得対象にあるがメニューに無い車種 … 取得してもツールから使えない
- 前回(--old)から消えた車種 … UNEGUI.MN側のURL変更・出品0件の疑い
終了コードは常に0（確認用。日次実行を止めない）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_json(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def menu_keys(template):
    t = Path(template).read_text(encoding="utf-8")
    start = t.index("const MODELS_MAP = {")
    keys, cur = [], None
    for line in t[start:].splitlines()[1:]:
        if line.startswith("};"):
            break
        m = re.match(r'\s{2}"?([\w-]+)"?:\[', line)
        if m:
            cur = m.group(1)
            continue
        m = re.search(r's:"([^"]+)"', line)
        if m and cur:
            keys.append(f"{cur}|{m.group(1)}")
    return keys


def target_keys():
    sys.path.insert(0, str(ROOT / "scripts"))
    import scraper
    return [t["key"] for t in scraper.TARGETS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "scripts" / "price_db.json"))
    ap.add_argument("--old")
    ap.add_argument("--template", default=str(ROOT / "templates" / "deed_motors_PC_v3_template.html"))
    a = ap.parse_args()

    db = load_json(a.db)["data"]
    menu = menu_keys(a.template)
    targets = target_keys()
    # 取得後に世代・グレード等へ振り分けられるキーは、取得対象側のキーと一致しないため、
    # 「データがある＝取得できている」とみなして判定する
    no_source = [k for k in menu if k not in targets and k not in db]
    no_data = [k for k in menu if k not in db]
    not_in_menu = [k for k in db if k not in menu]

    print(f"メニュー {len(menu)}車種 / 取得対象 {len(targets)} / データ {len(db)}車種")
    print(f"\n[A] メニューにあるがデータが無い（画面では「対象無し」）: {len(no_data)}")
    for k in no_data:
        print("   -", k, "（取得対象にも無い）" if k in no_source else "（取得対象はあるが現在0件）")
    print(f"\n[B] データがあるがメニューに無い（ツールから選べない）: {len(not_in_menu)}")
    for k in not_in_menu:
        print("   -", k, f"{len(db[k])}件")
    # 駆動方式の判定状況（詳細ページ取得は1晩あたり時間枠があり、数晩かけて埋まる。進み具合の確認用）
    tot = {"4WD": 0, "2WD": 0, "不明": 0}
    for v in db.values():
        for r in v:
            tot[r.get("drive", "不明")] = tot.get(r.get("drive", "不明"), 0) + 1
    n = sum(tot.values()) or 1
    print(f"\n[D] 駆動方式: 4WD {tot['4WD']} / 2WD {tot['2WD']} / 不明 {tot['不明']}（不明率 {tot['不明'] / n:.0%}）")
    unk = sorted(((k, len(v), sum(1 for r in v if r.get("drive", "不明") == "不明")) for k, v in db.items() if len(v) >= 10),
                 key=lambda x: -x[2] / x[1])
    print("    不明率の高い車種（10件以上、上位8）:", [f"{k} {u}/{n_}" for k, n_, u in unk[:8]])
    if a.old and Path(a.old).exists():
        old = load_json(a.old)["data"]
        gone = [k for k in old if k not in db]
        new = [k for k in db if k not in old]
        print(f"\n[C] 前回から消えた車種: {len(gone)}", gone)
        print(f"    前回に無かった車種: {len(new)}", new)
        drops = [(k, len(old[k]), len(db[k])) for k in db if k in old and len(old[k]) >= 6 and len(db[k]) < len(old[k]) * 0.5]
        print(f"    件数が半分未満に減った車種: {len(drops)}", drops)


if __name__ == "__main__":
    main()
