# deed-motors-scraper

DEED MOTORS 査定ツール（`index.html` / `bilingual.html`）と、UNEGUI.MN価格データの自動収集スクリプト一式。

## セットアップ（初回のみ）

`index.html` と `templates/deed_motors_PC_v3_template.html`（バイリンガル版は `bilingual.html` と `templates/deed_motors_PC_v3_BILINGUAL_template.html`）は常に内容を同期させておく必要があります。`index.html`側だけを直接編集してテンプレートへの反映を忘れると、次回の自動更新（GitHub Actions）で変更が消えてしまいます。

これを防ぐため、コミット前に自動でチェックするgit hookを用意しています。クローンしたら最初に一度だけ有効化してください。

```bash
git config core.hooksPath .githooks
```

以降、`index.html`/`bilingual.html` またはテンプレートを含むコミットのたびに、両者が（PRICE_DBブロックと更新バッジを除いて）一致しているか自動チェックされ、不一致だとコミットがブロックされます。

## テンプレート同期スクリプト

`index.html` 側にUI変更を加えたら、コミット前に以下でテンプレートへ反映してください。

```bash
# 差分確認のみ（CIやフックが内部で使うのと同じチェック）
python scripts/sync_template.py check --index index.html --template templates/deed_motors_PC_v3_template.html

# index.html の内容をテンプレートへ同期（更新バッジは自動で除去される）
python scripts/sync_template.py sync --index index.html --template templates/deed_motors_PC_v3_template.html
```

バイリンガル版を編集した場合は `--index bilingual.html --template templates/deed_motors_PC_v3_BILINGUAL_template.html` を指定して同様に実行します。

## 価格データの自動更新

`scripts/scraper.py` がUNEGUI.MNから価格データを収集し、`scripts/build_html.py` がテンプレート + 価格データから `index.html` / `bilingual.html` を生成します。毎日UTC 23:00（モンゴル時間 朝7時頃）にGitHub Actions（`.github/workflows/scrape.yml`）で自動実行されるほか、GitHubの Actions タブから手動実行も可能です。
