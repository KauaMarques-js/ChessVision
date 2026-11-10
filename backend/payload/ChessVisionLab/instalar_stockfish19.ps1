$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$homeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$engineDir = Join-Path $homeDir 'engine'
New-Item -Path $engineDir -ItemType Directory -Force | Out-Null
$already = Get-ChildItem -Path $engineDir -Recurse -Filter 'stockfish*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($already) {
    Write-Host "Stockfish encontrado: $($already.FullName)"
    exit 0
}
$zip = Join-Path $env:TEMP 'chessvision-stockfish19-x64.zip'
# Official GitHub asset corresponding to Stockfish 19 (sf_19).
$url = 'https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip'
Write-Host 'Baixando Stockfish 19 oficial (aproximadamente 80 MB)...'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $engineDir -Force
Remove-Item $zip -Force
$bin = Get-ChildItem $engineDir -Recurse -Filter 'stockfish*.exe' | Select-Object -First 1
if (-not $bin) { throw 'Nenhum executavel Stockfish foi encontrado no arquivo.' }
Write-Host "Stockfish 19 instalado em: $($bin.FullName)"
