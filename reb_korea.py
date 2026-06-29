# -*- coding: utf-8 -*-
"""
한국부동산원(R-ONE) - 전국(17개 시도) 아파트 시세(주택가격동향) 수집기
- 인증키 필요: 환경변수 REB_API_KEY (R-ONE OpenAPI 무료 발급)
  발급: https://www.reb.or.kr/r-one/  →  로그인 → OpenAPI 인증키 신청
- 출력: data/reb_korea.json  (KB와 동일한 구조의 대시보드용 compact JSON)
        data/reb_korea_시계열.csv (Tableau용 long-format)
실행: REB_API_KEY=xxxx python reb_korea.py   (Windows: $env:REB_API_KEY="xxxx")

KB(kb_korea.py)와 1:1로 비교하기 위해
  · 매매/전세 가격지수 = 주간(WK), 전국 + 17개 시도
  · 매매/전세 평균가격 = 월간(MM), 전국 + 17개 시도 (단위 천원 → 만원으로 환산)
부동산원은 '전세가율'을 OpenAPI로 공표하지 않아 해당 지표는 제외한다.
"""
import csv
import os
import sys
import json
import math
import time
import datetime as dt
from pathlib import Path

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# R-ONE 서버는 연속 호출 시 간헐적으로 연결을 끊는다(RemoteDisconnected).
# 세션 재사용 + 백오프 재시도로 견고하게 처리한다.
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
_retry = Retry(total=5, connect=5, read=5, backoff_factor=1.5,
               status_forcelist=(500, 502, 503, 504),
               allowed_methods=frozenset(["GET"]))
SESSION.mount("https://", HTTPAdapter(max_retries=_retry))
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

# 부동산원 지역명(짧은 형태/긴 형태 모두) → 표준 시도명 매핑.
SIDO_CANON = {
    "전국": "전국",
    "서울": "서울", "서울특별시": "서울",
    "부산": "부산", "부산광역시": "부산",
    "대구": "대구", "대구광역시": "대구",
    "인천": "인천", "인천광역시": "인천",
    "광주": "광주", "광주광역시": "광주",
    "대전": "대전", "대전광역시": "대전",
    "울산": "울산", "울산광역시": "울산",
    "세종": "세종", "세종특별자치시": "세종", "세종시": "세종",
    "경기": "경기", "경기도": "경기",
    "강원": "강원", "강원도": "강원", "강원특별자치도": "강원",
    "충북": "충북", "충청북도": "충북",
    "충남": "충남", "충청남도": "충남",
    "전북": "전북", "전라북도": "전북", "전북특별자치도": "전북",
    "전남": "전남", "전라남도": "전남",
    "경북": "경북", "경상북도": "경북",
    "경남": "경남", "경상남도": "경남",
    "제주": "제주", "제주도": "제주", "제주특별자치도": "제주",
}
SIDO_ORDER = ["전국", "서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산",
              "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
SLUG = {
    "서울": "seoul", "경기": "gyeonggi", "인천": "incheon", "부산": "busan",
    "대구": "daegu", "광주": "gwangju", "대전": "daejeon", "울산": "ulsan",
    "세종": "sejong", "강원": "gangwon", "충북": "chungbuk", "충남": "chungnam",
    "전북": "jeonbuk", "전남": "jeonnam", "경북": "gyeongbuk", "경남": "gyeongnam",
    "제주": "jeju",
}
PAGE = 1000


def call(statbl_id, cycle, *, cls_id=None, pindex=1, psize=PAGE):
    params = {"KEY": KEY, "STATBL_ID": statbl_id, "DTACYCLE_CD": cycle,
              "Type": "json", "pIndex": pindex, "pSize": psize}
    if cls_id is not None:
        params["CLS_ID"] = cls_id
    last_err = None
    for attempt in range(4):                       # 어댑터 재시도 외 추가 방어
        try:
            r = SESSION.get(BASE, params=params, verify=False, timeout=60)
            body = r.json()
            break
        except (requests.exceptions.RequestException, ValueError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"{statbl_id} 호출 실패(재시도 초과): {last_err}")
    if "SttsApiTblData" not in body:
        raise RuntimeError(f"{statbl_id} 응답 오류: {body.get('RESULT', body)}")
    time.sleep(0.2)                                # 서버 부하 완화(연결 끊김 방지)
    total, rows = 0, []
    for blk in body["SttsApiTblData"]:
        if "head" in blk:
            for h in blk["head"]:
                if "list_total_count" in h:
                    total = h["list_total_count"]
        if "row" in blk:
            rows = blk["row"]
    return total, rows


def discover_regions(statbl_id, cycle):
    """최신 기간 스냅샷에서 {표준시도명: CLS_ID} 매핑(전국 + 17개 시도).
    시도 레벨은 CLS_FULLNM 이 단일 지역명(공백 없음)인 행으로 식별한다."""
    total, _ = call(statbl_id, cycle, psize=1)
    last_page = max(1, math.ceil(total / PAGE))
    _, rows = call(statbl_id, cycle, pindex=last_page, psize=PAGE)
    region_map = {}
    for r in rows:
        full = (r.get("CLS_FULLNM") or "").strip()
        if " " in full:                 # '서울 강남구' 같은 시군구는 제외
            continue
        canon = SIDO_CANON.get(full)
        if canon and canon not in region_map:
            region_map[canon] = r["CLS_ID"]
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
        rmap = discover_regions(sid, cycle)
        for name in SIDO_ORDER:
            cid = rmap.get(name)
            if cid is None:
                continue
            all_recs += fetch_region_series(sid, cycle, name, cid, 지표, 거래, to_manwon=False)
    for 지표, 거래, sid, cycle in AVG_TABLES:
        print(f"· {거래} {지표}(월간) {sid} ...")
        rmap = discover_regions(sid, cycle)
        for name in SIDO_ORDER:
            cid = rmap.get(name)
            if cid is None:
                continue
            all_recs += fetch_region_series(sid, cycle, name, cid, 지표, 거래, to_manwon=True)
    return all_recs


def write_csv(recs):
    path = OUT / "reb_korea_시계열.csv"
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
    regions = [g for g in SIDO_ORDER if any(r["지역명"] == g for r in sub)]
    idx = {(r["날짜"], r["지역명"]): r["값"] for r in sub}
    out = {"dates": dates}
    for g in regions:
        out[g] = [idx.get((d, g)) for d in dates]
    return out


def write_json(recs):
    path = OUT / "reb_korea.json"
    latest = latest_snapshot(recs)
    summary = []
    for sido in SIDO_ORDER:
        def g(지표, 거래):
            r = latest.get((지표, 거래, sido))
            return r["값"] if r else None
        ma = g("평균가격", "매매")
        je = g("평균가격", "전세")
        summary.append({
            "region": sido,
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


# ---------------------------------------------------------------------------
# 시군구 단위(드릴다운): 부동산원은 시군구 단위로 매매/전세 가격지수를 제공한다
# (평균가격·전세가율은 시군구 단위 미제공). 시도별로 data/sg/reb/<slug>.json 생성.
# CLS_FULLNM 이 '<시도> <시군구>' 처럼 공백을 포함하면 시군구 레벨로 본다.
# ---------------------------------------------------------------------------

def sigungu_name(tokens):
    """CLS_FULLNM 토큰('시도>권역>…>시군구')에서 표시용 시군구명 생성.
    실제 행정단위(…시/군/구)만 남겨 KB 명명과 맞춘다. 권역(경부1권)·
    지역(강북지역) 같은 중간 묶음 레벨은 제외한다.
    예) '서울>강북지역>마포구'→'마포구', '충북>청주시>상당구'→'청주시 상당구',
        '경기>경부1권>수원시>장안구'→'수원시 장안구', '서울>강남지역'→'' (제외)"""
    parts = [t for t in tokens[1:] if t.endswith(("시", "군", "구"))]
    return " ".join(parts)


def discover_sigungu(statbl_id, cycle):
    """{시도: {시군구명: CLS_ID}} — CLS_FULLNM 은 '>' 로 구분된 계층 경로"""
    total, _ = call(statbl_id, cycle, psize=1)
    last_page = max(1, math.ceil(total / PAGE))
    _, rows = call(statbl_id, cycle, pindex=last_page, psize=PAGE)
    out = {}
    for r in rows:
        full = (r.get("CLS_FULLNM") or "").strip()
        toks = [t.strip() for t in full.split(">") if t.strip()]
        if len(toks) < 2:
            continue
        parent = SIDO_CANON.get(toks[0])
        if not parent:
            continue
        name = sigungu_name(toks)
        if not name:
            continue
        out.setdefault(parent, {}).setdefault(name, r["CLS_ID"])
    return out


def build_series_named(recs, 지표, 거래):
    sub = [r for r in recs if r["지표"] == 지표 and r["거래구분"] == 거래]
    dates = sorted({r["날짜"] for r in sub})
    regions = []
    for r in sub:
        if r["지역명"] not in regions:
            regions.append(r["지역명"])
    idx = {(r["날짜"], r["지역명"]): r["값"] for r in sub}
    out = {"dates": dates}
    for g in regions:
        out[g] = [idx.get((d, g)) for d in dates]
    return out


def write_sigungu():
    """시도별 시군구 파일 작성 후 [{name, slug, regions}] 반환"""
    base = OUT / "sg" / "reb"
    base.mkdir(parents=True, exist_ok=True)
    # 인덱스 표별로 한 번씩만 시군구 CLS_ID를 발견(추가 스냅샷 호출 절약)
    sg_maps = {}
    for 지표, 거래, sid, cycle in INDEX_TABLES:
        sg_maps[(sid, 거래)] = discover_sigungu(sid, cycle)
    info = []
    for name in SIDO_ORDER:
        if name == "전국":
            continue
        try:
            recs = []
            for 지표, 거래, sid, cycle in INDEX_TABLES:
                gumap = sg_maps[(sid, 거래)].get(name, {})
                for gu, cid in gumap.items():
                    recs += fetch_region_series(sid, cycle, gu, cid, 지표, 거래, to_manwon=False)
            if not recs:
                continue
            weekly = sorted({r["날짜"] for r in recs})
            payload = {
                "asof": {"weekly": weekly[-1] if weekly else None},
                "series": {
                    "매매지수": build_series_named(recs, "가격지수", "매매"),
                    "전세지수": build_series_named(recs, "가격지수", "전세"),
                },
            }
            with open(base / f"{SLUG[name]}.json", "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            # 태블로용 long-format CSV (대시보드는 JSON, 다운로드는 CSV)
            with open(base / f"{SLUG[name]}.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=["날짜", "시도", "시군구", "지표", "거래구분", "값"])
                w.writeheader()
                for r in sorted(recs, key=lambda r: (r["지표"], r["거래구분"], r["지역명"], r["날짜"])):
                    w.writerow({"날짜": r["날짜"], "시도": name, "시군구": r["지역명"],
                                "지표": r["지표"], "거래구분": r["거래구분"], "값": r["값"]})
            n = len(payload["series"]["매매지수"]) - 1
            info.append({"name": name, "slug": SLUG[name], "regions": n, "rows": len(recs)})
            print(f"  · {name}: 시군구 {n}개")
        except Exception as e:                 # 한 시도가 실패해도 나머지는 계속
            print(f"  · {name}: 시군구 수집 실패 → 건너뜀 ({e})")
    return info


def write_manifest(recs, sg_info, updated):
    """다운로더 페이지(download.html)용 파일 목록 manifest"""
    def sz(rel):
        p = OUT / rel
        return p.stat().st_size if p.exists() else 0

    items = [
        {"source": "한국부동산원", "scope": "전국", "name": "전국·시도 시계열",
         "file": "data/reb_korea_시계열.csv", "format": "CSV",
         "bytes": sz("reb_korea_시계열.csv"),
         "detail": f"전국+17개 시도 · {len(recs):,}행 · 매매/전세 지수·평균가 (long-format)"},
    ]
    for s in sg_info:
        items.append({
            "source": "한국부동산원", "scope": "시군구", "name": f"{s['name']} 시군구",
            "file": f"data/sg/reb/{s['slug']}.csv", "format": "CSV",
            "bytes": sz(f"sg/reb/{s['slug']}.csv"),
            "detail": f"{s['name']} {s['regions']}개 시군구 · {s.get('rows',0):,}행 · 매매/전세 지수 (long-format)",
        })
    payload = {"source": "한국부동산원", "updated": updated, "items": items}
    with open(OUT / "downloads_reb.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def main():
    print(f"[부동산원 전국 아파트 시세 수집] {dt.datetime.now():%Y-%m-%d %H:%M}")
    recs = gather()
    if not recs:
        sys.exit("수집된 레코드가 없습니다. 인증키/통계표 ID를 확인하세요.")
    csv_path = write_csv(recs)
    json_path = write_json(recs)
    last = max(r["날짜"] for r in recs)
    print(f"\n완료 · 레코드 {len(recs):,}건 · 최신 기준일 {last}")
    print(f"  - {csv_path}")
    print(f"  - {json_path}")
    print("· 시군구 단위(드릴다운) 수집 ...")
    sg_info = write_sigungu()
    sg_total = sum(s["regions"] for s in sg_info)
    print(f"  - data/sg/reb/*.json (시군구 총 {sg_total}개)")
    write_manifest(recs, sg_info, last)
    print("  - data/downloads_reb.json")


if __name__ == "__main__":
    main()
