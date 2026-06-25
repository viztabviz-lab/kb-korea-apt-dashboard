# -*- coding: utf-8 -*-
"""
한국부동산원(R-ONE) - 서울 아파트 시세(주택가격동향) 수집기
- 인증키 필요: 환경변수 REB_API_KEY (R-ONE OpenAPI 무료 발급)
  발급: https://www.reb.or.kr/r-one/  →  로그인 → OpenAPI 인증키 신청
- 출력: data/reb_seoul.json  (KB와 동일한 구조의 대시보드용 compact JSON)
        data/reb_seoul_시계열.csv (Tableau용 long-format)
실행: REB_API_KEY=xxxx python reb_seoul.py   (Windows: $env:REB_API_KEY="xxxx")

KB(kb_seoul.py)와 1:1로 비교하기 위해
  · 매매/전세 가격지수 = 주간(WK), 서울 + 25개 구
  · 매매/전세 평균가격 = 월간(MM), 서울 (단위 천원 → 만원으로 환산해 KB와 동일 단위)
부동산원은 '전세가율'을 OpenAPI로 공표하지 않아 해당 지표는 제외한다.
"""
import csv
import os
import sys
import json
import math
import datetime as dt
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
HEADERS = {"User-Agent": "Mozilla/5.0"}
HERE = Path(__file__).resolve().parent
OUT = HERE / "data"
OUT.mkdir(exist_ok=True)

KEY = os.environ.get("REB_API_KEY", "").strip()
if not KEY:
    sys.exit("환경변수 REB_API_KEY 가 비어 있습니다. R-ONE OpenAPI 인증키를 설정하세요.")

# (지표명, 거래구분, STATBL_ID, 주기코드)
INDEX_TABLES = [
    ("가격지수", "매매", "T244183132827305", "WK"),   # (주) 매매가격지수(아파트)
    ("가격지수", "전세", "T247713133046872", "WK"),   # (주) 전세가격지수(아파트)
]
AVG_TABLES = [
    ("평균가격", "매매", "A_2024_00060", "MM"),        # (월) 평균매매가격(아파트) · 천원
    ("평균가격", "전세", "A_2024_00064", "MM"),        # (월) 평균전세가격(아파트) · 천원
]

SEOUL_GU = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구",
    "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구",
    "구로구", "금천구", "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구",
]
GU_ORDER = ["서울"] + SEOUL_GU
GU_SET = set(SEOUL_GU)
PAGE = 1000


def call(statbl_id, cycle, *, cls_id=None, pindex=1, psize=PAGE):
    params = {"KEY": KEY, "STATBL_ID": statbl_id, "DTACYCLE_CD": cycle,
              "Type": "json", "pIndex": pindex, "pSize": psize}
    if cls_id is not None:
        params["CLS_ID"] = cls_id
    r = requests.get(BASE, params=params, headers=HEADERS, verify=False, timeout=60)
    body = r.json()
    if "SttsApiTblData" not in body:
        raise RuntimeError(f"{statbl_id} 응답 오류: {body.get('RESULT', body)}")
    total, rows = 0, []
    for blk in body["SttsApiTblData"]:
        if "head" in blk:
            for h in blk["head"]:
                if "list_total_count" in h:
                    total = h["list_total_count"]
        if "row" in blk:
            rows = blk["row"]
    return total, rows


def discover_regions(statbl_id, cycle, want):
    """최신 기간 스냅샷에서 {지역명: CLS_ID} 매핑을 만든다.
    want='all' → 서울 + 25개 구, want='seoul' → 서울만"""
    total, _ = call(statbl_id, cycle, psize=1)
    last_page = max(1, math.ceil(total / PAGE))
    _, rows = call(statbl_id, cycle, pindex=last_page, psize=PAGE)
    region_map = {}
    for r in rows:
        full = r.get("CLS_FULLNM") or ""
        leaf = r.get("CLS_NM") or ""
        if not full.startswith("서울"):
            continue
        if full == "서울":
            region_map["서울"] = r["CLS_ID"]
        elif want == "all" and leaf in GU_SET:
            region_map[leaf] = r["CLS_ID"]
    return region_map


def parse_date(cycle, row):
    if cycle == "MM":                     # WRTTIME = YYYYMM
        s = str(row["WRTTIME_IDTFR_ID"])
        return dt.date(int(s[:4]), int(s[4:6]), 1).isoformat()
    desc = str(row["WRTTIME_DESC"])       # 주간: 'YYYY-MM-DD'
    y, m, d = desc.split("-")
    return dt.date(int(y), int(m), int(d)).isoformat()


def fetch_region_series(statbl_id, cycle, name, cls_id, 지표, 거래, to_manwon):
    recs = []
    pindex = 1
    while True:
        total, rows = call(statbl_id, cycle, cls_id=cls_id, pindex=pindex)
        for r in rows:
            v = r.get("DTA_VAL")
            if v is None:
                continue
            val = float(v) / 10.0 if to_manwon else float(v)  # 천원 -> 만원
            recs.append({
                "날짜": parse_date(cycle, r),
                "지역명": name,
                "지표": 지표,
                "거래구분": 거래,
                "값": round(val, 4),
            })
        if pindex * PAGE >= total:
            break
        pindex += 1
    return recs


def gather():
    all_recs = []
    for 지표, 거래, sid, cycle in INDEX_TABLES:
        print(f"· {거래} {지표}(주간) {sid} ...")
        rmap = discover_regions(sid, cycle, want="all")
        for name in GU_ORDER:
            cid = rmap.get(name)
            if cid is None:
                continue
            all_recs += fetch_region_series(sid, cycle, name, cid, 지표, 거래, to_manwon=False)
    for 지표, 거래, sid, cycle in AVG_TABLES:
        print(f"· {거래} {지표}(월간) {sid} ...")
        rmap = discover_regions(sid, cycle, want="seoul")
        cid = rmap.get("서울")
        if cid is not None:
            all_recs += fetch_region_series(sid, cycle, "서울", cid, 지표, 거래, to_manwon=True)
    return all_recs


def write_csv(recs):
    path = OUT / "reb_seoul_시계열.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["날짜", "지역명", "지표", "거래구분", "값"])
        w.writeheader()
        w.writerows(sorted(recs, key=lambda r: (r["지표"], r["거래구분"], r["지역명"], r["날짜"])))
    return path


def latest_snapshot(recs):
    latest = {}
    for r in recs:
        k = (r["지표"], r["거래구분"], r["지역명"])
        if k not in latest or r["날짜"] > latest[k]["날짜"]:
            latest[k] = r
    return latest


def build_series(recs, 지표, 거래):
    sub = [r for r in recs if r["지표"] == 지표 and r["거래구분"] == 거래]
    dates = sorted({r["날짜"] for r in sub})
    regions = [g for g in GU_ORDER if any(r["지역명"] == g for r in sub)]
    idx = {(r["날짜"], r["지역명"]): r["값"] for r in sub}
    out = {"dates": dates}
    for g in regions:
        out[g] = [idx.get((d, g)) for d in dates]
    return out


def write_json(recs):
    path = OUT / "reb_seoul.json"
    latest = latest_snapshot(recs)
    summary = []
    for gu in GU_ORDER:
        def g(지표, 거래):
            r = latest.get((지표, 거래, gu))
            return r["값"] if r else None
        ma = g("평균가격", "매매")
        je = g("평균가격", "전세")
        summary.append({
            "region": gu,
            "매매평균억": round(ma / 10000, 2) if ma else None,   # 만원 -> 억
            "전세평균억": round(je / 10000, 2) if je else None,
            "매매지수": g("가격지수", "매매"),
            "전세지수": g("가격지수", "전세"),
        })
    weekly_dates = sorted({r["날짜"] for r in recs if r["지표"] == "가격지수"})
    monthly_dates = sorted({r["날짜"] for r in recs if r["지표"] == "평균가격"})
    payload = {
        "source": "한국부동산원 R-ONE 전국주택가격동향조사(아파트)",
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "asof": {
            "weekly": weekly_dates[-1] if weekly_dates else None,
            "monthly": monthly_dates[-1] if monthly_dates else None,
        },
        "summary": summary,
        "series": {
            "매매지수": build_series(recs, "가격지수", "매매"),
            "전세지수": build_series(recs, "가격지수", "전세"),
            "매매평균": build_series(recs, "평균가격", "매매"),
            "전세평균": build_series(recs, "평균가격", "전세"),
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return path


def main():
    print(f"[부동산원 서울 아파트 시세 수집] {dt.datetime.now():%Y-%m-%d %H:%M}")
    recs = gather()
    if not recs:
        sys.exit("수집된 레코드가 없습니다. 인증키/통계표 ID를 확인하세요.")
    csv_path = write_csv(recs)
    json_path = write_json(recs)
    last = max(r["날짜"] for r in recs)
    print(f"\n완료 · 레코드 {len(recs):,}건 · 최신 기준일 {last}")
    print(f"  - {csv_path}")
    print(f"  - {json_path}")


if __name__ == "__main__":
    main()
