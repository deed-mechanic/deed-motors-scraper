#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import json, time, re, sys, argparse, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_URL = "https://www.unegui.mn"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36", "Accept-Language": "mn,en;q=0.9"}
REQUEST_DELAY = 2.5
MAX_PAGES = 5

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

def build_search_url(search_word, page=1):
    keyword = requests.utils.quote(search_word)
    return f"{BASE_URL}/avto-mashin/avto-zarna/?keyword={keyword}&page={page}"

def parse_price_text(text):
    if not text: return None
    text = text.strip().replace("\xa0", " ").replace(",", "")
    m = re.search(r"([\d\.]+)\s*сая", text, re.IGNORECASE)
    if m: return round(float(m.group(1)), 1)
    m = re.search(r"([\d\.]+)\s*тэрбум", text, re.IGNORECASE)
    if m: return round(float(m.group(1)) * 1000, 1)
    m = re.search(r"(\d{6,})", text)
    if m: return round(int(m.group(1)) / 1_000_000, 1)
    return None

def parse_year(text):
    m = re.search(r"\b(19[89]\d|20[012]\d)\b", text)
    return int(m.group(1)) if m else None

def parse_drive(text):
    t = text.upper()
    if any(w in t for w in ["4WD","AWD","4×4","4X4"]): return "4WD"
    if any(w in t for w in ["2WD","FWD","FF","FR"]): return "2WD"
    return None

def parse_color(text):
    cmap = {"цагаан":"白","white":"白","хар":"黒","black":"黒","мөнгө":"銀",
            "silver":"銀","серебр":"銀","улаан":"赤","red":"赤","саарал":"グレー",
            "gray":"グレー","grey":"グレー","хөх":"青","blue":"青","ногоон":"緑","шар":"黄"}
    t = text.lower()
    for k, v in cmap.items():
        if k in t: return v
    return "不明"

def fetch_page(url, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:
            log.warning(f"取得失敗({attempt+1}/{retries}): {e}")
            if attempt < retries - 1: time.sleep(REQUEST_DELAY * (attempt+1))
    return None

def parse_card(card):
    price_text = ""
    for sel in [".price-announcement",".announcement-pricing","[class*='price']",".cost"]:
        el = card.select_one(sel)
        if el: price_text = el.get_text(" ", strip=True); break
    price = parse_price_text(price_text)
    if not price or price < 1.0 or price > 500.0: return None
    title = ""
    for sel in ["h2","h3",".announcement-block__title","[class*='title']"]:
        el = card.select_one(sel)
        if el: title = el.get_text(" ", strip=True); break
    full_text = card.get_text(" ")
    year = parse_year(title) or parse_year(full_text)
    if not year: return None
    drive = parse_drive(full_text) or "4WD"
    mileage = "不明"
    m = re.search(r"([\d,]+)\s*(?:км|km)", full_text, re.IGNORECASE)
    if m: mileage = f"{int(m.group(1).replace(',','')):,} km"
    return {"year":year,"drive":drive,"mileage":mileage,"color":parse_color(full_text),
            "import_year":datetime.now().year,"price":round(price,1)}

def parse_listing_page(html):
    soup = BeautifulSoup(html, "lxml")
    results = []
    cards = []
    for sel in ["li.announcement-container","div.announcement-block",
                "div[class*='list-announcement']","article.announcement"]:
        cards = soup.select(sel)
        if cards: log.info(f"  セレクタ: '{sel}' → {len(cards)}件"); break
    if not cards: log.warning("  カード見つからず"); return results
    for card in cards:
        try:
            item = parse_card(card)
            if item: results.append(item)
        except Exception as e: log.debug(f"
