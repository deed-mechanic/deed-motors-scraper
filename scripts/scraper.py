#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 2026-09: UNEGUI.MNがNext.js（React）ベースの構成に全面リニューアルされ、
# 一覧・詳細ページの実データがJavaScriptによるクライアント側描画になった
# （旧来のcloudscraper + 静的HTML解析では中身が空のシェルしか取得できない）。
# さらにCloudflareのボット検知（Turnstile）も導入されており、ヘッドレス
# ブラウザだと素の状態では"Just a moment..."チャレンジで弾かれる。
# そのためPlaywright（ヘッドレスChromium）+ playwright-stealth（ボット
# 検知の回避パッチ）でページを実際にレンダリングしてから解析する方式に変更した。
import json, time, re, sys, argparse, logging
from datetime import datetime
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install playwright playwright-stealth beautifulsoup4 lxml")
    print("python -m playwright install chromium")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

BASE_URL = "https://www.unegui.mn"
REQUEST_DELAY = 1.5
MAX_PAGES = 3
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# main()内でPlaywrightのページを生成しここに保持する（fetch()から使う）
_page = None
_BLOCK_STREAK_LIMIT = 4   # 一覧1ページ目の取得失敗がこの数だけ連続したら「サイトに遮断されている」と判断して中止
_last_target_blocked = False
_blocked = False
_FETCH_FAILED = []  # 取得に失敗した車種キー（前回データの引き継ぎ・再試行の判断に使う）

# 正しいURL構造: /avto-mashin/-avtomashin-zarna/メーカー/車種/
#
# 2026-09: ドロップダウン（MODELS_MAP）とスクレイパー対象が長年ずれており、
# 166車種中92車種がスクレイパー未対応だった問題を一括で解消した。
# 追加にあたり全URLをPlaywrightで実際に確認し、以下は現行サイトにカテゴリが
# 存在しない・または車種番号を区別する情報が無いため追加できていない：
#   - mitsubishi: eclipse-cross, montero-sport
#   - lexus: nx-450h-az20（PHEVをHVと区別する情報がタイトルに無い）,
#            ux-200/250h, lc-500/500h
#   - hyundai: palisade（既存targetのURLがリニューアルで/search/にリダイレクト、
#              代替スラッグ見つからず）
#   - bmw: x7-g07, 7series-g11
#   - mercedes-benz: gle-w166/w167（既存targetも同様にリダイレクト、代替
#     スラッグ見つからず）, glc-x253/x254, glb-x247, gla-h247, vito-w447
#   - volkswagen: multivan-t6
#   - audi: q8-f8, q3-8u/f3
#   - mazda: cx-5-ke, cx-9（cx-5-kfと同じURLだがタイトルが"Mazda CX"のみで
#     車種番号を区別できないため、別途追加しても同じデータの重複になる）
#   - dongfeng: aeolus-ax7, glory-ix5/ix7, forthing-t5, rich6
#     （現行サイトのDongfengラインナップが forthing-t5-evo/paladin/voyah-free
#      のみで、MODELS_MAP側の車種と実際の出品カテゴリが一致していない）
#   - ford: f-150-raptor（f-150-13と同じURLだがタイトルでRaptorを区別できない）
TARGETS = [
    {"key": "toyota|c-hr",                "url": "toyota/chr", "chr_drive_fix": True},
    # Harrier: UNEGUI.MN側は toyota/harrier の1URLに60系・80系が混在しているため、
    # ここで取得したのち年式・タイトルで60系ガソリン/60系HV/80系の3区分に自動振り分けする
    {"key": "toyota|harrier",                "url": "toyota/harrier", "harrier_split": True, "detail_fetch": True},
    {"key": "toyota|land-cruiser-300", "url": "toyota/land-cruiser-300", "year_min": 2021, "force_4wd": True, "wheel_fetch": True},
    {"key": "toyota|land-cruiser-200", "url": "toyota/land-cruiser-200", "year_min": 2007, "year_max": 2021, "force_4wd": True, "wheel_fetch": True},
    {"key": "toyota|land-cruiser-100", "url": "toyota/land-cruiser-100", "year_min": 1998, "year_max": 2007, "force_4wd": True},
    {"key": "toyota|land-cruiser-prado-150", "url": "toyota/land-cruiser-prado-150", "year_min": 2009, "year_max": 2024, "force_4wd": True, "wheel_fetch": True},
    {"key": "toyota|land-cruiser-prado-120", "url": "toyota/land-cruiser-prado-120", "year_min": 2002, "year_max": 2009, "force_4wd": True},
    {"key": "toyota|land-cruiser-prado-250", "url": "toyota/land-cruiser-prado-250", "year_min": 2024, "force_4wd": True},
    {"key": "toyota|crown-crossover", "url": "toyota/crown", "year_min": 2022},
    {"key": "toyota|sai", "url": "toyota/sai", "year_min": 2009, "year_max": 2017},
    {"key": "toyota|alphard-30", "url": "toyota/alphard", "alphard_split": True},
    {"key": "toyota|vellfire-30", "url": "toyota/vellfire", "vellfire_split": True},
    {"key": "toyota|prius-30", "url": "toyota/prius-30", "year_min": 2009, "year_max": 2015},
    {"key": "toyota|prius-50", "url": "toyota/prius-51", "year_min": 2015, "year_max": 2023, "wheel_fetch": True},
    {"key": "toyota|prius-60", "url": "toyota/prius-60", "year_min": 2023},
    {"key": "toyota|prius-41", "url": "toyota/prius-40", "year_min": 2009, "year_max": 2015},
    {"key": "toyota|aqua", "url": "toyota/aqua", "year_min": 2011},
    {"key": "toyota|rav4-50", "url": "toyota/rav4", "rav4_split": True, "detail_fetch": True},
    {"key": "toyota|camry-70", "url": "toyota/camry", "camry_split": True},
    {"key": "toyota|corolla-axio", "url": "toyota/corolla", "year_min": 2006, "year_max": 2019, "detail_fetch": True},
    {"key": "toyota|hiace-200", "url": "toyota/hiace", "year_min": 2004},
    {"key": "toyota|highlander", "url": "toyota/highlander", "year_min": 2013},
    {"key": "toyota|fortuner", "url": "toyota/fortuner", "year_min": 2015},
    {"key": "toyota|hilux", "url": "toyota/hilux", "year_min": 2015},
    {"key": "nissan|x-trail-t31",            "url": "nissan/x-trail", "year_max": 2013},
    {"key": "nissan|x-trail-t32",            "url": "nissan/x-trail", "year_min": 2013, "year_max": 2019},
    {"key": "nissan|x-trail-t33",            "url": "nissan/x-trail", "year_min": 2020},
    {"key": "nissan|patrol-y61",             "url": "nissan/patrol", "year_max": 2012},
    {"key": "nissan|patrol-y62",             "url": "nissan/patrol", "year_min": 2012},
    {"key": "nissan|elgrand-e52",            "url": "nissan/elgrand"},
    {"key": "nissan|serena-c27",             "url": "nissan/serena"},
    {"key": "mitsubishi|pajero-v60",         "url": "mitsubishi/pajero", "year_max": 2006},
    {"key": "mitsubishi|pajero-v80",         "url": "mitsubishi/pajero", "year_min": 2006},
    # Outlander: UNEGUI.MN側にPHEV専用カテゴリは無く、通常のOutlanderカテゴリに混在している。
    # 一覧カードの燃料表記（Цахилгаан=電気 / Хайбрид=ハイブリッド）でPHEVを見分け、ガソリン車の相場に混ざらないよう分ける
    {"key": "mitsubishi|outlander-gg",       "url": "mitsubishi/outlander", "year_max": 2012, "fuel_filter": "not_phev"},
    {"key": "mitsubishi|outlander-gf",       "url": "mitsubishi/outlander", "year_min": 2012, "fuel_filter": "not_phev"},
    {"key": "mitsubishi|outlander-phev",     "url": "mitsubishi/outlander", "fuel_filter": "phev"},
    # Nissan Leaf（EV）: 前輪駆動のみ。バッテリー劣化は査定ツール側の入力項目
    {"key": "nissan|leaf",                   "url": "nissan/leaf", "force_2wd": True, "wheel_fetch": True},
    # 「mitsubishi/delica-d5」はリニューアルでリダイレクトするようになったため
    # 「mitsubishi/delica」に修正
    {"key": "mitsubishi|delica-d5",          "url": "mitsubishi/delica"},
    {"key": "mitsubishi|l200",               "url": "mitsubishi/l200"},
    {"key": "mitsubishi|rvr",                "url": "mitsubishi/rvr"},
    {"key": "honda|cr-v-4",                  "url": "honda/cr-v", "year_max": 2011},
    {"key": "honda|cr-v-5",                  "url": "honda/cr-v", "year_min": 2011},
    {"key": "honda|odyssey",                 "url": "honda/odyssey"},
    {"key": "subaru|forester-sj",            "url": "subaru/forester"},
    {"key": "subaru|outback-bs",             "url": "subaru/outback"},
    {"key": "suzuki|jimny-jb23",             "url": "suzuki/jimny", "year_max": 2018},
    {"key": "suzuki|jimny-jb64",             "url": "suzuki/jimny", "year_min": 2018},
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
    {"key": "hyundai|tucson-nx4",            "url": "hyundai/tucson"},
    {"key": "kia|sorento-mq4",               "url": "kia/sorento"},
    {"key": "kia|sportage-ql",               "url": "kia/sportage"},
    {"key": "bmw|x5-e70", "url": "bmw/x5", "year_max": 2013},
    {"key": "bmw|x5-f15", "url": "bmw/x5", "year_min": 2013, "year_max": 2018},
    {"key": "bmw|x5-g05", "url": "bmw/x5", "year_min": 2018},
    {"key": "bmw|x3-f25", "url": "bmw/x3", "year_min": 2010, "year_max": 2017},
    {"key": "bmw|x3-g01", "url": "bmw/x3", "year_min": 2017},
    {"key": "bmw|x6-f16", "url": "bmw/x6", "year_min": 2014, "year_max": 2019},
    {"key": "bmw|x6-g06", "url": "bmw/x6", "year_min": 2019},
    {"key": "bmw|x1-f48", "url": "bmw/x1", "year_min": 2015},
    # 3シリーズ・5シリーズ: UNEGUI.MN側はモデル名（320/525）ごとの1URLに
    # 全世代混在。タイトルは世代不問だが個々の出品には生産年があるため、
    # 年式で従来どおり振り分け可能
    {"key": "bmw|3series-f30", "url": "bmw/320", "year_min": 2011, "year_max": 2018},
    {"key": "bmw|3series-g20", "url": "bmw/320", "year_min": 2018},
    {"key": "bmw|5series-f10", "url": "bmw/525", "year_min": 2010, "year_max": 2017},
    {"key": "bmw|5series-g30", "url": "bmw/525", "year_min": 2017},
    {"key": "mercedes-benz|g-class-w463",    "url": "mercedes-benz/g-class", "year_min": 2018},
    {"key": "mercedes-benz|gle-w166",        "url": "mercedes-benz/gle", "year_min": 2015, "year_max": 2018},
    {"key": "mercedes-benz|gls-x166", "url": "mercedes-benz/gls", "year_max": 2019},
    {"key": "mercedes-benz|gls-x167", "url": "mercedes-benz/gls", "year_min": 2019},
    {"key": "mercedes-benz|e-class-w212", "url": "mercedes-benz/e-class", "year_max": 2016},
    {"key": "mercedes-benz|e-class-w213", "url": "mercedes-benz/e-class", "year_min": 2016},
    {"key": "mercedes-benz|c-class-w205", "url": "mercedes-benz/c-class", "year_max": 2021},
    {"key": "mercedes-benz|c-class-w206", "url": "mercedes-benz/c-class", "year_min": 2021},
    {"key": "mercedes-benz|s-class-w222", "url": "mercedes-benz/s-class", "year_max": 2020},
    {"key": "mercedes-benz|s-class-w223", "url": "mercedes-benz/s-class", "year_min": 2020},
    {"key": "land-rover|discovery-4",        "url": "land-rover/discovery", "year_min": 2009, "year_max": 2016},
    {"key": "land-rover|range-rover-l405",   "url": "land-rover/range-rover", "year_min": 2012, "year_max": 2022},
    {"key": "land-rover|defender-l316",      "url": "land-rover/defender"},
    {"key": "volkswagen|tiguan-5n", "url": "volkswagen/tiguan", "year_max": 2016},
    {"key": "volkswagen|tiguan-ad1", "url": "volkswagen/tiguan", "year_min": 2016},
    {"key": "volkswagen|touareg-7l", "url": "volkswagen/touareg", "year_max": 2010},
    {"key": "volkswagen|touareg-7p", "url": "volkswagen/touareg", "year_min": 2010, "year_max": 2018},
    {"key": "volkswagen|touareg-cr", "url": "volkswagen/touareg", "year_min": 2018},
    {"key": "volkswagen|passat-b7", "url": "volkswagen/passat", "year_max": 2014},
    {"key": "volkswagen|passat-b8", "url": "volkswagen/passat", "year_min": 2014},
    {"key": "volkswagen|golf-7", "url": "volkswagen/golf", "year_max": 2019},
    {"key": "volkswagen|golf-8", "url": "volkswagen/golf", "year_min": 2019},
    {"key": "volkswagen|polo-6r", "url": "volkswagen/polo"},
    {"key": "audi|q7-4l", "url": "audi/q7", "year_max": 2015},
    {"key": "audi|q7-4m", "url": "audi/q7", "year_min": 2015},
    {"key": "audi|q5-8r", "url": "audi/q5", "year_max": 2017},
    {"key": "audi|q5-fy", "url": "audi/q5", "year_min": 2017},
    {"key": "audi|a6-c7", "url": "audi/a6", "year_max": 2018},
    {"key": "audi|a6-c8", "url": "audi/a6", "year_min": 2018},
    {"key": "audi|a4-b8", "url": "audi/a4", "year_min": 2007, "year_max": 2015},
    {"key": "audi|a4-b9", "url": "audi/a4", "year_min": 2015},
    {"key": "audi|a3-8v", "url": "audi/a3", "year_min": 2012, "year_max": 2020},
    # 注意: サイトリニューアルでCX-3/CX-5/CX-8等が mazda/cx に統合され、
    # タイトル・詳細ページどちらにも車種番号の区別情報が無くなったため、
    # フィルタ不可能。CX-5専用ではなくMazda CX全般のデータになる
    {"key": "mazda|cx-5-kf",                 "url": "mazda/cx"},
    {"key": "ford|explorer-u502", "url": "ford/explorer", "year_max": 2019},
    {"key": "ford|explorer-u625", "url": "ford/explorer", "year_min": 2019},
    {"key": "ford|escape-c520", "url": "ford/escape"},
    # F-150: UNEGUI.MN側は "ford/f150"（ハイフン無し）。タイトルでRaptorを
    # 区別できないため、Raptor専用キー(f-150-raptor)は追加していない
    {"key": "ford|f-150-13", "url": "ford/f150", "year_min": 2015},
    {"key": "ford|ranger-t6", "url": "ford/ranger"},
    {"key": "ford|everest-2", "url": "ford/everest"},
    # RAM: UNEGUI.MN側は「Dodge」カテゴリ内に「Dodge Ram」として掲載（Ramブランド独立カテゴリは無い）。
    # Challenger等が混在するためタイトルで絞る。ほぼ全車が4WDのピックアップ
    # Tesla: UNEGUI.MN側のURLは大文字小文字を区別する（Tesla/ModelY, Tesla/ModelS）。
    # Model 3 / Model X の独立カテゴリは無い（出品なし）。電気自動車のため駆動方式はデュアルモーター(4WD)/RWDの区別が
    # 一覧に無く「不明」のまま。詳細ページから取得する
    {"key": "tesla|model-y", "url": "Tesla/ModelY", "detail_fetch": True},
    {"key": "tesla|model-s", "url": "Tesla/ModelS", "detail_fetch": True},
    {"key": "ram|1500", "url": "dodge", "title_contains": "Ram", "force_4wd": True, "wheel_fetch": True},
    # Dongfeng: UNEGUI.MN側の乗用車は Forthing T5 Evo / Voyah Free のみ（2026-11-18時点で計3件）。
    # 協業ディーラーの販売車（約200台）はUNEGUI.MNに掲載されていないため、ここでは取得できない。
    # カテゴリ直下の他の掲載はトラック・部品。新しい車種カテゴリが増えたら上のslugを追加すること
    {"key": "dongfeng|forthing-t5-evo", "url": "dongfeng/forthing-t5-evo", "detail_fetch": True},
    {"key": "dongfeng|voyah-free", "url": "dongfeng/voyah-free", "detail_fetch": True},
    # Porsche: 911（1件のみ・平均5億超）は高額すぎるため対象外。
    # 実用車として流通量のある主要モデルのみ追加
    {"key": "porsche|cayenne", "url": "porsche/cayenne", "wheel_fetch": True},
    {"key": "porsche|macan", "url": "porsche/macan", "wheel_fetch": True},
    {"key": "porsche|panamera", "url": "porsche/panamera"},
    {"key": "porsche|cayman", "url": "porsche/cayman"},
    {"key": "porsche|boxster", "url": "porsche/boxster"},
]

# ── 駆動方式の取得方針 ─────────────────────────────────────────────
# 一覧ページには駆動方式がほぼ書かれていない（記載があるのは約1割。2026-11-19時点で全体の76%が「不明」だった）。
# 4WD設定のある車種は、詳細ページ（仕様欄）から駆動方式を取得する。
# 取得結果は広告IDごとに scripts/.detail_cache.json に保存し、2回目以降は新規広告だけ詳細ページを開く。
# 1晩あたりの新規取得には時間枠（--detail-budget-min）があり、超えた分は翌晩以降に回る。
# 常時4WDの車種（LX/GX/Gクラス/ランドローバー系）は4WD固定とし、ハンドル位置のみ詳細ページから取得する。
_ALWAYS_4WD_KEYS = {
    "lexus|lx-600", "lexus|lx-570", "lexus|lx-470", "lexus|gx-460",
    "mercedes-benz|g-class-w463",
    "mitsubishi|outlander-phev",  # 前後モーターの4WDのみ
    "land-rover|discovery-4", "land-rover|range-rover-l405", "land-rover|defender-l316",
}
_DRIVE_DETAIL_KEYS = {
    "toyota|c-hr", "toyota|crown-crossover", "toyota|alphard-30", "toyota|vellfire-30",
    "toyota|prius-50", "toyota|prius-60", "toyota|hiace-200", "toyota|highlander",
    "toyota|fortuner", "toyota|hilux",
    "nissan|x-trail-t31", "nissan|x-trail-t32", "nissan|x-trail-t33",
    "nissan|patrol-y61", "nissan|patrol-y62", "nissan|elgrand-e52", "nissan|serena-c27",
    "mitsubishi|pajero-v60", "mitsubishi|pajero-v80", "mitsubishi|outlander-gg",
    "mitsubishi|outlander-gf", "mitsubishi|delica-d5", "mitsubishi|l200", "mitsubishi|rvr",
    "honda|cr-v-4", "honda|cr-v-5",
    "subaru|forester-sj", "subaru|outback-bs",
    "suzuki|jimny-jb23", "suzuki|jimny-jb64",
    "lexus|rx-gas", "lexus|rx-hybrid", "lexus|nx-az10", "lexus|es-axzh10",
    "lexus|is-300-xe30", "lexus|gs-350", "lexus|ls-500",
    "hyundai|santa-fe-tm", "hyundai|palisade", "hyundai|tucson-nx4",
    "kia|sorento-mq4", "kia|sportage-ql",
    "bmw|x5-e70", "bmw|x5-f15", "bmw|x5-g05", "bmw|x3-f25", "bmw|x3-g01",
    "bmw|x6-f16", "bmw|x6-g06", "bmw|x1-f48",
    "bmw|3series-f30", "bmw|3series-g20", "bmw|5series-f10", "bmw|5series-g30",
    "mercedes-benz|gle-w166", "mercedes-benz|gls-x166", "mercedes-benz|gls-x167",
    "mercedes-benz|e-class-w212", "mercedes-benz|e-class-w213",
    "mercedes-benz|c-class-w205", "mercedes-benz|c-class-w206",
    "mercedes-benz|s-class-w222", "mercedes-benz|s-class-w223",
    "volkswagen|tiguan-5n", "volkswagen|tiguan-ad1", "volkswagen|touareg-7l",
    "volkswagen|touareg-7p", "volkswagen|touareg-cr",
    "audi|q7-4l", "audi|q7-4m", "audi|q5-8r", "audi|q5-fy",
    "audi|a6-c7", "audi|a6-c8", "audi|a4-b8", "audi|a4-b9",
    "mazda|cx-5-kf",
    "ford|explorer-u502", "ford|explorer-u625", "ford|escape-c520",
    "ford|f-150-13", "ford|ranger-t6", "ford|everest-2",
    "porsche|cayenne", "porsche|macan", "porsche|panamera",
}
for _t in TARGETS:
    if _t["key"] in _ALWAYS_4WD_KEYS:
        _t["force_4wd"] = True
        _t["wheel_fetch"] = True
    elif _t["key"] in _DRIVE_DETAIL_KEYS:
        _t["detail_fetch"] = True

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

# 取得に不要な外部の解析・広告・計測スクリプト。これらが応答しない時間帯があり（2026-11-17と11-19夜に確認）、
# 1ページの読み込みが約25秒かかる原因になっていた（本体のHTMLには関係ない）。Cloudflare本体の通信は止めない
_BLOCKED_HOSTS = (
    "doubleclick.net", "googlesyndication.com", "google-analytics.com", "googletagmanager.com",
    "googleadservices.com", "clarity.ms", "cloudflareinsights.com", "sentry.sshd.im",
    "facebook.net", "facebook.com", "maestra-static.io", "maestra.io", "ph.unegui.mn",
    "yandex.ru", "yandex.com", "mc.yandex.ru", "hotjar.com", "tiktok.com", "bing.com",
)

def new_page(browser):
    """スクレイピング用ページを作る。画像・動画・フォントは取得に不要なので読み込まない
    （転送量と読み込み時間の削減、外部リソースの遅延に引きずられないため）"""
    page = browser.new_page(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
        locale="mn-MN",
    )
    def _handler(route):
        try:
            req = route.request
            host = (urlparse(req.url).hostname or "").lower()
            if req.resource_type in ("image", "media", "font") or any(
                    host == d or host.endswith("." + d) for d in _BLOCKED_HOSTS):
                route.abort()
            else:
                route.continue_()
        except Exception:
            pass  # 画面遷移・終了と重なった場合などの無害な例外
    page.route("**/*", _handler)
    return page

# 詳細ページの取得結果の保存（広告ID → 駆動方式・ハンドル位置）。リポジトリには含めずローカルに置く
DETAIL_CACHE_PATH = "scripts/.detail_cache.json"
_detail_cache = {}
_detail_stats = {"cache": 0, "fetched": 0, "deferred": 0, "code_override": 0}
_detail_soft_deadline = None

def load_detail_cache():
    global _detail_cache
    try:
        with open(DETAIL_CACHE_PATH, encoding="utf-8") as f:
            _detail_cache = json.load(f)
        log.info(f"詳細ページの保存データ: {len(_detail_cache)}件を読み込み")
    except (OSError, ValueError):
        _detail_cache = {}

def save_detail_cache():
    # 45日以上見かけていない広告（掲載終了）は破棄して肥大化を防ぐ
    limit = time.time() - 45 * 86400
    keep = {k: v for k, v in _detail_cache.items() if v.get("seen", v.get("t", 0)) >= limit}
    try:
        with open(DETAIL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False)
    except OSError as e:
        log.warning(f"詳細ページの保存データを書き込めません: {e}")

def fetch_detail_extra(url, retries=2, brand=None):
    """detail_fetch / wheel_fetch フラグの車種向けに、詳細ページから
    駆動方式（Хөтлөгч）とハンドル位置（Хүрд）をまとめて取得する。
    一覧ページのカードにはどちらの記載もほぼ無いため、1件ずつ詳細ページを
    開いて確認する必要がある。両方必要な車種で2回開かずに済むよう1回のfetchで両方拾う。

    リニューアル後のサイトは <meta name="keywords" content="...,Хүрд Буруу,
    Хөтлөгч Бүх дугуй 4WD,..."> にスペック一覧をまとめて埋め込んでいるため、
    そこから正規表現で拾うのが最も簡単で壊れにくい（可視DOM側はTailwindの
    ユーティリティクラスのみでキー識別できるクラス名が無い）。

    ハンドル位置はモンゴル語で「Зөв」＝正しい（モンゴルは右側通行のため左ハンドルが正）、
    「Буруу」＝誤り（右ハンドル＝主に日本からの中古直輸入車）という表現になっている。
    """
    # 広告IDごとの保存（広告は何日も掲載されるため、2回目以降は新規広告だけ詳細ページを開けば済む）
    ad_id = None
    mid = re.search(r"/adv/(\d+)", url)
    if mid:
        ad_id = mid.group(1)
        ent = _detail_cache.get(ad_id)
        now = time.time()
        if ent and (ent.get("drive") or now - ent.get("t", 0) < 7 * 86400):
            # 駆動方式が分かっている広告はそのまま使う。不明だった広告は7日ごとに再確認する
            ent["seen"] = now
            _detail_stats["cache"] += 1
            return ent.get("drive"), ent.get("wheel")
    # 1晩あたりの新規取得に時間枠を設ける（超えた分は翌晩以降に取得。取得済みは保存されるため少しずつ埋まる）
    if _detail_soft_deadline is not None and time.time() > _detail_soft_deadline:
        _detail_stats["deferred"] += 1
        return None, None

    html = fetch(url, retries=retries, settle_ms=800)
    if not html:
        return None, None
    _detail_stats["fetched"] += 1

    km = re.search(r'name="keywords"\s+content="([^"]+)"', html)
    keywords = km.group(1) if km else ""

    drive = None
    m = re.search(r'Хөтлөгч\s+([^,"]+)', keywords)
    if m:
        # 表記は「Бүх дугуй 4WD」「Урдаа FWD」「Хойноо RWD」の3種類。
        # 4WDにはAWD、2WDにはFWD(前輪駆動)・RWD/FR(後輪駆動)の表現が含まれる
        val = m.group(1).upper()
        if any(w in val for w in ("4WD", "AWD", "4X4", "БҮХ ДУГУЙ")):
            drive = "4WD"
        elif any(w in val for w in ("FWD", "RWD", "2WD", "УРДАА", "ХОЙНОО")):
            drive = "2WD"

    # 型式（「Серийн ангилал: GYL25」のように詳細ページの仕様欄にある）から駆動方式を推定。
    # トヨタ/レクサスは型式の数字部の末尾が5だと4WDの可能性が高い（例: AE110=FF / AE115=4WD、
    # GYL15・GYL25・AVU65 など）。出品者が入力する駆動方式欄は誤りが多い（プリウスがRWD等）ため、
    # 型式が5で終わる場合はこちらを優先する
    if brand in ("toyota", "lexus"):
        try:
            txt = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        except Exception:
            txt = ""
        mc = re.search(r"Серийн ангилал:?\s*([A-Za-z]{2,5}\d{2,3})", txt)
        if mc:
            code_digits = re.search(r"(\d{2,3})$", mc.group(1)).group(1)
            if code_digits.endswith("5"):
                if drive == "2WD":
                    _detail_stats["code_override"] += 1
                drive = "4WD"

    wheel = None
    m2 = re.search(r'Хүрд\s+([^,"]+)', keywords)
    if m2:
        val2 = m2.group(1).strip()
        if val2 == "Зөв":
            wheel = "LHD"
        elif val2 == "Буруу":
            wheel = "RHD"

    if ad_id:
        now = time.time()
        _detail_cache[ad_id] = {"drive": drive, "wheel": wheel, "t": now, "seen": now}
    return drive, wheel

def fetch(url, retries=3, settle_ms=2500):
    """Playwright（ステルスパッチ済み）でページを実際に開いて描画後のHTMLを返す。
    Cloudflareのチャレンジ画面が出た場合は間隔を空けてリトライする。
    """
    for i in range(retries):
        try:
            # "load"（全リソース読み込み完了）ではなく "domcontentloaded" で待つ。
            # 2026-11-17は外部リソースの遅延で load が毎回約25秒止まり、1ページ29秒×約900ページで
            # 日次更新が4時間の上限を超えて強制終了された。カード情報はHTML本体(SSR)に含まれるため不要
            _page.goto(url, wait_until="domcontentloaded", timeout=45000)
            _page.wait_for_timeout(settle_ms)
            html = _page.content()
            head = html[:3000]
            if "Just a moment" in head or "challenges.cloudflare.com" in head:
                log.warning(f"  Cloudflareチャレンジ検出、再試行します({i+1}/{retries})")
                time.sleep(REQUEST_DELAY*(i+3))
                continue
            # サイトリニューアルでカテゴリURLのスラッグが変わっている場合、
            # /search/ やトップページにリダイレクトされることがある。
            # その場合は「0件」ではなく明示的に警告を出す（TARGETSのURL要修正のサイン）
            final_url = _page.url
            if "/search" in final_url or final_url.rstrip("/") == BASE_URL:
                # 2026-11-23: Cloudflareの確認画面を経由して /search/ に飛ばされ、Palisade(55件)・GLE(16件)が
                # 「0件」として保存・前回データが消えた。リダイレクト先のHTMLは車種の一覧ではないので、
                # 成功扱いにせず間隔を空けて再試行し、最後まで駄目なら取得失敗(None)にして前回データを引き継ぐ
                log.warning(f"  ⚠️ URLがリダイレクトされました（スラッグ変更/一時的な遮断）: {url} -> {final_url} 再試行します({i+1}/{retries})")
                time.sleep(REQUEST_DELAY*(i+4))
                continue
            log.info(f"  取得成功 ({len(html)} chars): {url}")
            return html
        except Exception as e:
            log.warning(f"  取得失敗({i+1}/{retries}): {e}")
        if i < retries-1: time.sleep(REQUEST_DELAY*(i+1))
    return None

def parse_card(card):
    # タイトル: リニューアル後は itemprop="name" のmetaタグにフルタイトルが入っている
    # （RX・Harrierの世代・グレード判定用、最終保存前に除去される）
    title_text = ""
    title_el = card.select_one('meta[itemprop="name"]')
    if title_el: title_text = (title_el.get("content") or "").strip()
    if not title_text:
        for sel in ["h3", "h4", "[class*='title']"]:
            el = card.select_one(sel)
            if el: title_text = el.get_text(" ", strip=True); break

    # 価格: itemprop="price" のmetaタグ（例: content="124 сая ₮"）
    price_text = ""
    price_el = card.select_one('meta[itemprop="price"]')
    if price_el: price_text = (price_el.get("content") or "").strip()
    if not price_text:
        # テキスト全体から「сая ₮」を探す
        price_text = card.get_text(" ")
    price = parse_price(price_text)
    if not price or price < 1.0 or price > 500.0: return None

    # 走行距離・駆動方式等の要約テキスト（data-component="ListingFeatures" 内に列挙）
    feat_el = card.select_one('[data-component="ListingFeatures"]')
    feat_text = feat_el.get_text(" ", strip=True) if feat_el else ""
    full = " ".join(t for t in [title_text, feat_text] if t) or card.get_text(" ")

    # 年（「2018/2022」形式＝生産年/モンゴル輸入年、タイトルに含まれる）
    m = re.search(r"\b(19[89]\d|20[012]\d)(?:/(20[012]\d))?\b", title_text or full)
    year = int(m.group(1)) if m else None
    if not year: return None
    import_year = int(m.group(2)) if m and m.group(2) else datetime.now().year

    drive = parse_drive(full)

    mileage = "不明"
    m2 = re.search(r"([\d,]+)\s*(?:км|km)", full, re.IGNORECASE)
    if m2: mileage = f"{int(m2.group(1).replace(',','')):,} km"

    # 詳細ページURL（駆動方式・ハンドル位置の正確な取得が必要な車種のみ使用、最終保存前に除去される）
    href = None
    link_el = card.select_one('a[itemprop="url"]') or card.select_one("a[href*='/adv/']")
    if link_el is None and card.name == "a" and card.get("href"):
        link_el = card  # グリッド表示ではカード自体が <a>
    if link_el:
        href = link_el.get("href")
        if href and href.startswith("/"):
            href = BASE_URL + href

    return {"year":year,"drive":drive,"mileage":mileage,
            "color":parse_color(full),
            "import_year":import_year,
            "price":round(price,1),
            "_title": title_text or full[:80],
            "_fulltext": full,
            "_href": href}

def generic_cards(soup):
    """data-marker（広告ID）を持つ要素から、1広告=1カードの要素を返す（関連広告は除外）"""
    cards, seen = [], set()
    for el in soup.select('[data-marker^="listing-advert_card-advert:"]'):
        mk = el.get("data-marker")
        if mk in seen:
            continue
        if el.find_parent(attrs={"data-component": re.compile(r"^Gallery")}):
            continue  # 関連広告
        seen.add(mk)
        # 価格などのmetaを含む最小の祖先（自分自身を含む）をカードとする。他の広告まで含む大きさにはしない
        cur, card = el, el
        for _ in range(4):
            if cur is None:
                break
            if cur.select_one('meta[itemprop="price"]'):
                card = cur
                break
            cur = cur.parent
        if len(card.select('[data-marker^="listing-advert_card-advert:"]')) > 1:
            card = el
        cards.append(card)
    return cards

def listing_count(html):
    """ページ見出しの掲載件数（例: 「Lexus LX 570 зарна 116」→116）。取れなければNone"""
    try:
        soup = BeautifulSoup(html, "lxml")
        h1 = soup.find("h1")
        if not h1:
            return None
        m = re.search(r"зарна\s+([\d,]+)", h1.get_text(" ", strip=True))
        return int(m.group(1).replace(",", "")) if m else None
    except Exception:
        return None

def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    # リニューアル後のカードは data-component="BigAdCard" の div（schema.org/Productのitemscope付き）
    cards = soup.select('div[data-component="BigAdCard"]')
    if not cards:
        # 汎用: コンポーネント名（BigAdCard / CardGridDesktop / CardGridLink など）はサイト更新のたびに変わる
        # （2026-11-19にCardGridDesktop→CardGridLinkへ変更されて解析が止まった）。名前に依存しない目印として、
        # 広告ごとに付く data-marker="listing-advert_card-advert:広告ID" を使う。
        # 一覧の下の「関連広告」(Gallery系。別車種のトラック等)は除外する
        cards = generic_cards(soup)
    if not cards:
        # グリッド表示のページ（LX 570 / LX 600 など。2026-11-18に判明: このレイアウトだと
        # BigAdCardが存在せず全件「カード未検出」になり、掲載が100件以上あっても0件扱いだった）。
        # カード自体が <a itemscope itemtype=schema.org/Product> で、中身は同じmeta(itemprop)構造。
        # ページ下部の「関連広告」(GalleryAdCard: 別車種のトラック等)は含めない
        cards = soup.select('[data-component="CardGridDesktop"]')
    if not cards:
        # フォールバック（サイトが旧レイアウトに戻った場合用）
        for sel in ["div.advert.js-item-listing", "div.advert", "div.advert-grid"]:
            cards = soup.select(sel)
            if cards:
                log.info(f"  旧セレクタ '{sel}' → {len(cards)}件")
                break
    if not cards:
        log.warning(f"  カード未検出 — タイトル: {soup.title.string if soup.title else 'なし'}")
        return []
    log.info(f"  カード{len(cards)}件検出")
    results = []
    for card in cards:
        try:
            item = parse_card(card)
            if item: results.append(item)
        except Exception as e:
            log.debug(f"  カードエラー: {e}")
    return results

def has_next(html, page):
    soup = BeautifulSoup(html, "lxml")
    # リニューアル後はページ番号リンクにキー識別できるクラス名が無いため、
    # href内の page=N を総なめして現在ページより大きい番号があるかで判定する
    max_page = page
    for a in soup.select('a[href*="page="]'):
        m = re.search(r"page=(\d+)", a.get("href",""))
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page > page

def scrape_one(target):
    global _last_target_blocked
    _last_target_blocked = False
    key = target["key"]
    path = target["url"]
    log.info(f"\n▶ [{key}]")
    results, seen = [], set()
    for page in range(1, MAX_PAGES+1):
        url = build_url(path, page)
        html = fetch(url)
        if not html:
            if page == 1:
                _FETCH_FAILED.append(key)  # 1ページ目すら取得できない＝「出品0件」ではなく取得失敗
                _last_target_blocked = True
            break
        items = parse_page(html)
        log.info(f"  p{page}: {len(items)}件パース")
        if page == 1 and not items:
            n_expected = listing_count(html)
            if n_expected and n_expected >= 3:
                # 見出しには掲載件数があるのに1件も読めない＝サイトの構造変更で解析できていない。
                # 「0件」として前回データを消さないよう、取得失敗として扱う（前回データを引き継ぎ、実行結果は失敗）
                log.error(f"  ❌ [{key}] 見出しは{n_expected}件なのに0件しか解析できません（サイトの構造変更の疑い）")
                _FETCH_FAILED.append(key)
                break
        for item in items:
            sig = (item["year"],item["drive"],item["price"])
            if sig not in seen: seen.add(sig); results.append(item)
        if not has_next(html, page): break
        time.sleep(REQUEST_DELAY)
    # 年式範囲フィルタ（表示ラベルの世代範囲と実データの食い違いを防ぐ）
    # メーカーカテゴリに複数車種が混在する場合（Dodge内のRam/Challenger等）タイトルで絞る
    tc = target.get("title_contains")
    if tc:
        before = len(results)
        results = [r for r in results if tc.lower() in (r.get("_title") or r.get("_fulltext") or "").lower()]
        log.info(f"  [{key}] タイトル「{tc}」以外を除外: {before - len(results)}件")

    # 燃料表記でPHEV（プラグインハイブリッド）を分ける（カードの要約に「Цахилгаан」「Хайбрид」等が入る）
    ff = target.get("fuel_filter")
    if ff:
        before = len(results)
        is_phev = lambda r: re.search(r"Цахилгаан|Хайбрид|Хибрид|Гибрид|Хосолсон|PHEV|Plug", r.get("_fulltext") or "", re.I) is not None
        results = [r for r in results if is_phev(r) == (ff == "phev")]
        log.info(f"  [{key}] 燃料表記で絞り込み({ff}): {before}件 → {len(results)}件")

    ymin = target.get("year_min")
    ymax = target.get("year_max")
    if ymin is not None or ymax is not None:
        before = len(results)
        results = [r for r in results if (ymin is None or r["year"] >= ymin) and (ymax is None or r["year"] <= ymax)]
        skipped = before - len(results)
        if skipped:
            log.info(f"  [{key}] 年式範囲外を除外: {skipped}件（範囲: {ymin}-{ymax}）")

    # 全車4WD固定（Land Cruiser・Prado等、2WD設定が存在しない車種向け）
    if target.get("force_4wd"):
        for item in results:
            item["drive"] = "4WD"
        log.info(f"  [{key}] 全件4WD固定")

    # 前輪駆動のみの車種（Nissan Leaf等）は2WD固定
    if target.get("force_2wd"):
        for item in results:
            item["drive"] = "2WD"
        log.info(f"  [{key}] 全件2WD固定")

    # 詳細ページから正確な駆動方式・ハンドル位置を取得（一覧ページに記載が無いため）
    need_detail = target.get("detail_fetch") or target.get("wheel_fetch")
    if need_detail:
        fixed_drive, fixed_wheel = 0, 0
        s0 = dict(_detail_stats)
        brand = key.split("|")[0]
        for item in results:
            href = item.pop("_href", None)
            if not href:
                continue
            fetched_before = _detail_stats["fetched"]
            real_drive, wheel = fetch_detail_extra(href, brand=brand)
            if target.get("detail_fetch") and real_drive:
                item["drive"] = real_drive
                fixed_drive += 1
            if wheel:
                item["wheel"] = wheel
                fixed_wheel += 1
            if _detail_stats["fetched"] > fetched_before:
                time.sleep(1.0)  # 実際にページを開いた時だけ間隔を空ける（保存済みは待たない）
        d = {k: _detail_stats[k] - s0[k] for k in s0}
        log.info(f"  [{key}] 詳細ページ: 駆動方式{fixed_drive}件 / ハンドル位置{fixed_wheel}件（全{len(results)}件）"
                 f" ［新規取得{d['fetched']} / 保存済み{d['cache']} / 時間枠超過で次回へ{d['deferred']} / 型式で4WDに修正{d['code_override']}］")
    else:
        for item in results:
            item.pop("_href", None)

    log.info(f"  [{key}] 計{len(results)}件")
    return results

def save(db, path="scripts/price_db.json"):
    # 取得が失敗して極端に少ない場合（サイト遮断など）は、正常な既存データを上書きしない。
    # 異常終了(exit 1)にして、日次ワークフローの失敗として検知できるようにする
    new_total = sum(len(v) for v in db.values())
    try:
        with open(path, encoding="utf-8") as f:
            old_total = json.load(f).get("total_records", 0)
    except (OSError, ValueError):
        old_total = 0
    if old_total > 0 and new_total < old_total * 0.3:
        log.error(f"取得件数が異常に少ないため保存を中止: 新{new_total}件 / 既存{old_total}件（既存データを保持）")
        sys.exit(1)
    out = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "source": "unegui.mn",
           "total_records": sum(len(v) for v in db.values()),
           "total_models": len(db), "data": db}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log.info(f"保存: {path} ({out['total_records']}件)")

def scrape_all(targets, db=None, done=None, on_target_done=None, deadline=None):
    """deadline: time.time()基準の打ち切り時刻。超えたら残りの車種は取得失敗扱い（前回データを引き継いで
    公開できる）にする。外部からの強制終了（タスクの実行時間上限）で何も公開できなくなるのを防ぐ"""
    global _blocked
    db = {} if db is None else db
    done = set() if done is None else done
    streak = 0
    for i,t in enumerate(targets,1):
        log.info(f"[{i}/{len(targets)}]")
        if t["key"] in done:
            log.info(f"  [{t['key']}] 再開: 取得済みのためスキップ")
            continue
        if deadline is not None and time.time() > deadline:
            _FETCH_FAILED.append(t["key"])
            log.warning(f"  [{t['key']}] 時間上限のため取得を打ち切り（前回データを引き継ぎ）")
            continue
        n_failed_before = len(_FETCH_FAILED)
        try:
            r = scrape_one(t)
            if not r:
                if _last_target_blocked:
                    streak += 1
                    if streak >= _BLOCK_STREAK_LIMIT:
                        _blocked = True
                        log.error(f"❌ 一覧の取得が{streak}車種連続で失敗しました。サイトに遮断されている可能性が高いため中止します")
                        break
                else:
                    streak = 0
                if i < len(targets): time.sleep(REQUEST_DELAY*2)
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
            _FETCH_FAILED.append(t["key"])
        if len(_FETCH_FAILED) == n_failed_before:
            done.add(t["key"])
            if on_target_done: on_target_done(db, done)
            streak = 0
        elif _last_target_blocked:
            streak += 1
            if streak >= _BLOCK_STREAK_LIMIT:
                # 2026-11-24: Cloudflareが全ページを遮断し、126車種×3回の再試行で約1時間を空費した上、
                # 何も取れていないのに更新日時だけが新しくなった。連続で取れない時点で打ち切り、
                # 保存せずに終了する（呼び出し側が時間を空けて再開する）
                _blocked = True
                log.error(f"❌ 一覧の取得が{streak}車種連続で失敗しました。サイトに遮断されている可能性が高いため中止します")
                break
        else:
            streak = 0
        if i < len(targets): time.sleep(REQUEST_DELAY*2)
    return db

def main():
    global _page, _detail_soft_deadline
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--output", default="scripts/price_db.json")
    parser.add_argument("--resume", action="store_true", help="12時間以内のチェックポイントがあれば、取得済みの車種をスキップして再開")
    parser.add_argument("--time-budget-min", type=float, default=300,
                        help="取得に使う最大分数。超えたら残りは前回データを引き継いで保存（既定300分）")
    parser.add_argument("--detail-budget-min", type=float, default=100,
                        help="詳細ページ（駆動方式など）の新規取得に使う最大分数。超えた分は翌晩以降に回す（既定100分。"
                             "一覧の取得に約80分かかるため、深夜0〜3時の枠に収まる）")
    args = parser.parse_args()
    deadline = time.time() + args.time_budget_min * 60
    _detail_soft_deadline = time.time() + min(args.detail_budget_min, args.time_budget_min - 20) * 60
    load_detail_cache()
    ckpt_path = "scripts/.scrape_checkpoint.json"
    targets = [t for t in TARGETS if t["key"]=="toyota|harrier"] if args.test else TARGETS

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        _page = new_page(browser)
        db, done = {}, set()
        if args.resume:
            try:
                with open(ckpt_path, encoding="utf-8") as f:
                    ck = json.load(f)
                if time.time() - ck.get("saved_at", 0) < 12*3600:
                    db, done = ck["db"], set(ck["done"])
                    log.info(f"チェックポイントから再開: 取得済み{len(done)}車種")
            except (OSError, ValueError, KeyError):
                pass

        def save_checkpoint(cur_db, cur_done):
            with open(ckpt_path, "w", encoding="utf-8") as f:
                json.dump({"saved_at": time.time(), "done": sorted(cur_done), "db": cur_db}, f, ensure_ascii=False)
            save_detail_cache()

        db = scrape_all(targets, db=db, done=done, on_target_done=save_checkpoint, deadline=deadline)
        browser.close()
    save_detail_cache()
    log.info(f"詳細ページ: 新規取得{_detail_stats['fetched']} / 保存済み利用{_detail_stats['cache']} / "
             f"次回へ繰り越し{_detail_stats['deferred']} / 型式で4WDに修正{_detail_stats['code_override']}")

    if _blocked:
        # データも更新日時も書き換えない（取得できていないのに「更新済み」に見せない）。
        # 取得済み分はチェックポイントに残してあるので、時間を置いて --resume で続きから取れる
        log.error("遮断のため保存せずに終了します（既存データ・更新日時は変更なし）。終了コード3")
        sys.exit(3)

    if _FETCH_FAILED:
        # 取得に失敗した車種は前回のデータを残す（全体を捨てず、その車種だけ古いまま維持）
        try:
            with open(args.output, encoding="utf-8") as f:
                old = json.load(f).get("data", {})
        except (OSError, ValueError):
            old = {}
        carried = [k for k in old if k not in db]
        for k in carried:
            db[k] = old[k]
        log.warning(f"取得失敗 {len(_FETCH_FAILED)}車種: {_FETCH_FAILED} / 前回データを引き継ぎ: {len(carried)}キー")

    # 前回あった車種（5件以上）が今回まるごと消えた場合は警告（URL変更・レイアウト変更・解析漏れの疑い）
    try:
        with open(args.output, encoding="utf-8") as f:
            prev = json.load(f).get("data", {})
        vanished = [f"{k}({len(v)}件)" for k, v in prev.items() if k not in db and len(v) >= 5]
        if vanished:
            log.warning(f"⚠️ 前回あった車種が今回0件: {vanished}")
    except (OSError, ValueError):
        pass

    save(db, args.output)
    if _FETCH_FAILED:
        sys.exit(2)  # 一部失敗（データは保存済み）。呼び出し側は --resume で再試行できる
    try:
        import os; os.remove(ckpt_path)
    except OSError:
        pass

if __name__ == "__main__":
    main()
