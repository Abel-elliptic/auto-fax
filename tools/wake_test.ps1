<#
  スリープ復帰テスト（FAX自動送信の事前確認用）

  このPCが「スリープ中に、タスクスケジューラで指定時刻に自動で起きる」かを実際に確かめます。
  FAX送信や印刷はしません。テスト用タスクがすることは、ログファイルに時刻を1行書くことだけです。

  使い方（PowerShell。管理者でなくても可）:
    1) 登録   : powershell -ExecutionPolicy Bypass -File tools\wake_test.ps1 -Register -Minutes 10
       → 電源ケーブルをつないだまま、スタート → 電源 → スリープ にして、予定時刻を過ぎるまで触らない
    2) 確認   : powershell -ExecutionPolicy Bypass -File tools\wake_test.ps1 -Check
    3) 後片付け: powershell -ExecutionPolicy Bypass -File tools\wake_test.ps1 -Remove

  事前に「スリープ解除タイマーの許可」を（電源に接続）=有効 にしておく必要があります（README参照）。
  このスクリプトは電源設定を変更しません。
#>
param(
    [switch]$Register,
    [int]$Minutes = 10,
    [switch]$Check,
    [switch]$Remove,
    [switch]$Log,            # タスクから呼ばれる用（手動で使う必要はない）
    [string]$LogDir = 'C:\FAX\ログ'
)

$ErrorActionPreference = 'Stop'
$TaskName = 'FAX_wake_test'
$TaskPath = '\FAX\'
$LogFile = Join-Path $LogDir 'wake_test.log'
$StateFile = Join-Path $LogDir 'wake_test_予定.txt'

function Get-PowerLine {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $s = [System.Windows.Forms.SystemInformation]::PowerStatus.PowerLineStatus
        switch ($s.ToString()) { 'Online' { '電源接続' } 'Offline' { 'バッテリー' } default { '不明' } }
    } catch { '不明' }
}

function Get-WakeTimerSetting {
    # powercfg の出力は言語で変わるため、0x で始まる値（AC, DC の順）だけを取り出す
    $out = (powercfg /q SCHEME_CURRENT SUB_SLEEP RTCWAKE 2>&1 | Out-String)
    $vals = [regex]::Matches($out, '0x[0-9a-fA-F]{8}') | ForEach-Object { [Convert]::ToInt32($_.Value, 16) }
    $names = @{ 0 = '無効'; 1 = '有効'; 2 = '重要なタイマーのみ' }
    if ($vals.Count -ge 2) {
        return [pscustomobject]@{ AC = $vals[$vals.Count - 2]; DC = $vals[$vals.Count - 1]; ACName = $names[$vals[$vals.Count - 2]]; DCName = $names[$vals[$vals.Count - 1]] }
    }
    return $null
}

# ---- タスクから呼ばれた時: 1行書くだけ ----
if ($Log) {
    if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "`t実行`t" + (Get-PowerLine)
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    exit 0
}

if (-not ($Register -or $Check -or $Remove)) {
    Write-Host '使い方: -Register [-Minutes 10] / -Check / -Remove のどれかを付けて実行してください。' -ForegroundColor Yellow
    exit 2
}

# ---- 登録 ----
if ($Register) {
    if ($Minutes -lt 3 -or $Minutes -gt 180) { throw '-Minutes は 3〜180 の範囲で指定してください' }
    $wt = Get-WakeTimerSetting
    if ($wt) {
        Write-Host ('スリープ解除タイマーの許可: 電源に接続=' + $wt.ACName + ' / バッテリー=' + $wt.DCName)
        if ($wt.AC -eq 0) {
            Write-Host '  ⚠ 「電源に接続」が無効のため、このままではPCは起きないはずです。README の手順で「有効」にしてから登録してください。' -ForegroundColor Yellow
            Write-Host '    （無効のまま試して「起きない」ことを確認したい場合は、そのまま続けても構いません）'
        }
    }
    if ((Get-PowerLine) -ne '電源接続') {
        Write-Host '  ⚠ 電源ケーブルがつながっていないようです。テスト用タスクは電源接続時のみ動く設定です。' -ForegroundColor Yellow
    }
    if (-not (Test-Path -LiteralPath $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        Write-Host ('ログ用フォルダを作成しました: ' + $LogDir)
    }
    $at = (Get-Date).AddMinutes($Minutes)
    $at = $at.AddSeconds(-$at.Second)
    $script = $MyInvocation.MyCommand.Path
    $arg = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $script + '" -Log -LogDir "' + $LogDir + '"'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
    $trigger = New-ScheduledTaskTrigger -Once -At $at
    # WakeToRun=起こして実行 / 電源接続時のみ / 予定時刻を過ぎたら後から実行しない（起きたかどうかを正しく判定するため）
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    $principal = New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN + '\' + $env:USERNAME) -LogonType Interactive -RunLevel Limited
    try {
        Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'FAX自動送信の事前確認：スリープ復帰テスト（ログに1行書くだけ）' -Force | Out-Null
    } catch {
        Write-Host ('タスクを登録できませんでした: ' + $_.Exception.Message) -ForegroundColor Red
        Write-Host 'PowerShell を「管理者として実行」して、もう一度試してください。'
        exit 1
    }
    ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "`n" + $at.ToString('yyyy-MM-dd HH:mm:ss')) | Set-Content -LiteralPath $StateFile -Encoding UTF8
    Write-Host ''
    Write-Host ('テスト用タスクを登録しました: ' + $TaskPath + $TaskName + '  予定時刻 ' + $at.ToString('yyyy-MM-dd HH:mm')) -ForegroundColor Green
    Write-Host '次の手順:'
    Write-Host '  1. 電源ケーブルをつないだまま、スタート → 電源 → スリープ'
    Write-Host ('  2. ' + $at.AddMinutes(3).ToString('HH:mm') + ' 以降まで触らない（画面が点くか、ファンが回るか見ておくと参考になります）')
    Write-Host '  3. PCを起こして  powershell -ExecutionPolicy Bypass -File tools\wake_test.ps1 -Check'
    exit 0
}

# ---- 確認 ----
if ($Check) {
    if (-not (Test-Path -LiteralPath $StateFile)) { Write-Host '登録情報がありません。先に -Register を実行してください。' -ForegroundColor Yellow; exit 2 }
    $st = Get-Content -LiteralPath $StateFile -Encoding UTF8
    $registered = [datetime]::ParseExact($st[0], 'yyyy-MM-dd HH:mm:ss', $null)
    $scheduled = [datetime]::ParseExact($st[1], 'yyyy-MM-dd HH:mm:ss', $null)
    Write-Host ('登録 ' + $registered.ToString('MM/dd HH:mm:ss') + ' / 予定時刻 ' + $scheduled.ToString('MM/dd HH:mm:ss'))

    $runs = @()
    if (Test-Path -LiteralPath $LogFile) {
        $runs = Get-Content -LiteralPath $LogFile -Encoding UTF8 | ForEach-Object {
            $c = $_ -split "`t"
            try { [pscustomobject]@{ Time = [datetime]::ParseExact($c[0], 'yyyy-MM-dd HH:mm:ss', $null); Power = $c[2] } } catch { }
        } | Where-Object { $_.Time -ge $registered }
    }
    $info = $null
    try { $info = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $TaskPath } catch { }
    if ($info) { Write-Host ('タスク: 最終実行 ' + $info.LastRunTime + ' / 結果コード ' + $info.LastTaskResult + '（0=正常、267011=未実行）') }

    Write-Host ''
    Write-Host '--- 電源イベント（システムログ） ---'
    $ids = @{ 'Microsoft-Windows-Kernel-Power' = @(42, 107, 506, 507); 'Microsoft-Windows-Power-Troubleshooter' = @(1) }
    $events = @()
    try {
        $events = Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = $registered.AddMinutes(-1) } -ErrorAction Stop |
            Where-Object { $ids.ContainsKey($_.ProviderName) -and ($ids[$_.ProviderName] -contains $_.Id) } |
            Sort-Object TimeCreated
    } catch { Write-Host ('  読み取れません: ' + $_.Exception.Message) }
    $sleepIds = @(42, 506)   # 42=スリープ開始, 506=モダンスタンバイ開始
    $wakeIds = @(107, 507, 1) # 107=復帰, 507=モダンスタンバイ終了, 1=スリープ解除（解除の理由を含む）
    foreach ($e in $events) {
        $kind = if ($sleepIds -contains $e.Id -and $e.ProviderName -like '*Kernel-Power') { 'スリープ開始' } else { '復帰' }
        $msg = ($e.Message -split "`r?`n" | Where-Object { $_ -match '\S' } | Select-Object -First 4) -join ' / '
        Write-Host ('  ' + $e.TimeCreated.ToString('MM/dd HH:mm:ss') + '  ' + $kind + '  [' + $e.ProviderName.Replace('Microsoft-Windows-', '') + ' ' + $e.Id + ']  ' + $msg)
    }

    Write-Host ''
    Write-Host '--- 判定 ---'
    $onTime = @($runs | Where-Object { [math]::Abs(($_.Time - $scheduled).TotalMinutes) -le 3 })
    $slept = @($events | Where-Object { ($sleepIds -contains $_.Id) -and $_.ProviderName -like '*Kernel-Power' -and $_.TimeCreated -lt $scheduled })
    if ($onTime.Count -gt 0 -and $slept.Count -gt 0) {
        Write-Host ('成功：スリープ中に予定時刻 ' + $onTime[0].Time.ToString('HH:mm:ss') + ' に起きて実行されました（' + $onTime[0].Power + '）。') -ForegroundColor Green
        Write-Host '  上の「復帰」行の解除の理由（Wake Source）にタイマーやタスク名が出ていれば確実です。'
    } elseif ($onTime.Count -gt 0) {
        Write-Host '予定時刻に実行されましたが、その前にスリープした記録がありません。PCが起きていた可能性があり、スリープ復帰の確認にはなりません。' -ForegroundColor Yellow
    } elseif ($runs.Count -gt 0) {
        Write-Host ('実行はされましたが予定時刻からずれています（' + $runs[0].Time.ToString('HH:mm:ss') + '）。スリープ中には起きなかった可能性があります。') -ForegroundColor Yellow
    } else {
        Write-Host '予定時刻に実行されていません。スリープ中に起きなかった可能性が高いです。' -ForegroundColor Red
        Write-Host '  確認：スリープ解除タイマーの許可（電源に接続）が有効か / 電源ケーブルがつながっていたか / 予定時刻を過ぎてから起こしたか'
    }
    Write-Host '（この画面の内容をコピーして共有してください）'
    exit 0
}

# ---- 後片付け ----
if ($Remove) {
    $t = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
        Write-Host ('テスト用タスクを削除しました: ' + $TaskPath + $TaskName) -ForegroundColor Green
    } else {
        Write-Host 'テスト用タスクは登録されていません。'
    }
    if (Test-Path -LiteralPath $StateFile) { Remove-Item -LiteralPath $StateFile }
    Write-Host ('ログ ' + $LogFile + ' は残しています（不要なら手で削除してください）。')
    exit 0
}
