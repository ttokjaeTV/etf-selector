#!/usr/bin/env python3
"""amc_links.json 에 없는 마스터 종목의 운용사 공식 상세 URL 을 샌드박스에서 직접 수집한다 (브라우저 불필요, 2026-09-15 검증).

지원: KODEX(samsungfund API) · RISE(finder 서버렌더 표) · HANARO(fund-list?searchWord) · PLUS(카테고리 페이지) ·
      DB/마이티(db-asset 목록) · MIDAS(워드프레스 검색)
미지원(네이버 폴백 정상): 브이아이·흥국·교보악사·현대·대신·유리·트러스톤·아이엠·더제이·디에스·KCGI / TIGER·KIWOOM 은 index.html 내장 패턴
그 외(ACE·SOL·TIMEFOLIO·WON·1Q·KoAct·ASSETPLUS·IBK·BNK)는 스킬 문서 6-1 방법으로 수동.

사용: python scripts/fetch_amc_links.py [--apply]   # --apply 없으면 결과만 출력
"""
import argparse, json, re, sys, urllib.parse, requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"}
def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=25, **kw); r.raise_for_status(); return r
def strip(html): return re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", html))
def norm(n): return re.sub(r"[\s&;]|amp", "", n.replace("&amp;", "&")).lower()

def kodex(targets):
    out, n = {}, 1
    while True:
        r = requests.get(f"https://m.samsungfund.com/api/v1/kodex/product.do?ordrSort=DESC&ordrColm=NAV&pageNo={n}", headers=UA, timeout=25)
        if r.status_code == 429 or "Just a moment" in r.text[:300]:
            raise RuntimeError("samsungfund Cloudflare 429 — 짧은 시간 반복 호출 시 차단됨. 1~2시간 뒤 재시도하거나 스킬 6-1 KODEX 팁(브라우저)으로")
        j = r.json()
        if not j: break
        for it in j:
            if it["stkTicker"] in targets: out[it["stkTicker"]] = f"https://www.samsungfund.com/etf/product/view.do?id={it['fId']}"
        if n * len(j) >= int(j[0]["totalCnt"]): break
        n += 1
    return out

def rise(targets):
    h = get("https://www.riseetf.co.kr/prod/finder").text
    d = {norm(nm): i for i, nm in re.findall(r"finderDetail/([A-Za-z0-9]+)'\">([^<]+)</th>", h)}
    return {t: f"https://www.riseetf.co.kr/prod/finderDetail/{d[norm(nm)]}" for t, nm in targets.items() if norm(nm) in d}

def hanaro(targets):
    out = {}
    for t, nm in targets.items():
        h = get("https://www.hanaroetf.com/fund/fund-list", params={"searchWord": nm}).text
        for m in re.finditer(r"/fund/([A-F0-9]{16})", h):
            if norm(nm) in norm(strip(h[m.end():m.end() + 800])):
                out[t] = f"https://www.hanaroetf.com/fund/{m.group(1)}"; break
    return out

def plus(targets):
    out = {}
    # /product/overview 만 전 종목을 서버렌더로 나열한다 (카테고리 페이지는 JS 렌더)
    h = get("https://www.plusetf.co.kr/product/overview").text
    d = {norm(nm): n for n, nm in re.findall(r'detail\?n=(\d+)">([^<]+)</a>', h)}
    for t, nm in targets.items():
        if norm(nm) in d: out[t] = f"https://www.plusetf.co.kr/product/detail?n={d[norm(nm)]}"
    # 검증: 상세 title
    for t, u in list(out.items()):
        if norm(targets[t]) not in norm(get(u).text.split("</title>")[0]): out.pop(t)
    return out

def db(targets):
    h = get("https://db-asset.com/front/kr/fund/etf").text
    out = {}
    for m in re.finditer(r"fund/(\d{5})", h):
        ctx = norm(strip(h[m.start():m.start() + 600]))
        for t, nm in targets.items():
            key = norm(nm.replace("마이티 ", ""))
            if key in ctx: out[t] = f"https://db-asset.com/front/kr/fund/{m.group(1)}"
    return out

def midas(targets):
    out = {}
    for t, nm in targets.items():
        kw = nm.replace("MIDAS ", "")
        h = get("https://midasasset.com/", params={"s": kw}).text
        for u in set(re.findall(r'href="(https://midasasset\.com/fund/[^"]+)"', h)):
            if norm(kw) in norm(urllib.parse.unquote(u)): out[t] = u; break
    return out

HOUSES = {"KODEX": kodex, "RISE": rise, "HANARO": hanaro, "PLUS": plus, "마이티": db, "MIGHTY": db, "MIDAS": midas}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--date", default=None)
    a = ap.parse_args()
    master = json.load(open("data/krx_etf_master.json", encoding="utf-8"))
    links = json.load(open("data/amc_links.json", encoding="utf-8"))
    L = links["links"]; tickers = {e["ticker"] for e in master["etfs"]}
    gone = [t for t in L if t not in tickers]
    todo = {}
    for e in master["etfs"]:
        if e["ticker"] not in L and e["brand"] in HOUSES: todo.setdefault(e["brand"], {})[e["ticker"]] = e["name"]
    found = {}
    for b, tg in todo.items():
        try: r = HOUSES[b](tg)
        except Exception as ex: print(f"  {b} 실패: {ex}"); r = {}
        found.update(r)
        for t, nm in tg.items(): print(f"  {b} {t} {nm} → {r.get(t, '★ 미확보')}")
    print(f"폐지 링크 제거 대상 {len(gone)}: {gone}")
    if a.apply and (found or gone):
        for t in gone: L.pop(t)
        for t, u in found.items(): L[t] = u
        if a.date: links["meta"]["updated"] = a.date
        json.dump(links, open("data/amc_links.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("amc_links.json 갱신 완료 (meta.houses count 는 수동 확인)")

if __name__ == "__main__":
    main()
