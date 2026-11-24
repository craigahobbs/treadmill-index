import zipfile, json, sys, os, glob, time
from datetime import date
from multiprocessing import Pool
ZP=glob.glob(os.path.expanduser('~/mnt/Downloads/companyfacts.zip'))[0]
TAGS={ 'rev':['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueNet'],
 'ocf':['NetCashProvidedByUsedInOperatingActivities','NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
 'ppe':['PaymentsToAcquirePropertyPlantAndEquipment'],'prod':['PaymentsToAcquireProductiveAssets'],'sw':['PaymentsToDevelopSoftware'],
 'sbc':['ShareBasedCompensation'],'sbc2':['AllocatedShareBasedCompensationExpense'],
 'opex':['OperatingExpenses'],'gp':['GrossProfit'],'opinc':['OperatingIncomeLoss'],'cae':['CostsAndExpenses'],
 'cor':['CostOfRevenue'],'cogs':['CostOfGoodsAndServicesSold'],
 'bb':['PaymentsForRepurchaseOfCommonStock'],'div':['PaymentsOfDividends','PaymentsOfDividendsCommonStock'],
 'wh':['PaymentsRelatedToTaxWithholdingForShareBasedCompensation'],'ni':['NetIncomeLoss'],
 'sh':['WeightedAverageNumberOfDilutedSharesOutstanding'],'rnd':['ResearchAndDevelopmentExpense']}
def d(s): return date(int(s[:4]),int(s[5:7]),int(s[8:10]))
def annual(units):
    best={}
    for u in units:
        if 'start' not in u: continue
        n=(d(u['end'])-d(u['start'])).days
        if n<350 or n>380: continue
        k=u['end']; f=u.get('filed','')
        if k not in best or f>best[k][0]: best[k]=(f,u['val'])
    return {k:v[1] for k,v in best.items()}
def one(name):
    try:
        z=one.z
    except AttributeError:
        z=one.z=zipfile.ZipFile(ZP)
    raw=z.read(name)
    if b'ShareBasedCompensation' not in raw or (b'"Revenues"' not in raw and b'RevenueFromContract' not in raw and b'SalesRevenueNet' not in raw): return None
    try: j=json.loads(raw)
    except Exception: return None
    g=j.get('facts',{}).get('us-gaap',{})
    out={'cik':j.get('cik'),'name':j.get('entityName')}
    for key,tags in TAGS.items():
        m={}
        for t in tags:
            if t not in g: continue
            for unit,vals in g[t].get('units',{}).items():
                if unit not in ('USD','shares'): continue
                a=annual(vals)
                for k,v in a.items():
                    if key=='rev': m[k]=max(m.get(k,v),v)
                    elif k not in m: m[k]=v
        out[key]=m
    if not out['rev'] or max(out['rev'].values())<5e8: return None
    return out
if __name__=='__main__':
    s,e=int(sys.argv[1]),int(sys.argv[2]); t=time.time()
    names=sorted(zipfile.ZipFile(ZP).namelist())[s:e]
    with Pool(int(sys.argv[3])) as p, open(f'out/part_{s:05d}.jsonl','w') as f:
        k=0
        for r in p.imap_unordered(one,names,chunksize=8):
            if r: f.write(json.dumps(r)+'\n'); k+=1
    print(s,e,'kept',k,'sec',round(time.time()-t,1))
