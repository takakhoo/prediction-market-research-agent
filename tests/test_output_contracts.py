import pytest
from src.polymarket.validation import probability
from src.polymarket.prompt_store import render_prompt_template
from src.polymarket.config import PolymarketConfig
from src.polymarket.realtime_listener import RealtimeMessageBatchMatcher
from scripts.offline_replay import RecordedClient, replay


@pytest.mark.parametrize('value',[True,False,'0.9',None,float('nan'),float('inf'),-1,1.01,10**400])
def test_invalid_probabilities(value): assert probability(value) is None


def test_prompt_data_is_not_reexpanded():
    assert render_prompt_template('{{A}} {{B}}',{'A':'literal {{B}}','B':'secret'})=='literal {{B}} secret'


def test_offline_replay():
    result=replay()
    assert result['passed']==result['total']==8


def test_unknown_duplicate_and_malformed_matches():
    item={'chat_id':1,'message_id':1,'text':'benign fixture'}
    markets=[{'market_id':'x'}]
    client=RecordedClient({'matches':[{'candidate_id':x,'confidence':.9,'reason_short':'fixture'} for x in ['M99','M01','M01']]})
    matcher=RealtimeMessageBatchMatcher(config=PolymarketConfig(),reasoning_client=client,model='fixture')
    assert len(matcher.evaluate_message(item=item,markets=markets))==1
    client.payload={'matches':'invalid'}
    with pytest.raises(ValueError): matcher.evaluate_message(item=item,markets=markets)
    with pytest.raises(ValueError): RealtimeMessageBatchMatcher(config=PolymarketConfig(),reasoning_client=client,model='fixture',min_confidence=float('nan'))
