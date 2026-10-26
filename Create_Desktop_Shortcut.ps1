$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $projectDir 'Run_Market_Radar.bat'
$icon = Join-Path $projectDir 'Market_Radar.ico'
if (-not (Test-Path $launcher)) {
    Write-Host 'Tidak menemukan Run_Market_Radar.bat di folder ini.' -ForegroundColor Red
    Write-Host 'Pastikan script ini berada di folder project Market Radar.'
    Read-Host 'Tekan Enter untuk keluar'
    exit 1
}
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop 'Market Radar.lnk'
$wsh = New-Object -ComObject WScript.Shell
$link = $wsh.CreateShortcut($linkPath)
$link.TargetPath = $launcher
$link.WorkingDirectory = $projectDir
$link.Description = 'Buka Market Radar dashboard'
if (Test-Path $icon) { $link.IconLocation = "$icon,0" }
$link.Save()
Write-Host "Shortcut berhasil dibuat: $linkPath" -ForegroundColor Green
Write-Host 'Folder project jangan dipindahkan setelah shortcut dibuat.'
Read-Host 'Tekan Enter untuk selesai'
