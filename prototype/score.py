import json, csv, sys
lin=lambda v,zero,full,pts: max(0.0,min(pts,pts*(zero-v)/(zero-full)))
rows=[]; funnel={'with_500M_rev_ever':0,'current_filers':0,'rev_1B':0,'5yrs':0,'grew_50':0}
for line in open('out/all.jsonl'):
    c=json.loads(line); funnel['with_500M_rev_ever']+=1
    sbc={**c['sbc2'],**c['sbc']}
    capx={}
    for k in set(c['ppe'])|set(c['prod'])|set(c['sw']):
        capx[k]=abs(c['ppe'].get(k, c['prod'].get(k,0)))+abs(c['sw'].get(k,0))
    ends=sorted(k for k in c['rev'] if k in c['ocf'] and k in sbc and c['rev'][k]>0)
    byyear={}
    for k in ends: byyear[k[:4] if k[5:7]>'03' else str(int(k[:4])-1)]=k   # fiscal years ending Jan-Mar belong to prior year
    yrs=sorted(byyear); 
    if not yrs: continue
    last=byyear[yrs[-1]]
    if last<'2025-06-30': continue
    funnel['current_filers']+=1
    if c['rev'][last]<1e9: continue
    funnel['rev_1B']+=1
    if len(yrs)<5: continue
    funnel['5yrs']+=1
    first=byyear[yrs[0]]
    if c['rev'][last]<1.5*c['rev'][first]: continue
    funnel['grew_50']+=1
    E=[byyear[y] for y in yrs]
    rev=[c['rev'][k] for k in E]; fcf=[c['ocf'][k]-capx.get(k,0) for k in E]; sb=[sbc[k] for k in E]
    oc=[f-s for f,s in zip(fcf,sb)]; m=[o/r for o,r in zip(oc,rev)]
    low=sum(1 for v in m if v<0.03); cum=sum(oc)/sum(rev); lastm=m[-1]
    p1=10*low/len(m)+lin(cum,0.05,-0.10,8)+lin(lastm,0.05,-0.05,7)
    def opx(k,method):
        if method==0 and k in c['opex']: return c['opex'][k]
        if method==1 and k in c['gp'] and k in c['opinc']: return c['gp'][k]-c['opinc'][k]
        cr=c['cor'].get(k, c['cogs'].get(k))
        if method==2 and k in c['cae'] and cr is not None: return c['cae'][k]-cr
        if method==3 and k in c['opinc'] and cr is not None: return c['rev'][k]-c['opinc'][k]-cr
        return None
    od=None; meth=None
    f5=E[-5]
    for mm in (1,2,3,0):
        a,b=opx(f5,mm),opx(last,mm)
        if a is not None and b is not None and a>0 and b>0:
            od=(b/c['rev'][last]-a/c['rev'][f5])*100; meth=mm; break
    p2=lin(-od,10,0,25) if od is not None else None
    score=p1+(p1/25)*(p2 if p2 is not None else 0)
    rows.append(dict(cik=c['cik'],name=c['name'],years=len(yrs),first=yrs[0],last_fye=last,rev_last_m=round(c['rev'][last]/1e6),
      rev_growth_x=round(c['rev'][last]/c['rev'][first],1),low_years=low,cum_owner_margin=round(cum*100,1),last_owner_margin=round(lastm*100,1),
      cum_fcf_margin=round(sum(fcf)/sum(rev)*100,1),sbc_pct_rev=round(sum(sb)/sum(rev)*100,1),sbc_last_m=round(sb[-1]/1e6),
      cum_owner_cash_m=round(sum(oc)/1e6),cum_sbc_m=round(sum(sb)/1e6),
      buybacks_m=round(sum(abs(v) for k,v in c['bb'].items() if k in E)/1e6),dividends_m=round(sum(abs(v) for k,v in c['div'].items() if k in E)/1e6),
      opex_change_pts=None if od is None else round(od,1),opex_method=meth,capex_missing_years=sum(1 for k in E if k not in capx),
      P1=round(p1,1),P2_cost=None if p2 is None else round(p2,1),screen_score=round(score,1)))
rows.sort(key=lambda r:-r['screen_score'])
w=csv.DictWriter(open('treadmill_market_screen.csv','w',newline=''),fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
json.dump(funnel,open('out/funnel.json','w'))
print(funnel, 'scored',len(rows))
