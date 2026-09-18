"""Scripted matcher-boundary replay. No inference, database, Telegram or network."""
from dataclasses import asdict
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.polymarket.config import PolymarketConfig
from src.polymarket.realtime_listener import RealtimeMessageBatchMatcher


class RecordedClient:
    provider_name='scripted-offline-fixture'
    def __init__(self,payload): self.payload=payload
    def generate_json(self,**kwargs): return self.payload


def replay():
    cases=[('valid',.91,True),('below_threshold',.79,False),('infinity',float('inf'),False),
           ('nan',float('nan'),False),('boolean',True,False),('string','0.95',False),
           ('out_of_range',1.4,False),('negative',-.2,False)]
    rows=[]
    for name,score,expected in cases:
        client=RecordedClient({'matches':[{'candidate_id':'M01','confidence':score,'reason_short':'Fixture evidence mentions the scheduled council vote.'}]})
        matcher=RealtimeMessageBatchMatcher(config=PolymarketConfig(),reasoning_client=client,model='fixture')
        result=matcher.evaluate_message(item={'chat_id':1,'message_id':1,'text':'Fictional Harbor City council scheduled a vote.'},
            markets=[{'market_id':'fixture-council','question':'Will the fictional council vote this month?'}])
        rows.append({'case':name,'expected_accepted':expected,'accepted':bool(result),'decisions':[asdict(r) for r in result]})
    return {'kind':'synthetic model-output contract replay, not relevance accuracy or trading performance',
            'passed':sum(r['accepted']==r['expected_accepted'] for r in rows),'total':len(rows),'cases':rows}


if __name__=='__main__':
    output=replay()
    target=ROOT/'results/offline-replay.json';target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps(output,indent=2))
    if output['passed']!=output['total']: raise SystemExit(1)
