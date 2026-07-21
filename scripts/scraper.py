#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, time, re, sys, argparse, logging
from datetime import datetime

try:
    import cloudscraper
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install cloudscraper beautifulsoup4 lxml")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_URL = "https://www.unegui.mn"
REQUEST_DELAY = 3.0
MAX_PAGES = 3

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

# 正しいURL構造: /avto-mashin/-avtomashin-zarna/メーカー/車種/
TARGETS = [
    {"key": "toyota|c-hr",                "url": "toyota/chr", "chr_drive_fix": True},
    # Harrier: UNEGUI.MN側は toyota/harrier の1URLに60系・80系が混在しているため、
    # ここで取得したのち年式・タイトルで60系ガソリン/60系HV/80系の3区分に自動振り分けする
    {"key": "toyota|harrier",                "url": "toyota/harrier", "harrier_split": True},
    {"key": "toyota|land-cruiser-200", "url": "toyota/land-cruiser-200", "year_min": 2007, "year_max": 2021},
    {"key": "toyota|land-cruiser-100", "url": "toyota/land-cruiser-100", "year_min": 1998, "year_max": 2007},
    {"key": "toyota|land-cruiser-prado-150", "url": "toyota/land-cruiser-prado-150", "year_min": 2009, "year_max": 2024},
    {"key": "toyota|land-cruiser-prado-120", "url": "toyota/land-cruiser-prado-120", "year_min": 2002, "year_max": 2009},
    {"key": "toyota|land-cruiser-prado-250", "url": "toyota/land-cruiser-prado-250", "year_min": 2024},
    {"key": "toyota|alphard-30", "url": "toyota/alphard", "alphard_split": True},
    {"key": "toyota|vellfire-30", "url": "toyota/vellfire", "vellfire_split": True},
    {"key": "toyota|prius-30", "url": "toyota/prius-30", "year_min": 2009, "year_max": 2015},
    {"key": "toyota|prius-60", "url": "toyota/prius-60", "year_min": 2023},
    {"key": "toyota|prius-41", "url": "toyota/prius-40", "year_min": 2009, "year_max": 2015},
    {"key": "toyota|aqua", "url": "toyota/aqua", "year_min": 2011},
    {"key": "toyota|rav4-50", "url": "toyota/rav4", "rav4_split": True},
    {"key": "toyota|camry-70", "url": "toyota/camry", "camry_split": True},
    {"key": "toyota|corolla-axio", "url": "toyota/corolla", "year_min": 2006, "year_max": 2019},
    {"key": "toyota|hiace-200", "url": "toyota/hiace", "year_min": 2004},
    {"key": "toyota|highlander", "url": "toyota/highlander", "year_min": 2013},
    {"key": "toyota|fortuner", "url": "toyota/fortuner", "year_min": 2015},
    {"key": "toyota|hilux", "url": "toyota/hilux", "year_min": 2015},
    {"key": "nissan|x-trail-t32",            "url": "nissan/x-trail"},
    {"key": "nissan|patrol-y62",             "url": "nissan/patrol"},
    {"key": "nissan|elgrand-e52",            "url": "nissan/elgrand"},
    {"key": "nissan|serena-c27",             "url": "nissan/serena"},
    {"key": "mitsubishi|pajero-v80",         "url": "mitsubishi/pajero"},
    {"key": "mitsubishi|outlander-gf",       "url": "mitsubishi/outlander"},
    {"key": "mitsubishi|delica-d5",          "url": "mitsubishi/delica-d5"},
    {"key": "honda|cr-v-5",                  "url": "honda/cr-v"},
    {"key": "honda|odyssey",                 "url": "honda/odyssey"},
    {"key": "subaru|forester-sj",            "url": "subaru/forester"},
    {"key": "subaru|outback-bs",             "url": "subaru/outback"},
    {"key": "suzuki|jimny-jb64",             "url": "suzuki/jimny"},
    {"key": "lexus|lx-600", "url": "lexus/lx-600", "year_min": 2021},
    {"key": "lexus|lx-570", "url": "lexus/lx-570", "year_min": 2007, "year_max": 2021},
    {"key": "lexus|lx-470", "url": "lexus/lx-470", "year_min": 1998, "year_max": 2007},
    {"key": "lexus|gx-460", "url": "lexus/gx", "gx_split": True},
    # RX: UNEGUI.MN側はガソリン/ハイブリッドの2URLしか存在しないため、
    # ここで取得したのち年式・タイトルで7区分（世代×グレード）に自動振り分けする
    {"key": "lexus|rx-gas",                  "url": "lexus/rx",     "rx_type": "gas"},
    {"key": "lexus|rx-hybrid",               "url": "lexus/rx-450", "rx_type": "hybrid"},
    {"key": "lexus|nx-az10",                 "url": "lexus/nx", "nx_split": True},
    {"key": "lexus|es-axzh10",               "url": "lexus/es", "es_split": True},
    {"key": "lexus|is-300-xe30",             "url": "lexus/is", "is_split": True},
    {"key": "lexus|gs-350",                  "url": "lexus/gs", "gs_split": True},
    {"key": "lexus|ls-500",                  "url": "lexus/ls", "ls_split": True},
    {"key": "lexus|ct-200h",                 "url": "lexus/ct", "year_min": 2011, "year_max": 2017},
    {"key": "lexus|hs-250h",                 "url": "lexus/hs", "year_min": 2009, "year_max": 2018},
    {"key": "hyundai|santa-fe-tm",           "url": "hyundai/santa-fe"},
    {"key": "hyundai|palisade",              "url": "hyundai/palisade"},
    {"key": "kia|sorento-mq4",               "url": "kia/sorento"},
    {"key": "kia|sportage-ql",               "url": "kia/sportage"},
    {"key": "bmw|x5-f15", "url": "bmw/x5", "year_min": 2013, "year_max": 2018},
    {"key": "mercedes-benz|g-class-w463",    "url": "mercedes-benz/g-class", "year_min": 2018},
    {"key": "mercedes-benz|gle-w166",        "url": "mercedes-benz/gle", "year_min": 2015, "year_max": 2018},
    {"key": "land-rover|discovery-4",        "url": "land-rover/discovery", "year_min": 2009, "year_max": 2016},
    {"key": "land-rover|range-rover-l405",   "url": "land-rover/range-rover", "year_min": 2012, "year_max": 2022},
    {"key": "volkswagen|tiguan-ad1", "url": "volkswagen/tiguan", "year_min": 2016},
    {"key": "audi|q7-4m", "url": "audi/q7", "year_min": 2015},
    {"key": "audi|q5-fy", "url": "audi/q5", "year_min": 2017},
    {"key": "mazda|cx-5-kf",                 "url": "mazda/cx-5"},
]

def build_url(path_suffix, page=1):
    base = f"{BASE_URL}/avto-mashin/-avtomashin-zarna/{path_suffix}/"
    return base if page == 1 else f"{base}?page={page}"

def parse_price(text):
    if not text: return None
    text = text.strip().replace("\xa0"," ").replace(",","")
    m = re.search(r"([\d\.]+)\s*сая", text, re.IGNORECASE)
    if m: return round(float(m.group(1)), 1)
    m = re.search(r"([\d\.]+)\s*тэрбум", text, re.IGNORECASE)
    if m: return round(float(m.group(1))*1000, 1)
    m = re.search(r"(\d{6,})", text)
    if m: return round(int(m.group(1))/1_000_000, 1)
    return None

def parse_year(text):
    # 「2018/2022」形式（生産年/輸入年）→ 最初の年が生産年
    m = re.search(r"\b(19[89]\d|20[012]\d)(?:/20\d\d)?\b", text)
    return int(m.group(1)) if m else None

def parse_drive(text):
    # 記載がない場合は「4WD」と決め打ちせず「不明」とする
    # （UNEGUI.MNのカード要約には駆動方式が書かれていない出品が多く、
    #   特にハイブリッド車は本来2WD(FF)のみのモデルが多いため、断定は誤情報になる）
    t = text.upper()
    if any(w in t for w in ["4WD","AWD","ПОЛНЫЙ","4×4"]): return "4WD"
    if any(w in t for w in ["2WD","FWD","FF","FR","ПЕРЕДНИЙ"]): return "2WD"
    return "不明"

def parse_color(text):
    cm = {"цагаан":"白","white":"白","хар":"黒","black":"黒","мөнгө":"銀",
          "silver":"銀","улаан":"赤","red":"赤","саарал":"グレー",
          "gray":"グレー","хөх":"青","blue":"青","ногоон":"緑","шар":"黄"}
    t = text.lower()
    for k,v in cm.items():
        if k in t: return v
    return "不明"

def classify_rx_key(rx_type, year, title=""):
    """RXの年式からドロップダウン（MODELS_MAP）のスラッグに一致するキーを判定する。
    UNEGUI.MN側は lexus/rx（ガソリン）と lexus/rx-450（ハイブリッド）の
    2カテゴリしか存在しないため、ここで世代・グレード別に振り分ける。
    重要: 生成するキーは index.html の MODELS_MAP 内スラッグと完全一致させること。
    （以前は独自の命名（rx-al10-gas等）を使っており、画面側と一致せず
      検索結果が常に0件になる不具合があったため、スラッグ基準に統一した）
    世代の目安: AL10=～2015, AL20=2016～2022, AL30=2023～
    """
    if year < 2008:
        return None  # AL10より前（ドロップダウンに存在しない世代）は除外
    if rx_type == "gas":
        if year <= 2015:
            return "lexus|rx-350-al10"
        elif year <= 2022:
            return "lexus|rx-350-al20-gas"
        else:
            return "lexus|rx-350-al20"  # 5代目(2022-)ガソリン。MODELS_MAPのスラッグ表記に合わせる
    else:  # hybrid
        if year <= 2015:
            return "lexus|rx-450h-al10"
        elif year <= 2022:
            return "lexus|rx-450h-al20"
        else:
            return "lexus|rx-500h"  # 5代目(2022-) HV/PHEV

def classify_harrier_key(year, title=""):
    """Harrierの年式・カード全文から60系（ACU/MCU）ガソリン/HV・80系ガソリン/HVを判定する。
    UNEGUI.MN側は toyota/harrier の1URLに全世代混在のため、ここで振り分ける。
    世代の目安: 60系=2003-2013年、80系=2014年以降。
    """
    t = (title or "").lower()
    hv_words = ["hybrid", "хайбрид", "гибрид", "mcu"]
    is_hybrid = any(w in t for w in hv_words)
    if year <= 2013:
        return "toyota|harrier-60-hv" if is_hybrid else "toyota|harrier-60-gas"
    return "toyota|harrier-80-hv" if is_hybrid else "toyota|harrier-80-gas"

def fix_chr_drive(item):
    """C-HRの駆動方式を実態に即して補正する。
    1.8L(NAガソリン)・ハイブリッドはFF(2WD)のみの設定のため、
    エンジン表記・ハイブリッド表記が確認できれば2WDと確定させる。
    1.2Lターボのみ2WD/4WD両方の設定があるため、そちらは実際の検出結果（不明含む）をそのまま使う。
    """
    t = (item.get("_fulltext") or "").lower()
    if "1.8" in t or "хайбрид" in t or "hybrid" in t:
        item["drive"] = "2WD"
    return item

def classify_nx_key(year, title=""):
    """NXの年式・ハイブリッド判定からMODELS_MAPのスラッグに一致するキーを判定する。
    UNEGUI.MN側は lexus/nx の1URLに全世代・全グレードが混在しているため、
    AZ10(初代 2014-2021)/AZ20(2代目 2021-)、ガソリン/HVで振り分ける。
    PHEV(NX450h+)は判別材料が乏しいため、まずはHV(NX350h)に含める。
    """
    t = (title or "").lower()
    is_hybrid = "хайбрид" in t or "hybrid" in t
    if year <= 2020:
        return "lexus|nx-300h-az10" if is_hybrid else "lexus|nx-300-az10"
    else:
        return "lexus|nx-350h-az20" if is_hybrid else "lexus|nx-350-az20"

def classify_es_key(year, title=""):
    """ESのハイブリッド判定からMODELS_MAPのスラッグに一致するキーを判定する。
    UNEGUI.MN側は lexus/es の1URLに旧型(6代目以前)も混在しているため、
    MODELS_MAPに存在する7代目(AXZH10, 2018-)以外は除外する（Noneを返す）。
    """
    if year < 2018:
        return None
    t = (title or "").lower()
    is_hybrid = "хайбрид" in t or "hybrid" in t
    return "lexus|es-300h" if is_hybrid else "lexus|es-250"

def classify_gx_key(year, title=""):
    """GXの年式からMODELS_MAPのスラッグに一致するキーを判定する。
    UNEGUI.MN側は lexus/gx の1URLに全世代混在。専用URL(gx-460/gx-550)は存在しないため年式で振り分ける。
    """
    if year < 2009:
        return "lexus|gx-470"
    elif year < 2023:
        return "lexus|gx-460"
    else:
        return "lexus|gx-550"

def classify_is_key(year, title=""):
    """ISの年式・ハイブリッド判定からMODELS_MAPのスラッグに一致するキーを判定する。
    XE20(2代目 2005-2013)はガソリンのみ、XE30(3代目 2013-)はガソリン/HV。
    """
    t = (title or "").lower()
    if year < 2013:
        return "lexus|is-250-xe20"
    is_hybrid = "хайбрид" in t or "hybrid" in t
    return "lexus|is-300h-xe30" if is_hybrid else "lexus|is-300-xe30"

def classify_gs_key(year, title=""):
    """GSの年式・ハイブリッド判定からMODELS_MAPのスラッグに一致するキーを判定する。
    GRS190(3代目 2005-2012)はガソリンのみ、AWL10/GRL10(4代目 2012-)はガソリン/HV。
    """
    t = (title or "").lower()
    if year < 2012:
        return "lexus|gs-350-grs190"
    is_hybrid = "хайбрид" in t or "hybrid" in t
    return "lexus|gs-300h" if is_hybrid else "lexus|gs-350"

def classify_ls_key(year, title=""):
    """LSの年式・ハイブリッド判定からMODELS_MAPのスラッグに一致するキーを判定する。
    UVF45(2006-2017)はHV(LS600h)のみ、VXFA50(2017-)はガソリン/HV。
    """
    t = (title or "").lower()
    if year < 2017:
        return "lexus|ls-600h"
    is_hybrid = "хайбрид" in t or "hybrid" in t
    return "lexus|ls-500h" if is_hybrid else "lexus|ls-500"

def classify_alphard_key(year, title=""):
    """Alphardの年式からMODELS_MAPのスラッグ（20系/30系/40系）に振り分ける。
    UNEGUI.MN側は toyota/alphard の1URLに全世代混在。
    """
    if year < 2015:
        return "toyota|alphard-20"
    elif year < 2023:
        return "toyota|alphard-30"
    else:
        return "toyota|alphard-40"

def classify_vellfire_key(year, title=""):
    """Vellfireの年式からMODELS_MAPのスラッグ（20系/30系/40系）に振り分ける。
    UNEGUI.MN側は toyota/vellfire の1URLに全世代混在。
    """
    if year < 2015:
        return "toyota|vellfire-20"
    elif year < 2023:
        return "toyota|vellfire-30"
    else:
        return "toyota|vellfire-40"

def classify_camry_key(year, title=""):
    """Camryの年式からMODELS_MAPのスラッグ（50系/70系）に振り分ける。
    UNEGUI.MN側は toyota/camry の1URLに全世代混在。
    """
    return "toyota|camry-50" if year < 2017 else "toyota|camry-70"

def classify_rav4_key(year, title=""):
    """RAV4の年式からMODELS_MAPのスラッグ（40系/50系）に振り分ける。
    UNEGUI.MN側は toyota/rav4 の1URLに全世代混在。
    """
    return "toyota|rav4-40" if year < 2018 else "toyota|rav4-50"

def fetch(url, retries=3):
    for i in range(retries):
        try:
            resp = scraper.get(url, timeout=30)
            log.info(f"  HTTP {resp.status_code} ({len(resp.text)} chars): {url}")
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 404:
                log.warning(f"  404 — URLが存在しません")
                return None
            log.warning(f"  ステータス {resp.status_code}")
        except Exception as e:
            log.warning(f"  取得失敗({i+1}/{retries}): {e}")
        if i < retries-1: time.sleep(REQUEST_DELAY*(i+1))
    return None

def parse_card(card):
    # タイトル（RX・Harrierの世代・グレード判定用、最終保存前に除去される）
    # 注意: UNEGUI.MN現行サイトの価格要素は class="advert__content-price _not-title" のように
    # "title"という文字列を含むため、汎用フォールバック [class*='title'] だけだと価格要素を
    # 誤って拾ってしまう。実際のタイトル要素 .advert__content-title を最優先で試す。
    title_text = ""
    for sel in [".advert__content-title", ".advert-grid__content-title", ".announcement-block__title",
                "a[itemprop='name']", "h3", "h4", "[class*='title']"]:
        el = card.select_one(sel)
        if el: title_text = el.get_text(" ", strip=True); break

    # 価格（UNEGUI.MN現行サイトは .advert__content-price）
    price_text = ""
    for sel in [".advert__content-price", ".advert-grid__content-price", ".price-announcement",".announcement-pricing",
                "[class*='price']",".cost","[class*='cost']"]:
        el = card.select_one(sel)
        if el: price_text = el.get_text(" ", strip=True); break
    if not price_text:
        # テキスト全体から「сая ₮」を探す
        price_text = card.get_text(" ")
    price = parse_price(price_text)
    if not price or price < 1.0 or price > 500.0: return None

    full = card.get_text(" ")

    # 年（「2018/2022」形式）
    m = re.search(r"\b(19[89]\d|20[012]\d)(?:/20\d\d)?\b", full)
    year = int(m.group(1)) if m else None
    if not year: return None

    drive = parse_drive(full)

    mileage = "不明"
    m2 = re.search(r"([\d,]+)\s*(?:км|km)", full, re.IGNORECASE)
    if m2: mileage = f"{int(m2.group(1).replace(',','')):,} km"

    return {"year":year,"drive":drive,"mileage":mileage,
            "color":parse_color(full),
            "import_year":datetime.now().year,
            "price":round(price,1),
            "_title": title_text or full[:80],
            "_fulltext": full}

def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    results = []
    cards = []
    for sel in ["div.advert.js-item-listing",
                "div.advert",
                "div.advert-grid",
                "li.announcement-container",
                "div.announcement-block",
                "div[class*='announcement']",
                "li[class*='announcement']",
                "article[class*='announcement']"]:
        cards = soup.select(sel)
        if cards:
            log.info(f"  セレクタ '{sel}' → {len(cards)}件")
            break
    if not cards:
        log.warning(f"  カード未検出 — タイトル: {soup.title.string if soup.title else 'なし'}")
        # デバッグ用：主要クラス名を出力
        from collections import Counter
        cls_counter = Counter()
        for el in soup.find_all(True):
            for c in el.get("class",[]):
                cls_counter[c] += 1
        log.info(f"  主要クラス: {cls_counter.most_common(10)}")
        return results
    for card in cards:
        try:
            item = parse_card(card)
            if item: results.append(item)
        except Exception as e:
            log.debug(f"  カードエラー: {e}")
    return results

def has_next(html, page):
    soup = BeautifulSoup(html, "lxml")
    # UNEGUI.MN現行サイトの「次のページ」リンク（例: <a class="number-list-next js-page-filter ..." href="...?page=2">）
    next_link = soup.select_one("a.number-list-next, a.js-page-filter[href*='page=']")
    if next_link:
        href = next_link.get("href", "")
        m = re.search(r"page=(\d+)", href)
        if m:
            return int(m.group(1)) > page
        return True
    # フォールバック（旧セレクタ／別レイアウト対策）
    for sel in [".pagination","[class*='pagination']","nav.pager","[class*='pager']"]:
        pager = soup.select_one(sel)
        if pager:
            for a in pager.find_all("a"):
                t = a.get_text(strip=True)
                try:
                    if int(t) > page: return True
                except ValueError:
                    if any(w in t.lower() for w in ["дараа","next",">"]): return True
    return False

def scrape_one(target):
    key = target["key"]
    path = target["url"]
    log.info(f"\n▶ [{key}]")
    results, seen = [], set()
    for page in range(1, MAX_PAGES+1):
        url = build_url(path, page)
        html = fetch(url)
        if not html: break
        items = parse_page(html)
        log.info(f"  p{page}: {len(items)}件パース")
        for item in items:
            sig = (item["year"],item["drive"],item["price"])
            if sig not in seen: seen.add(sig); results.append(item)
        if not has_next(html, page): break
        time.sleep(REQUEST_DELAY)
    # 年式範囲フィルタ（表示ラベルの世代範囲と実データの食い違いを防ぐ）
    ymin = target.get("year_min")
    ymax = target.get("year_max")
    if ymin is not None or ymax is not None:
        before = len(results)
        results = [r for r in results if (ymin is None or r["year"] >= ymin) and (ymax is None or r["year"] <= ymax)]
        skipped = before - len(results)
        if skipped:
            log.info(f"  [{key}] 年式範囲外を除外: {skipped}件（範囲: {ymin}-{ymax}）")
    log.info(f"  [{key}] 計{len(results)}件")
    return results

def save(db, path="scripts/price_db.json"):
    out = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "source": "unegui.mn",
           "total_records": sum(len(v) for v in db.values()),
           "total_models": len(db), "data": db}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log.info(f"保存: {path} ({out['total_records']}件)")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--output", default="scripts/price_db.json")
    args = parser.parse_args()
    targets = [t for t in TARGETS if t["key"]=="toyota|harrier"] if args.test else TARGETS
    db = {}
    for i,t in enumerate(targets,1):
        log.info(f"[{i}/{len(targets)}]")
        try:
            r = scrape_one(t)
            if not r:
                continue
            if "rx_type" in t:
                # RX: 年式・タイトルキーワードで世代×グレード別キーに自動振り分け（対象外年式はNoneで除外）
                for item in r:
                    sub_key = classify_rx_key(t["rx_type"], item["year"], item.pop("_title", ""))
                    if sub_key is None:
                        continue
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  RX振り分け完了（元キー: {t['key']}）")
            elif t.get("harrier_split"):
                # Harrier: 年式・カード全文キーワードで60系ガソリン/60系HV/80系に自動振り分け
                for item in r:
                    item.pop("_title", None)
                    sub_key = classify_harrier_key(item["year"], item.pop("_fulltext", ""))
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  Harrier振り分け完了（元キー: {t['key']}）")
            elif t.get("camry_split"):
                for item in r:
                    item.pop("_title", None); item.pop("_fulltext", None)
                    sub_key = classify_camry_key(item["year"])
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  Camry振り分け完了（元キー: {t['key']}）")
            elif t.get("rav4_split"):
                for item in r:
                    item.pop("_title", None); item.pop("_fulltext", None)
                    sub_key = classify_rav4_key(item["year"])
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  RAV4振り分け完了（元キー: {t['key']}）")
            elif t.get("alphard_split"):
                for item in r:
                    item.pop("_title", None); item.pop("_fulltext", None)
                    sub_key = classify_alphard_key(item["year"])
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  Alphard振り分け完了（元キー: {t['key']}）")
            elif t.get("vellfire_split"):
                for item in r:
                    item.pop("_title", None); item.pop("_fulltext", None)
                    sub_key = classify_vellfire_key(item["year"])
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  Vellfire振り分け完了（元キー: {t['key']}）")
            elif t.get("gx_split"):
                for item in r:
                    sub_key = classify_gx_key(item["year"], item.pop("_title", ""))
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  GX振り分け完了（元キー: {t['key']}）")
            elif t.get("is_split"):
                for item in r:
                    item.pop("_title", None)
                    sub_key = classify_is_key(item["year"], item.pop("_fulltext", ""))
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  IS振り分け完了（元キー: {t['key']}）")
            elif t.get("gs_split"):
                for item in r:
                    item.pop("_title", None)
                    sub_key = classify_gs_key(item["year"], item.pop("_fulltext", ""))
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  GS振り分け完了（元キー: {t['key']}）")
            elif t.get("ls_split"):
                for item in r:
                    item.pop("_title", None)
                    sub_key = classify_ls_key(item["year"], item.pop("_fulltext", ""))
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  LS振り分け完了（元キー: {t['key']}）")
            elif t.get("nx_split"):
                # NX: 世代(AZ10/AZ20)×ガソリン/HVで振り分け
                for item in r:
                    item.pop("_title", None)
                    sub_key = classify_nx_key(item["year"], item.pop("_fulltext", ""))
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  NX振り分け完了（元キー: {t['key']}）")
            elif t.get("es_split"):
                # ES: 7代目(2018-)のみ対象、ガソリン/HVで振り分け（旧型は除外）
                excluded = 0
                for item in r:
                    item.pop("_title", None)
                    fulltext = item.pop("_fulltext", "")
                    sub_key = classify_es_key(item["year"], fulltext)
                    if sub_key is None:
                        excluded += 1
                        continue
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  ES振り分け完了（元キー: {t['key']}、旧型除外: {excluded}件）")
            elif t.get("chr_drive_fix"):
                # C-HR: 1.8L/HVは2WD確定、1.2Lは検出結果のまま
                for item in r:
                    item.pop("_title", None)
                    fix_chr_drive(item)
                    item.pop("_fulltext", None)
                db[t["key"]] = r
            else:
                for item in r:
                    item.pop("_title", None)
                db[t["key"]] = r
        except Exception as e:
            log.error(f"エラー: {e}")
        if i < len(targets): time.sleep(REQUEST_DELAY*2)
    save(db, args.output)

if __name__ == "__main__":
    main()
