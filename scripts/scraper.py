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
    {"key": "toyota|harrier",                "url": "toyota/harrier"},
    {"key": "toyota|land-cruiser-200",       "url": "toyota/land-cruiser-200"},
    {"key": "toyota|land-cruiser-100",       "url": "toyota/land-cruiser-100"},
    {"key": "toyota|land-cruiser-prado-150", "url": "toyota/land-cruiser-prado"},
    {"key": "toyota|alphard-30",             "url": "toyota/alphard"},
    {"key": "toyota|vellfire-30",            "url": "toyota/vellfire"},
    {"key": "toyota|prius-50",               "url": "toyota/prius-50"},
    {"key": "toyota|prius-41",               "url": "toyota/prius-40"},
    {"key": "toyota|aqua",                   "url": "toyota/aqua"},
    {"key": "toyota|rav4-50",                "url": "toyota/rav4"},
    {"key": "toyota|camry-70",               "url": "toyota/camry"},
    {"key": "toyota|corolla-axio",           "url": "toyota/corolla-axio"},
    {"key": "toyota|hiace-200",              "url": "toyota/hiace"},
    {"key": "toyota|highlander",             "url": "toyota/highlander"},
    {"key": "toyota|fortuner",               "url": "toyota/fortuner"},
    {"key": "toyota|hilux",                  "url": "toyota/hilux"},
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
    {"key": "lexus|lx-570",                  "url": "lexus/lx"},
    {"key": "lexus|gx-460",                  "url": "lexus/gx"},
    # RX: UNEGUI.MN側はガソリン/ハイブリッドの2URLしか存在しないため、
    # ここで取得したのち年式・タイトルで7区分（世代×グレード）に自動振り分けする
    {"key": "lexus|rx-gas",                  "url": "lexus/rx",     "rx_type": "gas"},
    {"key": "lexus|rx-hybrid",               "url": "lexus/rx-450", "rx_type": "hybrid"},
    {"key": "lexus|nx-az10",                 "url": "lexus/nx"},
    {"key": "lexus|es-axzh10",               "url": "lexus/es"},
    {"key": "hyundai|santa-fe-tm",           "url": "hyundai/santa-fe"},
    {"key": "hyundai|palisade",              "url": "hyundai/palisade"},
    {"key": "kia|sorento-mq4",               "url": "kia/sorento"},
    {"key": "kia|sportage-ql",               "url": "kia/sportage"},
    {"key": "bmw|x5-f15",                    "url": "bmw/x5"},
    {"key": "mercedes-benz|g-class-w463",    "url": "mercedes-benz/g-class"},
    {"key": "mercedes-benz|gle-w166",        "url": "mercedes-benz/gle"},
    {"key": "land-rover|discovery-4",        "url": "land-rover/discovery"},
    {"key": "land-rover|range-rover-l405",   "url": "land-rover/range-rover"},
    {"key": "volkswagen|tiguan-ad1",         "url": "volkswagen/tiguan"},
    {"key": "audi|q7-4m",                    "url": "audi/q7"},
    {"key": "audi|q5-fy",                    "url": "audi/q5"},
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
    t = text.upper()
    if any(w in t for w in ["4WD","AWD","ПОЛНЫЙ","4×4"]): return "4WD"
    if any(w in t for w in ["2WD","FWD","FF","FR","ПЕРЕДНИЙ"]): return "2WD"
    return "4WD"
 
def parse_color(text):
    cm = {"цагаан":"白","white":"白","хар":"黒","black":"黒","мөнгө":"銀",
          "silver":"銀","улаан":"赤","red":"赤","саарал":"グレー",
          "gray":"グレー","хөх":"青","blue":"青","ногоон":"緑","шар":"黄"}
    t = text.lower()
    for k,v in cm.items():
        if k in t: return v
    return "不明"
 
def classify_rx_key(rx_type, year, title=""):
    """RXの年式・タイトルから世代×グレード別のDBキーを判定する。
    UNEGUI.MN側は lexus/rx（ガソリン）と lexus/rx-450（ハイブリッド）の
    2カテゴリしか存在しないため、ここで7区分に振り分ける。
    世代の目安: AL10=～2015, AL20=2016～2022, AL30=2023～
    """
    t = (title or "").lower()
    if rx_type == "gas":
        if year <= 2015:
            return "lexus|rx-al10-gas"
        elif year <= 2022:
            return "lexus|rx-al20-gas"
        else:
            return "lexus|rx-al30-350"
    else:  # hybrid
        if year <= 2015:
            return "lexus|rx-al10-hybrid"
        elif year <= 2022:
            if any(w in t for w in ["450hl", "450h l", "7 suudal", "7-suudal", "7суудал", "долгион", "long"]):
                return "lexus|rx-al20-450hl"
            return "lexus|rx-al20-hybrid"
        else:
            if any(w in t for w in ["500h", "f sport", "fsport", "ф спорт"]):
                return "lexus|rx-al30-500h"
            return "lexus|rx-al30-350"
 
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
    # タイトル（RXの世代・グレード判定用、最終保存前に除去される）
    title_text = ""
    for sel in [".announcement-block__title", "[class*='title']", "a[itemprop='name']", "h3", "h4"]:
        el = card.select_one(sel)
        if el: title_text = el.get_text(" ", strip=True); break
 
    # 価格
    price_text = ""
    for sel in [".price-announcement",".announcement-pricing",
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
            "_title": title_text or full[:80]}
 
def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    results = []
    cards = []
    for sel in ["li.announcement-container",
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
                # RX: 年式・タイトルキーワードで世代×グレード別キーに自動振り分け
                for item in r:
                    sub_key = classify_rx_key(t["rx_type"], item["year"], item.pop("_title", ""))
                    db.setdefault(sub_key, []).append(item)
                log.info(f"  RX振り分け完了（元キー: {t['key']}）")
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
 
