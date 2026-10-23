# PowerShell skript na nahratie projektu z Windows PC na dosku KD240
# Pouzitie:
#   .\scripts\upload_to_board.ps1 -BoardIp 192.168.1.50
#   alebo
#   .\scripts\upload_to_board.ps1 -BoardIp 100.x.y.z (Tailscale)

param(
    [Parameter(Mandatory=$false)]
    [string]$BoardIp,

    [Parameter(Mandatory=$false)]
    [string]$User = "ubuntu",

    [Parameter(Mandatory=$false)]
    [string]$RemoteDir = "/home/ubuntu/kd240-tsn-sync",

    [Parameter(Mandatory=$false)]
    [switch]$IncludeReference
)

if (-not $BoardIp) {
    $BoardIp = Read-Host "Zadaj IP adresu dosky KD240 (napr. 192.168.1.50 alebo Tailscale IP)"
}

if (-not $BoardIp) {
    Write-Error "IP adresa dosky je povinna!"
    exit 1
}

$ProjectDir = (Get-Item $PSScriptRoot).Parent.FullName
Write-Host "Kopirujem projekt z $ProjectDir na ${User}@${BoardIp}:${RemoteDir} ..." -ForegroundColor Cyan

# Vytvor cielovy adresar na doske
ssh "${User}@${BoardIp}" "mkdir -p ${RemoteDir}"

# Kopirovanie suborov cez SCP (vylucenie .git, docasnych suborov a reference)
$excludeList = @(".git", "__pycache__", "*.pyc", ".pytest_cache", "*.log", "*.csv")
if (-not $IncludeReference) {
    $excludeList += "reference"
}
$items = Get-ChildItem -Path $ProjectDir -Exclude $excludeList

foreach ($item in $items) {
    Write-Host "  -> Nahravam $($item.Name)..."
    scp -r "$($item.FullName)" "${User}@${BoardIp}:${RemoteDir}/"
}

# Nastavenie prav na spustanie skriptov na doske
Write-Host "Nastavujem prava na spustenie skriptov (chmod +x)..." -ForegroundColor Cyan
ssh "${User}@${BoardIp}" "chmod +x ${RemoteDir}/scripts/*.sh ${RemoteDir}/tools/*.py"

Write-Host "Hotovo! Projekt je uspesne nahraty na doske." -ForegroundColor Green
Write-Host "Na doske mozes projekt spustit:" -ForegroundColor Yellow
Write-Host "  ssh ${User}@${BoardIp}"
Write-Host "  cd ${RemoteDir}"
Write-Host "  ./scripts/run_motor_cli.sh"
