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

# cloudscraper でCloudflare回避
scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

TARGETS = [
    {"key": "toyota|harrier", "search": "Harrier", "brand": "Toyota"},
    {"key": "toyota|harrier-60", "search": "Harrier ACU MCU", "brand": "Toyota"},
    {"key": "toyota|land-cruiser-200", "search": "Land Cruiser 200", "brand": "Toyota"},
    {"key": "toyota|land-cruiser-100", "search": "Land Cruiser 100", "brand": "Toyota"},
    {"key": "toyota|land-cruiser-prado-150", "search": "Prado 150", "brand": "Toyota"},
    {"key": "toyota|alphard-30", "search": "Alphard", "brand": "Toyota"},
    {"key": "toyota|vellfire-30", "search": "Vellfire", "brand": "Toyota"},
    {"key": "toyota|prius-50", "search": "Prius 50", "brand": "Toyota"},
    {"key": "toyota|prius-41", "search": "Prius 41", "brand": "Toyota"},
    {"key": "toyota|aqua", "search": "Aqua", "brand": "Toyota"},
    {"key": "toyota|rav4-50", "search": "RAV4", "brand": "Toyota"},
    {"key": "toyota|camry-70", "search": "Camry", "brand": "Toyota"},
    {"key": "toyota|corolla-axio", "search": "Corolla Axio", "brand": "Toyota"},
    {"key": "toyota|hiace-200", "search": "Hiace", "brand": "Toyota"},
    {"key": "toyota|highlander", "search": "Highlander", "brand": "Toyota"},
    {"key": "toyota|fortuner", "search": "Fortuner", "brand": "Toyota"},
    {"key": "toyota|hilux", "search": "Hilux", "brand": "Toyota"},
    {"key": "nissan|x-trail-t32", "search": "X-Trail T32", "brand": "Nissan"},
    {"key": "nissan|x-trail-t31", "search": "X-Trail T31", "brand": "Nissan"},
    {"key": "nissan|patrol-y62", "search": "Patrol Y62", "brand": "Nissan"},
    {"key": "nissan|patrol-y61", "search": "Patrol Y61", "brand": "Nissan"},
    {"key": "nissan|elgrand-e52", "search": "Elgrand", "brand": "Nissan"},
    {"key": "nissan|serena-c27", "search": "Serena", "brand": "Nissan"},
    {"key": "mitsubishi|pajero-v80", "search": "Pajero V80", "brand": "Mitsubishi"},
    {"key": "mitsubishi|pajero-v60", "search": "Pajero V60", "brand": "Mitsubishi"},
    {"key": "mitsubishi|outlander-gf", "search": "Outlander", "brand": "Mitsubishi"},
    {"key": "mitsubishi|delica-d5", "search": "Delica", "brand": "Mitsubishi"},
    {"key": "honda|cr-v-5", "search": "CR-V", "brand": "Honda"},
    {"key": "honda|odyssey", "search": "Odyssey", "brand": "Honda"},
    {"key": "subaru|forester-sj", "search": "Forester", "brand": "Subaru"},
    {"key": "subaru|outback-bs", "search": "Outback", "brand": "Subaru"},
    {"key": "suzuki|jimny-jb64", "search": "Jimny JB64", "brand": "Suzuki"},
    {"key": "suzuki|jimny-jb23", "search": "Jimny JB23", "brand": "Suzuki"},
    {"key": "lexus|lx-570", "search": "LX570", "brand": "Lexus"},
    {"key": "lexus|lx-470", "search": "LX470", "brand": "Lexus"},
    {"key": "lexus|gx-460", "search": "GX460", "brand": "Lexus"},
    {"key": "lexus|gx-470", "search": "GX470", "brand": "Lexus"},
    {"key": "lexus|rx-al20", "search": "RX 200 300", "brand": "Lexus"},
    {"key": "lexus|rx450h", "search": "RX450h", "brand": "Lexus"},
    {"key": "lexus|nx-az10", "search": "NX", "brand": "Lexus"},
    {"key": "lexus|es-axzh10", "search": "ES", "brand": "Lexus"},
    {"key": "hyundai|santa-fe-tm", "search": "Santa Fe", "brand": "Hyundai"},
    {"key": "hyundai|palisade", "search": "Palisade", "brand": "Hyundai"},
    {"key": "kia|sorento-mq4", "search": "Sorento", "brand": "Kia"},
    {"key": "kia|sportage-ql", "search": "Sportage", "brand": "Kia"},
    {"key": "bmw|x5-f15", "search": "X5", "brand": "BMW"},
    {"key": "bmw|x5-g05", "search": "X5 G05", "brand": "BMW"},
    {"key": "mercedes-benz|g-class-w463", "search": "G-Class", "brand": "Mercedes"},
    {"key": "mercedes-benz|gle-w166", "search": "GLE", "brand": "Mercedes"},
    {"key": "mercedes-benz|gls-x166", "search": "GLS", "brand": "Mercedes"},
    {"key": "land-rover|discovery-4", "search": "Discovery 4", "brand": "Land Rover"},
    {"key": "land-rover|range-rover-l405", "search": "Range Rover", "brand": "Land Rover"},
    {"key": "volkswagen|tiguan-ad1", "search": "Tiguan", "brand": "Volkswagen"},
    {"key": "audi|q7-4m", "search": "Q7", "brand": "Audi"},
    {"key": "audi|q5-fy", "search": "Q5", "brand": "Audi"},
    {"key": "mazda|cx-5-kf", "search": "CX-5", "brand": "Mazda"},
]

def build_url(search, page=1):
    import urllib.parse
    kw = urllib.parse.quote(search)
    return f"{BASE_URL}/avto-mashin/avto-zarna/?keyword={kw}&page={page}"

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
    m = re.search(r"\b(19[89]\d|20[012]\d)\b", text)
    return int(m.group(1)) if m else None

def parse_drive(text):
    t = text.upper()
    if any(w in t for w in ["4WD","AWD","4×4","4X4"]): return "4WD"
    if any(w in t for w in ["2WD","FWD","FF","FR"]): return "2WD"
    return "4WD"

def parse_color(text):
    cm = {"цагаан":"白","white":"白","хар":"黒","black":"黒","мөнгө":"銀",
          "silver":"銀","серебр":"銀","улаан":"赤","red":"赤","саарал":"グレー",
          "gray":"グレー","grey":"グレー","хөх":"青","blue":"青","ногоон":"緑","шар":"黄"}
    t = text.lower()
    for k,v in cm.items():
        if k in t: return v
    return "不明"

def fetch(url, retries=3):
    for i in range(retries):
        try:
            resp = scraper.get(url, timeout=30)
            log.info(f"  HTTP {resp.status_code} ({len(resp.text)} chars)")
            if resp.status_code == 200:
                return resp.text
            log.warning(f"  ステータス {resp.status_code}")
        except Exception as e:
            log.warning(f"  取得失敗({i+1}/{retries}): {e}")
        if i < retries-1: time.sleep(REQUEST_DELAY*(i+1))
    return None

def parse_card(card):
    price_text = ""
    for sel in [".price-announcement",".announcement-pricing","[class*='price']",".cost"]:
        el = card.select_one(sel)
        if el: price_text = el.get_text(" ", strip=True); break
    price = parse_price(price_text)
    if not price or price < 1.0 or price > 500.0: return None
    title = ""
    for sel in ["h2","h3",".announcement-block__title","[class*='title']","a[href*='avto']"]:
        el = card.select_one(sel)
        if el: title = el.get_text(" ", strip=True); break
    full = card.get_text(" ")
    year = parse_year(title) or parse_year(full)
    if not year: return None
    drive = parse_drive(full)
    mileage = "不明"
    m = re.search(r"([\d,]+)\s*(?:км|km)", full, re.IGNORECASE)
    if m: mileage = f"{int(m.group(1).replace(',','')):,} km"
    return {"year":year,"drive":drive,"mileage":mileage,"color":parse_color(full),
            "import_year":datetime.now().year,"price":round(price,1)}

def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    results = []
    # 複数セレクタを試す
    cards = []
    for sel in ["li.announcement-container","div.announcement-block",
                "div[class*='list-announcement']","article.announcement",
                "div[class*='announcement']","li[class*='announcement']"]:
        cards = soup.select(sel)
        if cards:
            log.info(f"  セレクタ '{sel}' → {len(cards)}件")
            break
    if not cards:
        # ページ内容をログに記録
        log.warning(f"  カード未検出。タイトル: {soup.title.string if soup.title else 'なし'}")
        log.warning(f"  HTML先頭300文字: {html[:300]}")
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
    key, search = target["key"], target["search"]
    log.info(f"\n▶ [{key}] '{search}'")
    results, seen = [], set()
    for page in range(1, MAX_PAGES+1):
        url = build_url(search, page)
        log.info(f"  p{page}: {url}")
        html = fetch(url)
        if not html:
            log.warning("  取得失敗")
            break
        items = parse_page(html)
        log.info(f"  パース: {len(items)}件")
        for item in items:
            sig = (item["year"],item["drive"],item["price"])
            if sig not in seen: seen.add(sig); results.append(item)
        if not has_next(html, page): break
        time.sleep(REQUEST_DELAY)
    log.info(f"  ✓ {len(results)}件")
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
    parser.add_argument("--test", action="store_true", help="Harrier 1車種のみ")
    parser.add_argument("--output", default="scripts/price_db.json")
    args = parser.parse_args()

    targets = [t for t in TARGETS if t["key"]=="toyota|harrier"] if args.test else TARGETS
    db = {}
    for i, t in enumerate(targets, 1):
        log.info(f"[{i}/{len(targets)}]")
        try:
            r = scrape_one(t)
            if r: db[t["key"]] = r
        except Exception as e:
            log.error(f"エラー: {e}")
        if i < len(targets): time.sleep(REQUEST_DELAY*2)
    save(db, args.output)
    log.info(f"\n完了: {sum(len(v) for v in db.values())}件")

if __name__ == "__main__":
    main()
