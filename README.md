# 서울 아파트 시세 비교 · KB vs 한국부동산원

**KB부동산**과 **한국부동산원(R-ONE)** 두 기관의 서울 아파트 시세를
같은 구조로 수집해 한 화면에서 비교하는 대시보드입니다. (GitHub Pages)

## 수집 항목
### KB부동산 (`kb_seoul.py`, 인증키 불필요)
| 지표 | 범위 | 주기 | 단위 |
|---|---|---|---|
| 매매/전세 가격지수 | 서울 + 25개 구 | 주간 | 지수(2022.1=100) |
| 전세가율 | 서울 + 25개 구 | 월간 | % |
| 매매/전세 평균가격 | 서울 (시도 단위) | 월간 | 만원 |

### 한국부동산원 (`reb_seoul.py`, **인증키 필요**)
| 지표 | 범위 | 주기 | 단위 |
|---|---|---|---|
| 매매/전세 가격지수 | 서울 + 25개 구 | 주간 | 지수(2021.6=100) |
| 매매/전세 평균가격 | 서울 (시도 단위) | 월간 | 만원(천원→환산) |

> - 구별 **평균가격**은 두 API 모두 시도 단위까지만 제공 → 구 단위는 가격지수로 비교.
> - 부동산원은 **전세가율**을 OpenAPI로 공표하지 않아 미수집.
> - 두 기관은 표본·산정방식이 달라 절대수준에 차이가 있습니다(부동산원 < KB).

## 결과물 (`data/`)
- `kb_seoul.json` / `reb_seoul.json` — 대시보드용 compact JSON(동일 구조)
- `kb_seoul_시계열.csv` / `reb_seoul_시계열.csv` — Tableau용 long-format
- `KB_서울아파트시세.xlsx` — 요약(최신) + 지표별 wide 시트

## 인증키 발급 (부동산원, 무료)
1. <https://www.reb.or.kr/r-one/> 로그인/회원가입
2. **OpenAPI → 인증키 신청** → 발급된 키 복사
3. 사용처에 등록:
   - **로컬**: 환경변수 `REB_API_KEY`
     ```powershell
     $env:REB_API_KEY = "발급받은_키"
     ```
   - **GitHub Actions**: 저장소 **Settings → Secrets and variables → Actions →
     New repository secret** 에 이름 `REB_API_KEY` 로 등록

## 수동 실행
```powershell
python kb_seoul.py
$env:REB_API_KEY = "발급받은_키"; python reb_seoul.py
```

## 자동화 (등록됨)
Windows 작업 스케줄러 작업 **`KB_서울아파트시세_주간수집`** 이 매주 금요일 18:30
(KB 주간 발표일)에 `kb_seoul.py`를 실행합니다. 로그는 `update.log`.

```powershell
# 상태 확인
Get-ScheduledTask -TaskName "KB_서울아파트시세_주간수집"
# 지금 즉시 1회 실행
Start-ScheduledTask -TaskName "KB_서울아파트시세_주간수집"
# 등록 해제
Unregister-ScheduledTask -TaskName "KB_서울아파트시세_주간수집" -Confirm:$false
```

## API 참고
### KB부동산
- Base: `https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/`
- 엔드포인트: `priceIndex`(가격지수) · `avgPrc`(평균가격) · `dealCntstTnantRato`(전세가율)
- 공통 파라미터: `월간주간구분코드`(01월/02주) · `매물종별구분`(01아파트) · `매매전세코드`(01매매/02전세) · `지역코드`(서울=1100000000)
- 성공 코드: `dataBody.resultCode == 11000`

### 한국부동산원 R-ONE
- Base: `https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do`
- 파라미터: `KEY`(인증키) · `STATBL_ID`(통계표) · `DTACYCLE_CD`(MM월/WK주) · `CLS_ID`(지역) · `Type=json` · `pIndex`/`pSize`(최대 1,000)
- 통계표 ID: 주간 매매지수 `T244183132827305` · 주간 전세지수 `T247713133046872` · 월 평균매매 `A_2024_00060` · 월 평균전세 `A_2024_00064`
- 통계표 목록: `SttsApiTbl.do` · 성공 코드: `RESULT.CODE == INFO-000`
- 인증키 없으면 표당 5건 샘플만 반환
