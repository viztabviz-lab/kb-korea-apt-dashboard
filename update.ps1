# KB 서울 아파트 시세 자동 수집 래퍼
# 작업 스케줄러에서 이 스크립트를 주기 실행합니다.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$log = Join-Path $here "update.log"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

try {
    $out = python "$here\kb_seoul.py" 2>&1 | Out-String
    Add-Content -Path $log -Value "[$stamp] OK`r`n$out" -Encoding UTF8
    Write-Host $out
} catch {
    Add-Content -Path $log -Value "[$stamp] ERROR: $_" -Encoding UTF8
    throw
}
