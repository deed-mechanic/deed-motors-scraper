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

# 二重起動の防止（手動実行と定時実行が重なると、同じファイルを同時に書き込んで壊れる）
$script:mutex = New-Object System.Threading.Mutex($false, "Global\DeedMotorsDailyScrape")
if (-not $script:mutex.WaitOne(0)) { Log "別の実行が進行中のため、今回は実行しません"; exit 0 }

# 実行中であることを記録する。強制終了（タスクの実行時間上限・電源断など）された場合、
# 「成功」のまま残らず、朝に LAST_STATUS.txt が「実行中」のままなら異常終了と分かる
$startTime = Get-Date
if (-not $DryRun) {
    Set-Content -Path $statusFile -Value ("{0}  実行中  開始しました（終了していない場合は異常終了の疑い）`r`nログ: {1}" -f $startTime.ToString("yyyy-MM-dd HH:mm"), $log) -Encoding UTF8
}
# 古いログの整理（30日より前のものを削除）
Get-ChildItem $logDir -Filter "run_*.log" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
# 全体の時間枠（タスクの実行時間上限8時間のうち7時間で打ち切り、公開処理の時間を残す）
$deadline = $startTime.AddHours(7)
function BudgetMin() { [math]::Min(300, [math]::Floor(($deadline - (Get-Date)).TotalMinutes - 20)) }

# VPN経由の通信かどうかを調べる。VPNの出口IPは多数の人が共有するためCloudflareに疑われやすく、
# 2026-11-24にNordVPN接続中で全ページが遮断された（切断後に回復）。インターネット向けの標準経路がVPNを通っていれば名前を返す
function VpnInUse() {
    try {
        $r = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop | Sort-Object { $_.RouteMetric + (Get-NetIPInterface -InterfaceIndex $_.ifIndex -AddressFamily IPv4).InterfaceMetric } | Select-Object -First 1
        $a = Get-NetAdapter -InterfaceIndex $r.ifIndex -ErrorAction Stop
        if (("{0} {1}" -f $a.Name, $a.InterfaceDescription) -match "VPN|Nord|Lynx|WireGuard|Wintun|TAP-|OpenVPN|Proton|WARP|AnyConnect|Mullvad|Express|Surfshark|Tailscale|ZeroTier") { return $a.Name }
    } catch { }
    return $null
}
$vpnName = VpnInUse
if ($vpnName) { Log ("⚠️ VPN({0})経由で通信しています。Cloudflareに遮断されやすいため、遮断された場合はVPNを切断するか、python.exeをVPNの対象外にしてください" -f $vpnName) }

# Playwrightのライブラリだけ更新されるとブラウザ本体が合わず起動できなくなる（過去に発生）。
# 実行前に必ず確認し、不足していれば公式の手順で導入する（導入済みなら何もしない）
# ライブラリのバージョンは requirements.txt で固定（勝手な更新で止まらないように）
if ((Run $py @("-m", "pip", "install", "-q", "-r", "requirements.txt")) -ne 0) { Finish $false "ライブラリの導入に失敗（ネット接続を確認）" }
if ((Run $py @("-m", "playwright", "install", "chromium")) -ne 0) { Finish $false "Chromiumの確認/導入に失敗（ネット接続を確認）" }

if (-not $DryRun) {
    if ((Run "git" @("pull", "--ff-only", "origin", "main")) -ne 0) { Finish $false "git pull失敗（ローカルに未コミットの変更がないか確認）" }
}

$dbPath = if ($DryRun) { Join-Path $logDir "dryrun_price_db.json" } else { "scripts/price_db.json" }
$scrapeArgs = @("scripts/scraper.py", "--output", $dbPath)
if ($DryRun) { $scrapeArgs += "--test" }
# 前回データの控え（取得後に「消えた車種」を確認するため）
$prevDb = Join-Path $logDir "prev_price_db.json"
if (-not $DryRun -and (Test-Path $dbPath)) { Copy-Item $dbPath $prevDb -Force }
$rc = Run $py ($scrapeArgs + @("--time-budget-min", (BudgetMin)))
# 失敗時は取得済みの車種を飛ばして再開する（--resume）
#  code=2（一部の車種だけ失敗）: 10分空けて最大2回
#  code=3（サイトに遮断されている＝Cloudflare）: 30分空けて、時間枠（開始から7時間）の残りがある限り繰り返す。
#   遮断は数時間で解けることがあるため。遮断中は保存しない（既存データ・更新日時は変更されない）
# 時間枠が残りわずかなら再試行せず、その時点の結果で終える
$attempt = 0
$blockedTries = 0
while ($rc -ne 0 -and -not $DryRun) {
    if ((BudgetMin) -le 40) { Log "時間枠が残りわずかのため再試行しません"; break }
    if ($rc -eq 3) {
        $blockedTries++
        Log "サイトに遮断されています(code=3)。30分後に再開します（遮断での再試行 $blockedTries回目）。VPN接続: $(if (VpnInUse) { '有り→切断してください' } else { '無し' })"
        Start-Sleep -Seconds 1800
    } elseif ($attempt -lt 2) {
        $attempt++
        Log "取得が完了しませんでした(code=$rc)。10分後に再開します（再試行 $attempt/2）"
        Start-Sleep -Seconds 600
    } else { break }
    $rc = Run $py ($scrapeArgs + @("--resume", "--time-budget-min", (BudgetMin)))
}
$partial = ($rc -eq 2)
if ($rc -eq 3) {
    $vpnNow = VpnInUse
    $hint = if ($vpnNow) { "VPN($vpnNow)に接続中です。VPNを切断するか、python.exeをVPNの対象外にしてください。" } else { "VPNは使っていません。回線自体が疑われている可能性があるため、別の回線（テザリング等）で試してください。" }
    Finish $false ("サイトに遮断され続け、今回は更新できませんでした（{0}回再試行）。データは前回のまま変更していません。{1}" -f $blockedTries, $hint)
}
if ($rc -ne 0 -and -not $partial) { Finish $false "スクレイピング失敗(code=$rc)。既存データは保持。ログ参照" }

$d = Get-Content $dbPath -Raw -Encoding UTF8 | ConvertFrom-Json
Log ("取得結果: {0}車種 {1}件 ({2})" -f $d.total_models, $d.total_records, $d.updated_at)
if ($DryRun) { Log "DryRun完了（HTML生成・コミット・プッシュは実施しない）"; exit 0 }

# 整合チェック（確認用。失敗しても公開は止めない）: メニューにあるのにデータが無い車種、前回から消えた車種を記録
if (Test-Path $prevDb) { Run $py @("scripts/check_consistency.py", "--old", $prevDb) | Out-Null } else { Run $py @("scripts/check_consistency.py") | Out-Null }

if ((Run $py @("scripts/build_html.py", "--template", "templates/deed_motors_PC_v3_template.html", "--db", "scripts/price_db.json", "--out", "index.html")) -ne 0) { Finish $false "HTML生成(日本語)失敗" }
if ((Run $py @("scripts/build_html.py", "--template", "templates/deed_motors_PC_v3_BILINGUAL_template.html", "--db", "scripts/price_db.json", "--out", "bilingual.html")) -ne 0) { Finish $false "HTML生成(バイリンガル)失敗" }

Run "git" @("add", "scripts/price_db.json", "index.html", "bilingual.html") | Out-Null
& git diff --staged --quiet
if ($LASTEXITCODE -eq 0) { Finish $true "取得成功（前回から変更なし）" }
$msg = "価格データ更新 " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm") + " UTC（ローカルPC取得）"
if ((Run "git" @("commit", "-m", $msg)) -ne 0) { Finish $false "commit失敗" }
if ((Run "git" @("pull", "--rebase", "origin", "main")) -ne 0) { Finish $false "rebase失敗（データはコミット済み。次回再試行）" }
if ((Run "git" @("push", "origin", "main")) -ne 0) { Finish $false "push失敗（データはコミット済み）" }
if ($partial) { Finish $false ("一部の車種が取得できず、その車種は前回データのまま公開 {0}車種 {1}件" -f $d.total_models, $d.total_records) }
Finish $true ("公開完了 {0}車種 {1}件" -f $d.total_models, $d.total_records)
