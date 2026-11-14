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
$py = "C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"

function Log($m) { $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m; Add-Content -Path $log -Value $line -Encoding UTF8; Write-Host $line }
function Run($exe, $argList) {
    $out = & $exe @argList 2>&1 | Out-String
    Add-Content -Path $log -Value $out -Encoding UTF8
    return $LASTEXITCODE
}

Set-Location $repo
Log "開始 DryRun=$DryRun"

if (-not $DryRun) {
    if ((Run "git" @("pull", "--ff-only", "origin", "main")) -ne 0) { Log "git pull 失敗。中止"; exit 1 }
}

$dbPath = if ($DryRun) { Join-Path $logDir "dryrun_price_db.json" } else { "scripts/price_db.json" }
$scrapeArgs = @("scripts/scraper.py", "--output", $dbPath)
if ($DryRun) { $scrapeArgs += "--test" }
$rc = Run $py $scrapeArgs
if ($rc -ne 0) { Log "スクレイピング異常終了(code=$rc)。既存データを保持して中止"; exit 1 }

$d = Get-Content $dbPath -Raw -Encoding UTF8 | ConvertFrom-Json
Log ("取得結果: {0}車種 {1}件 ({2})" -f $d.total_models, $d.total_records, $d.updated_at)
if ($DryRun) { Log "DryRun完了（HTML生成・コミット・プッシュは実施しない）"; exit 0 }

if ((Run $py @("scripts/build_html.py", "--template", "templates/deed_motors_PC_v3_template.html", "--db", "scripts/price_db.json", "--out", "index.html")) -ne 0) { Log "HTML生成(日本語)失敗。中止"; exit 1 }
if ((Run $py @("scripts/build_html.py", "--template", "templates/deed_motors_PC_v3_BILINGUAL_template.html", "--db", "scripts/price_db.json", "--out", "bilingual.html")) -ne 0) { Log "HTML生成(バイリンガル)失敗。中止"; exit 1 }

Run "git" @("add", "scripts/price_db.json", "index.html", "bilingual.html") | Out-Null
& git diff --staged --quiet
if ($LASTEXITCODE -eq 0) { Log "変更なし。終了"; exit 0 }
$msg = "価格データ更新 " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm") + " UTC（ローカルPC取得）"
if ((Run "git" @("commit", "-m", $msg)) -ne 0) { Log "commit失敗"; exit 1 }
if ((Run "git" @("pull", "--rebase", "origin", "main")) -ne 0) { Log "rebase失敗。中止"; exit 1 }
if ((Run "git" @("push", "origin", "main")) -ne 0) { Log "push失敗"; exit 1 }
Log "公開完了"
exit 0
