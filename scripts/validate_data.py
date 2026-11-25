"""価格データの検証（公開前の最終チェック）。

背景: この市場価格は顧客への提示額の根拠になるため、誤ったデータが1件でも混ざると即損失につながる。
2026-11-24に「Palisade55件・GLE16件が実はLand Cruiser/Patrol等の検索結果だった」問題が
数日間見つからなかった反省から、取得後・公開前に機械的に矛盾を洗い出し、
疑わしい車種のデータは「前回の正常データ」に戻して公開する（誤った値を公開しない）。

使い方:
  python scripts/validate_data.py --db scripts/price_db.json --prev <前回のdb> [--report <出力先>]
終了コード: 0=異常なし / 4=疑わしい車種を前回データに戻した（dbを書き換えた） / 1=検証自体が失敗

検証内容
  [E] 誤りとみなして除外・差し戻すもの
    E1 レコードの構造異常（価格・年式の範囲外、駆動方式の値、必須項目欠落）→ そのレコードを削除
    E2 取得対象に設定した年式範囲(year_min/year_max)外のレコード → 削除
    E3 車種キーのメーカーと、広告タイトル(_fulltext)のメーカーが合わない（別車種の混入）→ その車種を差し戻し
    E4 別の車種キーと中身がほぼ同一（同じ検索結果を複数の車種に保存した疑い）→ 新しい方を差し戻し
    E5 前回から件数が激減（前回10件以上で40%未満）→ 差し戻し
  [W] 警告（公開はするが、ログと結果に残す）
    W1 中央値が前回から35%以上動いた車種   W2 同一車種・同年式で価格が大きく外れる広告
    W3 件数が前回の3倍以上                 W4 輸入年が生産年より前
    W5 件数が少ない車種(2〜5件)で、最高値が最安値の3倍以上
  W1は件数が少ない車種も対象（2026-11-26: 4件に減ったPajero V60が中央値20→50でも警告されなかったため）
"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

# キーのメーカー名 → 広告タイトルに現れうる表記
BRAND_ALIASES = {
    "mercedes-benz": ["mercedes", "benz"],
    "land-rover": ["land rover", "range rover", "discovery", "defender", "rover"],
    "ram": ["ram", "dodge"],
    "volkswagen": ["volkswagen", "vw"],
    "dongfeng": ["dongfeng", "forthing", "voyah", "fengshen", "dfsk", "ssangyong"],
    "mini": ["mini"],
    "alfa-romeo": ["alfa"],
    "rolls-royce": ["rolls"],
    "aston-martin": ["aston"],
    "gmc": ["gmc"],
}
VALID_DRIVE = {"4WD", "2WD", "不明"}
PRICE_MIN, PRICE_MAX = 1.0, 500.0
YEAR_MIN, YEAR_MAX = 1990, 2027
SMALL_N, SPREAD_RATIO = 5, 3.0  # W5: この件数以下で、最高値が最安値の何倍以上なら警告するか


def norm(s):
    return re.sub(r"[^a-z0-9а-яөү]", "", (s or "").lower())


def brand_ok(key, text):
    b = key.split("|")[0]
    cands = [b] + BRAND_ALIASES.get(b, [])
    t = (text or "").lower()
    tn = norm(t)
    return any(c in t or norm(c) in tn for c in cands)


def sig(x):
    return (x.get("year"), x.get("price"), x.get("mileage"), x.get("drive"), x.get("import_year"), x.get("wheel"))


def load_targets():
    """scraper.py の取得対象（年式範囲）を読む。読めなければ年式範囲の検証は省く"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import scraper  # noqa
        return {t["key"]: t for t in scraper.TARGETS}
    except Exception as e:  # pragma: no cover
        print(f"（取得対象を読めないため年式範囲の検証は省略: {e}）")
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--prev")
    ap.add_argument("--report")
    ap.add_argument("--no-fix", action="store_true", help="dbを書き換えず報告のみ")
    a = ap.parse_args()

    with open(a.db, encoding="utf-8-sig") as f:
        doc = json.load(f)
    data = doc["data"]
    prev = {}
    if a.prev and os.path.exists(a.prev):
        with open(a.prev, encoding="utf-8-sig") as f:
            prev = json.load(f).get("data", {})
    targets = load_targets()

    errors, warns = [], []          # (key, message)
    revert = {}                     # key -> 理由（差し戻す車種）
    dropped = defaultdict(int)      # key -> 削除レコード数

    # ── E1/E2: レコード単位 ──
    for k, v in list(data.items()):
        t = targets.get(k, {})
        ymin, ymax = t.get("year_min"), t.get("year_max")
        keep = []
        for x in v:
            why = None
            p, y = x.get("price"), x.get("year")
            if not isinstance(p, (int, float)) or not (PRICE_MIN <= p <= PRICE_MAX):
                why = f"価格が範囲外({p})"
            elif not isinstance(y, int) or not (YEAR_MIN <= y <= YEAR_MAX):
                why = f"年式が範囲外({y})"
            elif x.get("drive") not in VALID_DRIVE:
                why = f"駆動方式が不正({x.get('drive')})"
            elif (ymin is not None and y < ymin) or (ymax is not None and y > ymax):
                why = f"取得対象の年式範囲外({y} / {ymin}-{ymax})"
            if why:
                dropped[k] += 1
                errors.append((k, f"レコード削除: {why}"))
            else:
                keep.append(x)
        data[k] = keep

    # ── E3: メーカー不一致（別車種の混入） ──
    for k, v in data.items():
        withtxt = [x for x in v if x.get("_fulltext")]
        if len(withtxt) >= 3:
            miss = sum(1 for x in withtxt if not brand_ok(k, x["_fulltext"]))
            if miss / len(withtxt) > 0.2:
                revert[k] = f"広告タイトルのメーカーが{miss}/{len(withtxt)}件で一致しない（別車種の混入の疑い）"

    # ── E4: 他の車種キーと中身がほぼ同一 ──
    sigs = {k: {sig(x) for x in v} for k, v in data.items() if len(v) >= 5}
    keys = list(sigs)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a_, b_ = keys[i], keys[j]
            inter = len(sigs[a_] & sigs[b_])
            if inter / min(len(sigs[a_]), len(sigs[b_])) >= 0.5:
                # 前回の件数が少ない（新しく現れた）方を、同じ検索結果が混入した側とみなす
                bad = a_ if len(prev.get(a_, [])) <= len(prev.get(b_, [])) else b_
                revert.setdefault(bad, f"{a_} と {b_} の中身が{inter}件同一（同じ結果を複数車種に保存した疑い）")

    # ── E5/W1/W3: 前回との比較 ──
    for k, v in data.items():
        pv = prev.get(k)
        if not pv:
            continue
        n, m = len(v), len(pv)
        if _is_flagged_in_prev(k, prev):
            continue  # 前回データ自体が誤り（別車種の混入）だった場合は、件数の比較をしない
        if m >= 10 and n < m * 0.4:
            revert.setdefault(k, f"件数が前回{m}件→{n}件に激減")
        elif n >= 1:
            med_n = statistics.median(x["price"] for x in v)
            med_p = statistics.median(x["price"] for x in pv)
            if med_p > 0 and abs(med_n - med_p) / med_p >= 0.35:
                few = f"／件数{m}→{n}" if min(m, n) < 5 else ""
                warns.append((k, f"中央値が前回{med_p:.1f}→{med_n:.1f}（{(med_n - med_p) / med_p * 100:+.0f}%{few}）"))
        if m >= 5 and n >= m * 3:
            warns.append((k, f"件数が前回{m}件→{n}件に急増"))

    # ── W5: 件数が少ない車種のばらつき ──
    for k, v in data.items():
        if 2 <= len(v) <= SMALL_N:
            lo, hi = min(x["price"] for x in v), max(x["price"] for x in v)
            if hi >= lo * SPREAD_RATIO:
                prices = ", ".join(f"{x['year']}年式 {x['price']}" for x in sorted(v, key=lambda x: x["price"]))
                warns.append((k, f"件数が少なく価格のばらつきが大きい（{len(v)}件: {prices}）"))

    # ── W2/W4 ──
    for k, v in data.items():
        by_year = defaultdict(list)
        for x in v:
            by_year[x["year"]].append(x["price"])
            if x.get("import_year") and x["import_year"] < x["year"]:
                warns.append((k, f"輸入年{x['import_year']}が生産年{x['year']}より前（{x['price']}）"))
        if len(v) >= 6:
            med_all = statistics.median(x["price"] for x in v)
            for x in v:
                if x["price"] > med_all * 4 or x["price"] < med_all / 5:
                    warns.append((k, f"{x['year']}年式 {x['price']}（車種中央値{med_all:.1f}の大きな外れ値。入力ミスの疑い）"))

    # ── 差し戻し ──
    reverted = []
    for k, why in revert.items():
        if k in prev and prev[k] and not _is_flagged_in_prev(k, prev):
            data[k] = prev[k]
            reverted.append((k, why, "前回データに戻した"))
        else:
            data.pop(k, None)
            reverted.append((k, why, "前回に正常データが無いため除外"))

    lines = []
    lines.append(f"検証結果: 差し戻し/除外 {len(reverted)}車種 / レコード削除 {sum(dropped.values())}件 / 警告 {len(warns)}件")
    for k, why, act in reverted:
        lines.append(f"  [E] {k}: {why} → {act}")
    for k, msg in errors:
        lines.append(f"  [E] {k}: {msg}")
    for k, msg in warns[:60]:
        lines.append(f"  [W] {k}: {msg}")
    if len(warns) > 60:
        lines.append(f"  [W] ...ほか{len(warns) - 60}件")
    text = "\n".join(lines)
    print(text)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")

    changed = bool(reverted) or bool(dropped)
    if changed and not a.no_fix:
        doc["data"] = data
        doc["total_models"] = len(data)
        doc["total_records"] = sum(len(v) for v in data.values())
        with open(a.db, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"検証結果を反映して保存: {doc['total_models']}車種 {doc['total_records']}件")
    sys.exit(4 if (reverted or dropped) else 0)


def _is_flagged_in_prev(k, prev):
    """前回データ自体がメーカー不一致なら、戻さずに除外する（誤データを引き継がない）"""
    v = prev.get(k) or []
    withtxt = [x for x in v if x.get("_fulltext")]
    if len(withtxt) >= 3:
        miss = sum(1 for x in withtxt if not brand_ok(k, x["_fulltext"]))
        return miss / len(withtxt) > 0.2
    return False


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"検証スクリプトが失敗しました: {e}")
        sys.exit(1)
