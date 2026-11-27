import json,sys
R={json.loads(l)['id']:json.loads(l) for l in open('/home/user/X-map/accounts/astridwilde/posts.jsonl')}
L=json.load(open('/home/user/X-map/accounts/astridwilde/backtest/ledger.json'))
bad=[];n=0;q=0
def text_all(p):
    t=[p['text']];o=p.get('quoted')
    while o: t.append(o.get('text') or ''); o=o.get('quoted')
    return t
def chk(o):
    global n,q
    if isinstance(o,dict):
        for idk,dk in (('entry_post','entry_date'),('exit_post','exit_date'),('post_id','date'),('post','date'),('latest_post','latest_date'),('last_seen_post','last_seen_held'),('first_absent_post','first_absent')):
            if idk in o and o[idk] is not None:
                n+=1
                if o[idk] not in R: bad.append(('missing',o[idk]))
                elif dk in o and o[dk]!=R[o[idk]]['created_at'][:10]:
                    qq=R[o[idk]].get('quoted'); ok=False
                    while qq:
                        if qq.get('id')==o.get('quoted_id') and (qq.get('created_at') or '')[:10]==o[dk]: ok=True
                        qq=qq.get('quoted')
                    if not ok: bad.append(('date',o[idk],o[dk]))
        if 'quote' in o and ('post' in o or 'post_id' in o or 'quote_post' in o):
            pid=o.get('quote_post') or o.get('post') or o.get('post_id'); q+=1
            if pid in R and not any(o['quote'] in t for t in text_all(R[pid])): bad.append(('quote',pid,o['quote']))
        for v in o.values(): chk(v)
    elif isinstance(o,list):
        for v in o: chk(v)
chk(L)
for t in L['current_bullish']['themes']:
    for i in t['mention_post_ids']:
        if i not in R or R[i]['created_at']<'2026-09-01': bad.append(('period',i))
print('id/date checks',n,'quote checks',q,'problems',bad[:20],len(bad))
from collections import Counter
P=L['positions']
print(len(P),Counter(p['confidence'] for p in P),Counter(p['status'] for p in P))
print({k:len(v) for k,v in L.items() if isinstance(v,list)}, len(L['current_bullish']['themes']))
