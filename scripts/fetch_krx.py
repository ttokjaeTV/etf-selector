#!/usr/bin/env python3
"""KRX 정보데이터시스템에서 ETF 전종목 기본정보(MDCSTAT04601)·전종목 시세(MDCSTAT04301)를
엑셀 없이 JSON으로 직접 수집한다. 컬럼명은 KRX 엑셀 다운로드와 동일한 한글 헤더로 변환한다.

사용: python scripts/fetch_krx.py [--date YYYYMMDD] [--out DIR]
자격증명: KRX_ID/KRX_PW 환경변수 또는 KRX_ENV_FILE / 알려진 경로의 krx.env (값은 절대 출력하지 않음)
"""
import argparse, datetime as dt, json, os, sys, time
import requests

KNOWN_ENV = [
    os.environ.get("KRX_ENV_FILE", ""),
    "/sessions/exciting-relaxed-wozniak/mnt/.secrets/krx.env",
    os.path.expanduser("~/Desktop/Claude/.secrets/krx.env"),
    r"C:\Users\이상준\Desktop\Claude\.secrets\krx.env",
]
def load_env():
    if os.environ.get("KRX_ID") and os.environ.get("KRX_PW"):
        return "env"
    for cand in [c for c in KNOWN_ENV if c]:
        # 마운트 경로 후보
        for base in [cand] + [os.path.join(d, ".secrets", "krx.env") for d in _mnt_dirs()]:
            if os.path.isfile(base):
                with open(base, encoding="utf-8-sig") as f:  # BOM 대응
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip())
                if os.environ.get("KRX_ID") and os.environ.get("KRX_PW"):
                    return base
    return None

def _mnt_dirs():
    out = []
    for root in ("/sessions",):
        if os.path.isdir(root):
            for s in os.listdir(root):
                m = os.path.join(root, s, "mnt")
                if os.path.isdir(m):
                    out.append(m)
    return out

URL_JSON = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
    "X-Requested-With": "XMLHttpRequest",
}

# KRX JSON 컬럼 → 엑셀 헤더
BASIC_MAP = [
    ("ISU_CD", "표준코드"), ("ISU_SRT_CD", "단축코드"), ("ISU_NM", "한글종목명"), ("ISU_ABBRV", "한글종목약명"),
    ("ISU_ENG_NM", "영문종목명"), ("LIST_DD", "상장일"), ("ETF_OBJ_IDX_NM", "기초지수명"), ("IDX_CALC_INST_NM1", "지수산출기관"),
    ("IDX_CALC_INST_NM2", "추적배수"), ("ETF_REPLICA_METHD_TP_CD", "복제방법"), ("IDX_MKT_CLSS_NM", "기초시장분류"),
    ("IDX_ASST_CLSS_NM", "기초자산분류"), ("LIST_SHRS", "상장좌수"), ("COM_ABBRV", "운용사"), ("CU_QTY", "CU수량"),
    ("ETF_TOT_FEE", "총보수"), ("TAX_TP_CD", "과세유형"),
]
PRICE_MAP = [
    ("ISU_SRT_CD", "종목코드"), ("ISU_ABBRV", "종목명"), ("TDD_CLSPRC", "종가"), ("CMPPREVDD_PRC", "대비"), ("FLUC_RT", "등락률"),
    ("NAV", "순자산가치(NAV)"), ("TDD_OPNPRC", "시가"), ("TDD_HGPRC", "고가"), ("TDD_LWPRC", "저가"), ("ACC_TRDVOL", "거래량"),
    ("ACC_TRDVAL", "거래대금"), ("MKTCAP", "시가총액"), ("INVSTASST_NETASST_TOTAMT", "순자산총액"), ("LIST_SHRS", "상장좌수"),
    ("IDX_IND_NM", "기초지수_지수명"), ("OBJ_STKPRC_IDX", "기초지수_종가"), ("CMPPREVDD_IDX", "기초지수_대비"), ("FLUC_RT1", "기초지수_등락률"),
]

LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
LOGIN_JSP = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"

def login(session):
    """pykrx login_krx 와 동일한 흐름. pykrx 를 import 하면 모듈 로드 시 ID 를 stdout 에 찍으므로
    여기서 직접 구현한다 (자격증명은 어떤 경우에도 출력하지 않는다)."""
    ua = {"User-Agent": HEADERS["User-Agent"]}
    session.get(LOGIN_PAGE, headers=ua, timeout=15)
    session.get(LOGIN_JSP, headers={**ua, "Referer": LOGIN_PAGE}, timeout=15)
    payload = {"mbrNm": "", "telNo": "", "di": "", "certType": "",
               "mbrId": os.environ["KRX_ID"], "pw": os.environ["KRX_PW"]}
    hdr = {**ua, "Referer": LOGIN_PAGE}
    data = session.post(LOGIN_URL, data=payload, headers=hdr, timeout=15).json()
    code = data.get("_error_code", "")
    if code == "CD010":
        print("KRX 비밀번호 변경 필요(CD010) — krx.co.kr 에서 변경 후 재시도"); return False
    if code == "CD011":  # 중복 로그인 → 기존 세션 끊고 진행
        payload["skipDup"] = "Y"
        data = session.post(LOGIN_URL, data=payload, headers=hdr, timeout=15).json()
        code = data.get("_error_code", "")
    return code == "CD001"

def get_json(session, bld, **params):
    data = {"bld": bld, "locale": "ko_KR", "csvxls_isNo": "false", "share": "1", "money": "1"}
    data.update(params)
    r = session.post(URL_JSON, data=data, headers=HEADERS, timeout=60)
    r.raise_for_status()
    if not r.text.strip():
        raise RuntimeError(f"빈 응답 (로그인 필요?) bld={bld}")
    return r.json()

def remap(rows, mapping):
    out = []
    for row in rows:
        o = {}
        for src, dst in mapping:
            o[dst] = row.get(src)
        out.append(o)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="시세 기준일 YYYYMMDD (기본: 최근 거래일 자동)")
    ap.add_argument("--out", default=".", help="저장 폴더")
    a = ap.parse_args()

    src = load_env()
    if not src:
        print("KRX 자격증명을 찾지 못했습니다 (KRX_ID/KRX_PW 또는 krx.env)."); sys.exit(1)
    print(f"자격증명 로드: {src if src=='env' else os.path.dirname(src)}")

    s = requests.Session()
    if not login(s):
        print("KRX 로그인 실패"); sys.exit(1)
    print("KRX 로그인 성공")

    basic = get_json(s, "dbms/MDC/STAT/standard/MDCSTAT04601")
    basic_rows = basic.get("output") or basic.get("OutBlock_1") or []
    if not basic_rows:
        print("기본정보 응답 비어 있음:", str(basic)[:200]); sys.exit(1)
    print(f"기본정보 {len(basic_rows)}종")

    # 시세: 지정일 → 없으면 오늘부터 거슬러 올라가며 종가가 있는 최근 거래일
    dates = [a.date] if a.date else [(dt.date.today() - dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(0, 7)]
    price_rows, used = [], None
    for d in dates:
        pr = get_json(s, "dbms/MDC/STAT/standard/MDCSTAT04301", trdDd=d)
        rows = pr.get("output") or pr.get("OutBlock_1") or []
        nz = [r for r in rows if str(r.get("MKTCAP", "0")).replace(",", "") not in ("", "0", "-")]
        if rows and len(nz) > len(rows) * 0.5:
            price_rows, used = rows, d
            break
        time.sleep(0.5)
    if not price_rows:
        print("시세 응답 비어 있음"); sys.exit(1)
    print(f"시세 {len(price_rows)}종 (기준일 {used})")

    os.makedirs(a.out, exist_ok=True)
    stamp = used
    with open(os.path.join(a.out, f"krx_basic_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(remap(basic_rows, BASIC_MAP), f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, f"krx_price_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(remap(price_rows, PRICE_MAP), f, ensure_ascii=False, indent=1)
    print(f"저장: {a.out}/krx_basic_{stamp}.json, krx_price_{stamp}.json")

if __name__ == "__main__":
    main()
