# 전국 아파트 시세 비교 · KB vs 한국부동산원

**KB부동산**과 **한국부동산원(R-ONE)** 두 기관의 **전국 17개 시도** 아파트 시세를
같은 구조로 수집해 한 화면에서 비교하는 대시보드입니다. (GitHub Pages)

> 대상 지역: 전국 + 17개 시도(서울·경기·인천·부산·대구·광주·대전·울산·세종·강원·충북·충남·전북·전남·경북·경남·제주)

## 수집 항목
### KB부동산 (`kb_korea.py`, 인증키 불필요)
| 지표 | 범위 | 주기 | 단위 |
|---|---|---|---|
| 매매/전세 가격지수 | 전국 + 17개 시도 | 주간 | 지수(2022.1=100) |
| 매매/전세 평균가격 | 전국 + 17개 시도 | 월간 | 만원 |
| 전세가율 | 전국 + 17개 시도 | 월간 | % |

### 한국부동산원 (`reb_korea.py`, **인증키 필요**)
| 지표 | 범위 | 주기 | 단위 |
|---|---|---|---|
| 매매/전세 가격지수 | 전국 + 17개 시도 | 주간 | 지수(2021.6=100) |
| 매매/전세 평균가격 | 전국 + 17개 시도 | 월간 | 만원(천원→환산) |

> - 부동산원은 **전세가율**을 OpenAPI로 공표하지 않아 미수집.
> - 두 기관은 표본·산정방식이 달라 절대수준에 차이가 있습니다(부동산원 < KB).

## 결과물 (`data/`)
- `kb_korea.json` / `reb_korea.json` — 대시보드용 compact JSON(동일 구조)
- `kb_korea_시계열.csv` / `reb_korea_시계열.csv` — Tableau용 long-format
- `KB_전국아파트시세.xlsx` — 요약(최신) + 지표별 wide 시트

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
python kb_korea.py
$env:REB_API_KEY = "발급받은_키"; python reb_korea.py
```

## 자동화
GitHub Actions(`.github/workflows/update.yml`)가 매주 금요일 18:30 KST
(KB 주간 발표일)에 두 수집기를 실행하고 데이터를 갱신/배포합니다.
로컬에서 작업 스케줄러로 돌리려면 `update.ps1` 을 주기 실행하세요(로그: `update.log`).

## API 참고
### KB부동산
- Base: `https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/`
- 엔드포인트: `priceIndex`(가격지수) · `avgPrc`(평균가격) · `dealCntstTnantRato`(전세가율)
- 공통 파라미터: `월간주간구분코드`(01월/02주) · `매물종별구분`(01아파트) · `매매전세코드`(01매매/02전세)
- 최상위 호출(지역코드 미지정)이 전국/광역집계/17개 시도를 한 번에 반환
- 성공 코드: `dataBody.resultCode == 11000`

### 한국부동산원 R-ONE
- Base: `https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do`
- 파라미터: `KEY`(인증키) · `STATBL_ID`(통계표) · `DTACYCLE_CD`(MM월/WK주) · `CLS_ID`(지역) · `Type=json` · `pIndex`/`pSize`(최대 1,000)
- 통계표 ID: 주간 매매지수 `T244183132827305` · 주간 전세지수 `T247713133046872` · 월 평균매매 `A_2024_00060` · 월 평균전세 `A_2024_00064`
- 시도 식별: 응답의 `CLS_FULLNM` 이 공백 없는 단일 지역명인 행이 시도 레벨
- 통계표 목록: `SttsApiTbl.do` · 성공 코드: `RESULT.CODE == INFO-000`
- 인증키 없으면 표당 5건 샘플만 반환
