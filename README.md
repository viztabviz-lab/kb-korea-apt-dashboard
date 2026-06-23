# KB 서울 아파트 시세 자동 수집

KB부동산 데이터허브(`data-api.kbland.kr`)의 **주택가격동향조사** 통계를
인증키 없이 받아 서울 아파트 시세 시계열을 출력·자동화합니다.

## 수집 항목
| 지표 | 범위 | 주기 | 단위 |
|---|---|---|---|
| 매매/전세 가격지수 | 서울 + 25개 구 | 주간 | 지수(2022.1=100) |
| 전세가율 | 서울 + 25개 구 | 월간 | % |
| 매매/전세 평균가격 | 서울 (시도 단위) | 월간 | 만원 |

> 구별 **평균가격(원)**은 KB API가 시도 단위까지만 제공해 미수집입니다.
> 구 단위는 가격지수·전세가율로 비교합니다.

## 결과물 (`data/`)
- `kb_seoul_시계열.csv` — Tableau용 long-format (날짜·지역명·지표·거래구분·값)
- `KB_서울아파트시세.xlsx` — 요약(최신) 시트 + 지표별 wide 시트(행=날짜, 열=지역)

## 수동 실행
```powershell
python kb_seoul.py
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
- Base: `https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/`
- 엔드포인트: `priceIndex`(가격지수) · `avgPrc`(평균가격) · `dealCntstTnantRato`(전세가율)
- 공통 파라미터: `월간주간구분코드`(01월/02주) · `매물종별구분`(01아파트) · `매매전세코드`(01매매/02전세) · `지역코드`(서울=1100000000)
- 성공 코드: `dataBody.resultCode == 11000`
