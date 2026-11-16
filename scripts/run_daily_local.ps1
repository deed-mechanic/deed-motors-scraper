# DEED MOTORS 市場価格 日次更新（このPCで実行）
# GitHub ActionsのIPはUNEGUI.MNのCloudflareに遮断されるため、遮断されないこのPCで取得して公開する。
# 使い方: powershell -File scripts\run_daily_local.ps1 [-DryRun]
#   -DryRun: 取得は harrier のみ・一時ファイルへ保存し、コミット/プッシュはしない（動作確認用）
param([switch]$DryRun)

$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:USERPROFILE "deed-scrape-logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("run_" + (Get-Date -Format "yyyyMMdd_HHmm") + ".log")
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$py = "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"

function Log($m) { $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m; Add-Content -Path $log -Value $line -Encoding UTF8; Write-Host $line }
# 出力を1行ずつリアルタイムでログに追記する（長時間のスクレイピングの進捗を確認できる）
function Run($exe, $argList) {
    & $exe @argList 2>&1 | ForEach-Object { Add-Content -Path $log -Value ("" + $_) -Encoding UTF8 }
    return $LASTEXITCODE
}

# 実行結果を1か所に残す（毎朝これを見れば、成功/失敗とその理由が分かる）
$statusFile = Join-Path $logDir "LAST_STATUS.txt"
function Finish($ok, $msg) {
    $state = if ($ok) { "成功" } else { "失敗" }
    Set-Content -Path $statusFile -Value ("{0}  {1}  {2}`r`nログ: {3}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $state, $msg, $log) -Encoding UTF8
    Log ("結果: {0} {1}" -f $state, $msg)
    if ($ok) { exit 0 } else { exit 1 }
}

Set-Location $repo
Log "開始 DryRun=$DryRun"

# Playwrightのライブラリだけ更新されるとブラウザ本体が合わず起動できなくなる（過去に発生）。
# 実行前に必ず確認し、不足していれば公式の手順で導入する（導入済みなら何もしない）
if ((Run $py @("-m", "playwright", "install", "chromium")) -ne 0) { Finish $false "Chromiumの確認/導入に失敗（ネット接続を確認）" }

if (-not $DryRun) {
    if ((Run "git" @("pull", "--ff-only", "origin", "main")) -ne 0) { Finish $false "git pull失敗（ローカルに未コミットの変更がないか確認）" }
}

$dbPath = if ($DryRun) { Join-Path $logDir "dryrun_price_db.json" } else { "scripts/price_db.json" }
$scrapeArgs = @("scripts/scraper.py", "--output", $dbPath)
if ($DryRun) { $scrapeArgs += "--test" }
$rc = Run $py $scrapeArgs
if ($rc -ne 0) { Finish $false "スクレイピング異常終了(code=$rc)。既存データは保持。ログ参照" }

$d = Get-Content $dbPath -Raw -Encoding UTF8 | ConvertFrom-Json
Log ("取得結果: {0}車種 {1}件 ({2})" -f $d.total_models, $d.total_records, $d.updated_at)
if ($DryRun) { Log "DryRun完了（HTML生成・コミット・プッシュは実施しない）"; exit 0 }

if ((Run $py @("scripts/build_html.py", "--template", "templates/deed_motors_PC_v3_template.html", "--db", "scripts/price_db.json", "--out", "index.html")) -ne 0) { Finish $false "HTML生成(日本語)失敗" }
if ((Run $py @("scripts/build_html.py", "--template", "templates/deed_motors_PC_v3_BILINGUAL_template.html", "--db", "scripts/price_db.json", "--out", "bilingual.html")) -ne 0) { Finish $false "HTML生成(バイリンガル)失敗" }

Run "git" @("add", "scripts/price_db.json", "index.html", "bilingual.html") | Out-Null
& git diff --staged --quiet
if ($LASTEXITCODE -eq 0) { Finish $true "取得成功（前回から変更なし）" }
$msg = "価格データ更新 " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm") + " UTC（ローカルPC取得）"
if ((Run "git" @("commit", "-m", $msg)) -ne 0) { Finish $false "commit失敗" }
if ((Run "git" @("pull", "--rebase", "origin", "main")) -ne 0) { Finish $false "rebase失敗（データはコミット済み。次回再試行）" }
if ((Run "git" @("push", "origin", "main")) -ne 0) { Finish $false "push失敗（データはコミット済み）" }
Finish $true ("公開完了 {0}車種 {1}件" -f $d.total_models, $d.total_records)
