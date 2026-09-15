#!/usr/bin/env python3
"""KRX 직접수집 JSON(fetch_krx.py 산출물) + KOFIA 실부담비용 스냅샷으로 data/krx_etf_master.json 을 재빌드한다.

- 매칭 키: 단축코드. 기존 종목은 분류/플래그 보존, 메타·시세만 갱신
- 신규 종목: ETF_분류_마스터_룰셋 의사코드로 자동 분류 (+ --override JSON 으로 수동 지정)
- 총보수: KOFIA 총보수_kofia 가 있으면 우선
- 출력: indent=1, ensure_ascii=False, etfs[] 순서 = KRX 기본정보 행 순서

사용: python scripts/build_master.py --basic krx_basic_YYYYMMDD.json --price krx_price_YYYYMMDD.json \
        --kofia 실부담비용_YYYY-MM-DD.json --base /tmp/base.json --out data/krx_etf_master.json --date YYYY-MM-DD
"""
import argparse, json, re, sys

def num(s, default=0):
    if s is None: return default
    s = str(s).replace(",", "").strip()
    if s in ("", "-"): return default
    try:
        return float(s)
    except ValueError:
        return default

FIELD_ORDER = ["ticker","isin","name","fullName","englishName","fundHouse","brand","listingDate","indexName","market",
 "assetClass","replication","taxType","expenseRatio","marketCap","nav","tradingValue","group","groupName","region",
 "isCoveredCall","isLeveraged","isInverse","isTDF","isTRF","isTIF","isBondMix","isBondMixCC","isShortTerm","isActive",
 "isDividend","isHedged","isCarbon","isMixedAsset","isPensionSafeAsset","pensionTradable","specialTag"]
FLAGS = [f for f in FIELD_ORDER if f.startswith("is") and f != "isin"]

CC = re.compile(r"커버드콜|CC\b|타겟위클리|프리미엄|위클리커버드콜", re.I)

def classify(r):
    """룰셋 의사코드. r = 기본정보 행(엑셀 헤더). 반환 (group, flags dict, region)"""
    n = r["한글종목약명"]; asset = r["기초자산분류"]; mkt = r["기초시장분류"]; tax = r["과세유형"]
    f = {k: False for k in FLAGS}
    f["isCoveredCall"] = bool(CC.search(n))
    f["isLeveraged"] = "레버리지" in n or "2X" in n.upper() and "인버스" not in n
    f["isInverse"] = "인버스" in n
    f["isActive"] = "액티브" in n or "액티브" in r["복제방법"]
    f["isHedged"] = "(H)" in n or "헤지" in n
    f["isCarbon"] = "탄소" in n
    f["isTDF"] = "TDF" in n; f["isTRF"] = "TRF" in n; f["isTIF"] = "TIF" in n
    bondmix = bool(re.search(r"채권혼합|미국채혼합|국채혼합|채권플러스", n))
    region = "한국" if mkt == "국내" else region_of(n)
    g = None
    if bondmix and f["isCoveredCall"]: g = "G"; f["isBondMixCC"] = True; f["isPensionSafeAsset"] = True
    elif bondmix: g = "F"; f["isBondMix"] = True; f["isPensionSafeAsset"] = True; region = "미국" if mkt != "국내" or "미국채" in n else region
    elif tax == "배당소득세(부동산)": g = "K"
    elif asset == "원자재" or "탄소배출권" in n: g = "L"
    elif re.search(r"TDF|TRF|TIF|우선증권|멀티에셋|자산배분|월간헤지|주식혼합", n):
        g = "M"; f["isMixedAsset"] = True
        if f["isTDF"] or f["isTIF"] or "TRF3070" in n: f["isPensionSafeAsset"] = True
        if f["isTDF"]: region = "기타"
    elif re.search(r"롱숏|ETF선물", n) and "미국달러" not in n: g = "N"
    elif "미국달러" in n or "미국머니마켓" in n or ("일본엔" in n and "선물" in n) or (asset == "통화" and mkt != "국내"): g = "J"
    elif re.search(r"CD금리|KOFR|머니마켓|단기채권|초단기채|단기금리|CD1년", n): g = "I"; f["isShortTerm"] = True; f["isPensionSafeAsset"] = True
    elif asset == "채권": g = "H"; f["isPensionSafeAsset"] = True
    elif tax == "비과세":
        g = "A2" if re.search(r"고배당|배당|주주환원|주주가치", n) else "A1"
        f["isDividend"] = g == "A2"
    elif asset == "주식" and mkt in ("해외", "국내&해외"): g = "E" if f["isCoveredCall"] else "D"
    elif asset == "주식" and mkt == "국내": g = "C" if f["isCoveredCall"] else "B"
    else: g = "_애매"
    return g, f, region

def region_of(n):
    for k, v in [("미국", "미국"), ("중국", "중국"), ("차이나", "중국"), ("일본", "일본"), ("인도", "인도"), ("유럽", "유럽"),
                 ("베트남", "베트남"), ("대만", "대만"), ("글로벌", "글로벌"), ("선진국", "글로벌"), ("신흥국", "신흥국"), ("코리아", "한국")]:
        if k in n: return v
    return "글로벌"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--basic", required=True); ap.add_argument("--price", required=True)
    ap.add_argument("--kofia", required=True); ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--date", required=True)
    ap.add_argument("--override", default=None, help="신규 종목 수동 지정 JSON {ticker:{group,region,flags...}}")
    ap.add_argument("--changelog", default=None)
    a = ap.parse_args()

    basic = json.load(open(a.basic, encoding="utf-8")); price = {r["종목코드"]: r for r in json.load(open(a.price, encoding="utf-8"))}
    kof = json.load(open(a.kofia, encoding="utf-8")); kdata = kof["data"]; kbasis = kof["meta"]["basis"]
    base = json.load(open(a.base, encoding="utf-8")); old = {e["ticker"]: e for e in base["etfs"]}
    ov = json.load(open(a.override, encoding="utf-8")) if a.override else {}
    group_names = {k: v["name"] for k, v in base["groups"].items()}

    etfs, new, gone, kofia_fix, no_kofia, no_price = [], [], [], [], [], []
    for r in basic:
        t = r["단축코드"]; p = price.get(t)
        meta = dict(isin=r["표준코드"], name=r["한글종목약명"], fullName=r["한글종목명"], englishName=r["영문종목명"],
                    listingDate=r["상장일"], indexName=r["기초지수명"], market=r["기초시장분류"], assetClass=r["기초자산분류"],
                    replication=r["복제방법"], taxType=r["과세유형"], fundHouse=r["운용사"], expenseRatio=round(num(r["총보수"]), 4))
        if p:
            mc = int(num(p["시가총액"])); nav = int(round(num(p["순자산가치(NAV)"]) * num(p["상장좌수"]))); tv = int(num(p["거래대금"]))
        else:
            mc = nav = tv = 0; no_price.append((t, r["한글종목약명"], r["상장일"]))
        if t in old:
            e = dict(old[t]); e.update(meta); e.update(marketCap=mc, nav=nav, tradingValue=tv)
        else:
            g, f, region = classify(r)
            o = ov.get(t, {})
            g = o.get("group", g); region = o.get("region", region)
            for k in FLAGS:
                if k in o: f[k] = o[k]
            brand = o.get("brand", r["한글종목약명"].split()[0])
            e = dict(ticker=t, **meta, brand=brand, marketCap=mc, nav=nav, tradingValue=tv, group=g,
                     groupName=group_names.get(g, g), region=region, **f,
                     pensionTradable=o.get("pensionTradable", not (f["isLeveraged"] or f["isInverse"])),
                     specialTag=o.get("specialTag", "TDF (적격)" if f["isTDF"] else None))
            new.append(e)
        # KOFIA 총보수 보정
        k = kdata.get(t)
        if k and k.get("총보수_kofia") not in (None, 0):
            kv = round(float(k["총보수_kofia"]), 4)
            if abs(kv - e["expenseRatio"]) > 1e-9:
                kofia_fix.append((t, e["name"], e["expenseRatio"], kv)); e["expenseRatio"] = kv
        elif t not in old or not k:
            no_kofia.append((t, e["name"]))
        # 필드 순서 정규화 (기존 종목의 추가 필드는 뒤에 유지)
        ordered = {k: e[k] for k in FIELD_ORDER if k in e}
        ordered.update({k: v for k, v in e.items() if k not in ordered})
        etfs.append(ordered)
    present = {r["단축코드"] for r in basic}
    gone = [(t, old[t]["name"], old[t]["group"]) for t in old if t not in present]

    # groupStats
    gs = {}
    for e in etfs:
        g = gs.setdefault(e["group"], {"count": 0, "totalMarketCap": 0}); g["count"] += 1; g["totalMarketCap"] += e["marketCap"]
    base["groupStats"] = {k: gs.get(k, {"count": 0, "totalMarketCap": 0}) for k in base["groupStats"]}
    for k in gs:
        if k not in base["groupStats"]: base["groupStats"][k] = gs[k]
    base["etfs"] = etfs
    base["meta"]["dataDate"] = a.date; base["meta"]["lastUpdate"] = a.date; base["meta"]["totalETFs"] = len(etfs)
    base["meta"]["expenseRatioSource"] = f"KRX 기본정보(기본) + KOFIA 공시 {kbasis}(불일치 시 우선)"
    if a.changelog: base["meta"]["changeLog"].append({"date": a.date, "change": a.changelog})

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=1)

    print(f"총 {len(etfs)}종 / 신규 {len(new)} / 폐지 {len(gone)} / KOFIA 보정 {len(kofia_fix)} / KOFIA 미수록 {len(no_kofia)} / 시세없음 {len(no_price)}")
    for e in new: print("  NEW", e["ticker"], e["name"], "→", e["group"], e["region"], {k for k in FLAGS if e[k]})
    for g in gone: print("  GONE", *g)
    for x in kofia_fix: print("  FEE", *x)
    for x in no_kofia: print("  NOKOFIA", *x)
    for x in no_price: print("  NOPRICE", *x)
    amb = [e for e in new if e["group"] == "_애매"]
    if amb: print("★ 애매 분류 있음 — override 필요"); sys.exit(2)

if __name__ == "__main__":
    main()
