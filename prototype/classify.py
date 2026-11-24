# One-off step run after score.py during the first market run. Adds the "type" column.
# TODO for the build: fold this into score.py and replace the name list with SIC codes from submissions.zip.
import csv
R=list(csv.DictReader(open('treadmill_market_screen.csv')))
f=lambda r,k: float(r[k]) if r[k] not in ('','None') else None
FIN=['EQUINIX','ARES MANAGEMENT','KKR','STEPSTONE','DIGITAL REALTY','BLUE OWL','CARLYLE','APOLLO','TPG ','HAMILTON LANE','SBA COMM','AMERICAN TOWER','CROWN CASTLE','IRON MOUNTAIN']
for r in R:
    cm,fm,sp=f(r,'cum_owner_margin'),f(r,'cum_fcf_margin'),f(r,'sbc_pct_rev')
    if any(x in r['name'].upper() for x in FIN): t='excluded_financial_or_reit'
    elif cm>=3: t='cash_generative'
    elif fm>=0 and sp>=2 and sp>=0.5*fm: t='stock_pay_treadmill'
    elif fm<0 and sp>=5: t='cash_burner_heavy_stock_pay'
    elif fm<0: t='cash_burner_other'
    else: t='thin_margin_low_stock_pay'
    r['type']=t
w=csv.DictWriter(open('treadmill_market_screen.csv','w',newline=''),fieldnames=list(R[0])); w.writeheader(); w.writerows(R)
