"""구성종목 TOP10 수집 → data/holdings.json

네이버 모바일 ETF 구성종목 API(https://m.stock.naver.com/api/etf/{단축코드}/constituent)에서
마스터(data/krx_etf_master.json)의 전 종목 상위 10개 구성종목과 비중을 받아 holdings.json을 다시 만든다.
표준 라이브러리만 쓴다.

  python3 scripts/fetch_holdings.py                 # 수집 → data/holdings.json 교체
  python3 scripts/fetch_holdings.py --out /tmp/h.json  # 드라이런
  python3 scripts/fetch_holdings.py --date 2026-10-13  # meta.fetched 날짜 지정(기본 오늘)

- 형식은 기존과 같다: {"meta":{...}, "data":{"단축코드": [[종목명, 비중%], ... 최대 10]}}
- 받기 실패한 종목은 기존 holdings.json 값을 그대로 둔다(실패 목록은 마지막에 출력).
- 마스터에 없는 종목(상장폐지)은 뺀다.
- 네이버 구성종목은 보통 전 영업일 기준(PDF)이다.
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "krx_etf_master.json"
HOLD = ROOT / "data" / "holdings.json"
URL = "https://m.stock.naver.com/api/etf/{code}/constituent"
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"


def fetch(code, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(URL.format(code=code), headers={
                "User-Agent": UA, "Referer": f"https://m.stock.naver.com/domestic/stock/{code}/total"})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode("utf-8"))
            rows = sorted(d.get("result") or [], key=lambda x: -(x.get("constituentWeight") or 0))[:10]
            out = []
            for x in rows:
                name = (x.get("itemName") or "").strip()
                w = x.get("constituentWeight")
                if not name or w is None:
                    continue
                out.append([name, round(float(w), 2)])
            return code, out, None
        except Exception as e:  # noqa: BLE001
            err = str(e)[:80]
            time.sleep(1.5 * (i + 1))
    return code, None, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HOLD))
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    master = json.loads(MASTER.read_text(encoding="utf-8"))
    codes = [e["ticker"] for e in master["etfs"]]
    old = {}
    if HOLD.exists():
        old = json.loads(HOLD.read_text(encoding="utf-8")).get("data", {})

    data, failed, empty = {}, [], []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for code, rows, err in ex.map(fetch, codes):
            if rows is None:
                failed.append((code, err))
                if code in old:
                    data[code] = old[code]
            elif not rows:
                empty.append(code)
                if code in old:
                    data[code] = old[code]
            else:
                data[code] = rows
    # 마스터 순서 유지
    data = {c: data[c] for c in codes if c in data}

    changed = sum(1 for c, v in data.items() if old.get(c) != v)
    new_codes = [c for c in data if c not in old]
    res = {
        "meta": {
            "source": "네이버 모바일 ETF constituent API",
            "fetched": a.date,
            "count": len(data),
            "note": "code: [[종목명, 비중%] x 최대10]. 네이버 PDF는 보통 전영업일 기준",
        },
        "data": data,
    }
    if len(data) < len(codes) * 0.8:
        print(f"중단: 수집 {len(data)}/{len(codes)}종으로 너무 적습니다. 파일을 바꾸지 않습니다.")
        sys.exit(1)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장 {a.out}: {len(data)}/{len(codes)}종 · 바뀐 종목 {changed} · 새로 생긴 종목 {len(new_codes)} · 기준 {a.date}")
    if failed:
        print(f"받기 실패 {len(failed)}종(기존 값 유지): " + ", ".join(f"{c}({e})" for c, e in failed[:15]))
    if empty:
        print(f"구성종목 없음 {len(empty)}종(기존 값 유지 또는 비움): " + ", ".join(empty[:20]))


if __name__ == "__main__":
    main()
