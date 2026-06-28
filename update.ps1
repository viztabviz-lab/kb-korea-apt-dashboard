# 전국 아파트 시세 자동 수집 래퍼 (KB + 한국부동산원)
# 작업 스케줄러에서 이 스크립트를 주기 실행합니다.
# 부동산원 수집을 켜려면 환경변수 REB_API_KEY 를 설정하세요. (R-ONE OpenAPI 인증키)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$log = Join-Path $here "update.log"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

try {
    $out = python "$here\kb_korea.py" 2>&1 | Out-String
    if ($env:REB_API_KEY) {
        $out += python "$here\reb_korea.py" 2>&1 | Out-String
    } else {
        $out += "`r`n(부동산원 건너뜀: 환경변수 REB_API_KEY 미설정)"
    }
    Add-Content -Path $log -Value "[$stamp] OK`r`n$out" -Encoding UTF8
    Write-Host $out
} catch {
    Add-Content -Path $log -Value "[$stamp] ERROR: $_" -Encoding UTF8
    throw
}
