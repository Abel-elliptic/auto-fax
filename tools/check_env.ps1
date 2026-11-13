<#
  FAX自動送信 環境チェック（読み取り専用）

  このPCのプリンター・FAXドライバー・ポート・Python・スリープ設定を一覧表示します。
  設定の変更、印刷、FAX送信は一切行いません。

  実行方法（PowerShell）:
    powershell -ExecutionPolicy Bypass -File tools\check_env.ps1
#>
param(
    [string]$DeviceIP = '10.203.101.230',
    [string]$LogDir = 'C:\FAX\ログ'
)

$ErrorActionPreference = 'Continue'
$lines = New-Object System.Collections.Generic.List[string]
$faxPattern = 'FAX|Fax|fax|ファクス|ファックス|ART EX|FUJIFILM|Apeos|Fuji'
# FAXドライバーと判定する条件（faxjob/printer_win.py の looks_like_fax と同じ考え方）
$faxOnlyPattern = '(?i)fax|ファクス|ファックス|art ex'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

function Write-Line([string]$text = '', [string]$color = '') {
    $lines.Add($text)
    if ($color) { Write-Host $text -ForegroundColor $color } else { Write-Host $text }
}
function Write-Section([string]$title) {
    Write-Line ''
    Write-Line ('=== ' + $title + ' ===') 'Cyan'
}
function Write-Table($rows, [string]$highlight) {
    if (-not $rows) { Write-Line '  (なし)'; return }
    $text = ($rows | Format-Table -AutoSize | Out-String -Width 300).TrimEnd()
    foreach ($l in $text -split "`r?`n") {
        if ($highlight -and $l -match $highlight) { Write-Line ('* ' + $l) 'Yellow' } else { Write-Line ('  ' + $l) }
    }
}

Write-Line ('FAX自動送信 環境チェック  ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) 'Green'
Write-Line '（読み取りのみ。設定変更・印刷・送信はしていません）'

Write-Section 'Windows'
try {
    $os = Get-CimInstance Win32_OperatingSystem
    Write-Line ('  ' + $os.Caption + '  版:' + $os.Version + '  ' + $os.OSArchitecture)
} catch { Write-Line ('  取得できません: ' + $_.Exception.Message) 'Red' }
Write-Line ('  CPU種別: ' + $env:PROCESSOR_ARCHITECTURE + '  （ARM64 の場合、ART EX ダイレクトファクスドライバーに既知の注意事項あり）')
Write-Line ('  ユーザー: ' + $env:USERNAME + '  コンピューター名: ' + $env:COMPUTERNAME)

Write-Section ('複合機 ' + $DeviceIP + ' への疎通')
try {
    $ok = Test-Connection -ComputerName $DeviceIP -Count 2 -Quiet
    if ($ok) { Write-Line '  ping 応答あり' 'Green' } else { Write-Line '  ping 応答なし' 'Red' }
} catch { Write-Line ('  確認できません: ' + $_.Exception.Message) 'Red' }

Write-Section 'プリンター一覧（* = FAX/富士フイルム関連の可能性）'
try {
    $printers = Get-Printer | Sort-Object Name | Select-Object Name, DriverName, PortName, Type
    Write-Table $printers $faxPattern
    $fujiPrinters = @($printers | Where-Object { ($_.Name + ' ' + $_.DriverName) -match $faxPattern })
    $faxPrinters = @($fujiPrinters | Where-Object { ($_.Name + ' ' + $_.DriverName) -match $faxOnlyPattern })
    $paperPrinters = @($fujiPrinters | Where-Object { ($_.Name + ' ' + $_.DriverName) -notmatch $faxOnlyPattern })
    Write-Line ''
    if ($faxPrinters.Count -gt 0) {
        Write-Line ('  → FAXドライバーらしいプリンター: ' + (($faxPrinters | ForEach-Object { $_.Name }) -join ' / ')) 'Yellow'
    } else {
        Write-Line '  → 名前・ドライバー名に FAX/ファクス/ART EX を含むプリンターはありません。ダイレクトファクスドライバーは未導入の可能性があります。' 'Yellow'
    }
    foreach ($pp in $paperPrinters) {
        Write-Line ('  → 「' + $pp.Name + '」は紙に印刷するプリンターと思われます。faxjob print で指定すると紙が出ます（FAXは出ません）。') 'Yellow'
    }
    if ($printers | Where-Object { $_.Name -eq 'Microsoft Print to PDF' }) {
        Write-Line '  → 「Microsoft Print to PDF」あり（Step 2 の確認に使います）' 'Green'
    } else {
        Write-Line '  → 「Microsoft Print to PDF」が見つかりません（Step 2 の確認に必要）' 'Red'
    }
} catch { Write-Line ('  取得できません: ' + $_.Exception.Message) 'Red' }

Write-Section 'プリンタードライバー（* = FAX/富士フイルム関連の可能性）'
try {
    $drivers = Get-PrinterDriver | Sort-Object Name | ForEach-Object {
        $v = $_.DriverVersion
        $ver = if ($v) { '{0}.{1}.{2}.{3}' -f (($v -shr 48) -band 0xffff), (($v -shr 32) -band 0xffff), (($v -shr 16) -band 0xffff), ($v -band 0xffff) } else { '' }
        [pscustomobject]@{ Name = $_.Name; Manufacturer = $_.Manufacturer; Version = $ver; Environment = $_.PrinterEnvironment }
    }
    Write-Table $drivers $faxPattern
} catch { Write-Line ('  取得できません: ' + $_.Exception.Message) 'Red' }

Write-Section ('プリンターポート（* = ' + $DeviceIP + ' 宛て）')
try {
    $ports = Get-PrinterPort | Sort-Object Name | Select-Object Name, PrinterHostAddress, PortNumber, Description
    Write-Table $ports ([regex]::Escape($DeviceIP))
} catch { Write-Line ('  取得できません: ' + $_.Exception.Message) 'Red' }

Write-Section 'Python'
foreach ($cmd in @('py', 'python')) {
    $c = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($c) {
        $ver = (& $cmd -V 2>&1 | Out-String).Trim()
        Write-Line ('  ' + $cmd + ': ' + $ver + '  (' + $c.Source + ')')
    } else {
        Write-Line ('  ' + $cmd + ': 見つかりません')
    }
}

Write-Section '電源（スリープからの自動復帰に関係）'
try {
    Write-Line '  [使用できるスリープ状態] powercfg /a'
    (powercfg /a 2>&1 | Out-String).TrimEnd() -split "`r?`n" | ForEach-Object { Write-Line ('    ' + $_) }
} catch { Write-Line ('  取得できません: ' + $_.Exception.Message) 'Red' }
try {
    Write-Line '  [スリープ解除タイマーの許可] powercfg /q SCHEME_CURRENT SUB_SLEEP RTCWAKE'
    (powercfg /q SCHEME_CURRENT SUB_SLEEP RTCWAKE 2>&1 | Out-String).TrimEnd() -split "`r?`n" | ForEach-Object { Write-Line ('    ' + $_) }
    Write-Line '    （0x00000000=無効 / 0x00000001=有効 / 0x00000002=重要なタイマーのみ。AC=電源接続時、DC=バッテリー時）'
} catch { Write-Line ('  取得できません: ' + $_.Exception.Message) 'Red' }
Write-Line '  [現在のスリープ解除タイマー] powercfg /waketimers'
if ($isAdmin) {
    try {
        (powercfg /waketimers 2>&1 | Out-String).TrimEnd() -split "`r?`n" | ForEach-Object { Write-Line ('    ' + $_) }
    } catch { Write-Line ('    取得できません: ' + $_.Exception.Message) 'Red' }
} else {
    Write-Line '    （管理者権限が必要なため省略。見る場合は PowerShell を「管理者として実行」してこのスクリプトを実行）'
}

Write-Line ''
if (Test-Path -LiteralPath $LogDir) {
    $out = Join-Path $LogDir ('check_env_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt')
    $lines | Out-File -LiteralPath $out -Encoding utf8
    Write-Line ('結果を保存しました: ' + $out) 'Green'
} else {
    Write-Line ('（' + $LogDir + ' が無いため、ファイルには保存していません。画面の内容をコピーして共有してください）')
}
