# etf-selector — 주간 갱신 지침 (로컬 Claude Code용)

똑재TV ETF 계좌 추천 도구. 매주 화요일 16:00(KST) KRX 데이터로 `data/`를 갱신하고 commit·push한다.
라이브: GitHub Pages (repo ttokjaeTV/etf-selector). 본체 `index.html`은 건드리지 않는다(데이터만 fetch).

## 절대 금지
- `C:\Users\이상준\Desktop\Claude\.secrets\krx.env` 의 값(KRX_ID/KRX_PW)을 읽어 출력·로그·보고에 남기지 않는다. `scripts/fetch_krx.py`가 알아서 읽는다.
- pykrx import 금지(로드 시 ID 출력).
- `etfs[]` 정렬 금지(KRX 행 순서 유지), JSON `indent=1`·`ensure_ascii=False`, `amc_links.json` 키 정렬 금지, `groups` 수정 금지.
- 파일은 반드시 `data\` 안. repo 루트에 두지 않는다. `holdings.json`은 스크립트 출력 형식(한 줄, 구분자 공백 없음) 그대로.
- 수치·분류·URL 추측 금지. 못 구하면 비워 두고 보고. `index.html`은 수정·커밋하지 않는다.

## 절차 (매주 화 16:00, 시세는 당일 종가)
0. `git status` 확인. `.git`의 `*.lock`·`tmp_obj_*` 잔해가 있으면 삭제(이름만 바꿔두지 말 것). `index.html`이 modified여도 무시(커밋 금지).
1. `python scripts/fetch_krx.py --out <임시폴더>` — 출력 폴더는 매번 새 이름. 로그인 실패(CD010 등)면 사유 보고 후 중단.
2. `git show HEAD:data/krx_etf_master.json > base.json`
3. 드라이런: `python scripts/build_master.py --basic … --price … --kofia <실부담비용 최신 json> --base base.json --out master_new.json --date YYYY-MM-DD`
   KOFIA 폴더: `C:\Users\이상준\Desktop\Claude\new etf\신규ETF\실부담비용\` 의 가장 최근 `실부담비용_YYYY-MM-DD.json`.
   - NEW(신규 분류)는 눈으로 검증: 같은 키워드 기존 종목의 group/플래그와 대조. `국내&해외` 주식형은 뉴스로 편입 국가 확인(국내 88%↑ B, 아니면 D). 커버드콜 오분류 주의(Price Return 패시브는 커버드콜 아님). 틀리면 `--override ov.json`.
   - FEE는 매번 70건 안팎 나온다(KRX가 낡음). base와 대조해 **실제 변경분**만 의미. 0.05%p 이상 변경은 뉴스/운용사 페이지로 확인 후 반영. KOFIA 미수록(당월 신규)은 KRX값 유지.
   - 검증: 그룹별 count 증감 = 신규·폐지, `groups` 불변, 중복 코드 0, 총시총 400~500조, marketCap 0은 당일 상장분만.
4. 검증 후 `--out data/krx_etf_master.json --changelog "KRX YYYY-MM-DD 기준(시세 M/D 종가) 신규 N종 추가(종목명→그룹 …), 폐지 M종, 시총·NAV·총보수 전종목 갱신. 총보수는 KOFIA YYYY-MM-DD 공시 우선(변경 종목 …)"`. `git diff --stat -- data`가 약 3,500줄(±)인지 확인. 훨씬 크면 되돌리고 원인 조사.
5. 링크: `python scripts/fetch_amc_links.py` 결과 확인 후 `--apply --date YYYY-MM-DD`. 소형 운용사·TIGER·KIWOOM은 네이버 폴백이 정상. KODEX 429면 비워 두고 보고. RISE는 `riseetf.co.kr/prod/finderDetail/{code}` 형식, 페이지로 검증 불가하면 비워 둠. `meta.updated`와 손댄 브랜드 `meta.houses[브랜드].count/updated`만 수동 갱신. 마스터에 없는 링크 키 0, URL 중복 0.
5-1. `python scripts/fetch_holdings.py --date YYYY-MM-DD` (수집 80% 미만이면 스크립트가 중단).
6. `scripts/__pycache__` 삭제 → `git add data/krx_etf_master.json data/amc_links.json data/holdings.json` → commit `data: KRX YYYY-MM-DD 갱신 (신규 N종, 폐지 M종, 총 T종, 링크 +K, 구성종목 N종)`.

## push 게이트
아래를 **모두** 만족할 때만 `git push`. 하나라도 어긋나면 commit만 하고 push하지 말고 사유를 보고한다.
- 신규 종목 분류를 눈으로 검증했고 `_애매`·미해결 분류가 없다.
- 그룹 count 증감 = 신규·폐지, `groups` 불변, 중복 0, 총시총 400~500조.
- `git diff --stat -- data`가 정상 규모.
- 총보수 실제 변경이 있으면 근거 확인 완료.
- `git status`에서 data 외 변경 파일을 커밋에 섞지 않았다.

## 완료 보고 (한국어, 간결)
총 종목 수 / 신규(종목명→그룹)·폐지 / 총보수 실제 변경(근거) / 링크 추가·미확보 / 시세 0인 당일 상장 종목 / KOFIA 재확인 대상 / 구성종목 N/T종·실패 수 / push 여부(게이트 결과).
