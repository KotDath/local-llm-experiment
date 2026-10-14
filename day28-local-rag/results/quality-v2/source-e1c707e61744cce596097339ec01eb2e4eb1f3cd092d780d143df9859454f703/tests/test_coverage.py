"""Controller faults: final support, retry boundaries and cost/history integrity."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import Agent
from common import ServiceError


class Retriever:
    def __init__(self):self.queries=[]
    def retrieve(self,question,rerank):
        self.queries.append(question)
        return {'evidence':[{'chunk':{'id':'fixture','source':'fixture','revision':'fixture',
                'section':'fixture','start':0,'text':'The first mechanism is documented. The second mechanism is documented.'}}]}


def response(value):
    return {'text':json.dumps(value),'usage':{'prompt_tokens':5,'completion_tokens':7,'total_tokens':12},
            'finish_reason':'stop','timings':{}}


class Model:
    def __init__(self,final_supported=True,malformed=False):
        self.calls=[];self.reviews=0;self.answers=0
        self.final_supported=final_supported;self.malformed=malformed
    def count_prompt(self,messages):return 50,'fixture'
    def complete(self,messages,profile):
        self.calls.append(copy.deepcopy(messages))
        if profile['max_tokens']==256:return response({'query':'Explain both mechanisms.'})
        if profile['max_tokens']==512 and any(key.startswith('C') for key in profile.get('response_format',{}).get('schema',{}).get('properties',{})):
            return response({key:True for key in profile['response_format']['schema']['properties']})
        if profile['max_tokens']==512:return response({'parts':[{'question':'Explain both mechanisms.','search':'Explain both mechanisms.'}]})
        if profile['max_tokens']==1024:
            self.reviews+=1
            if self.malformed:return response({'coverage':{'complete':True,'issues':[]},'P1':{'complete':True,'unsupported_claims':['bad'],'issues':[]}})
            return response({'coverage':{'complete':True,'issues':[]},'P1':{'complete':self.reviews>1,'unsupported_claims':[] if self.reviews==1 or self.final_supported else [0,1],
                             'issues':['The second mechanism is missing.'] if self.reviews==1 else ([] if self.final_supported else ['Unsupported final fact.'])}})
        self.answers+=1
        claims=[{'text':'The first mechanism','citations':['E001']}]
        if self.answers>1:claims.append({'text':'The second mechanism','citations':['E001']})
        return response({'P1':{'status':'partial' if self.answers==1 else 'answered','claims':claims}})


class CoverageControllerTests(unittest.TestCase):
    def test_revision_is_semantically_rechecked_and_all_calls_billed(self):
        a=Agent(rag=True);a.model=Model();a.retriever=Retriever()
        result=a.ask('Explain both mechanisms.')
        self.assertEqual([c['phase'] for c in result['llm_calls']],
                         ['question_plan','answer','coverage_review','answer_revision','final_review','answer_focus'])
        self.assertEqual(len(a.retriever.queries),2)
        self.assertEqual(len(result['claims']),2)
        self.assertEqual(result['usage'],{'prompt_tokens':30,'completion_tokens':42,'total_tokens':72})
        self.assertTrue(result['parts'][0]['final_review']['supported'])
        self.assertEqual(a.history[-1]['content'],result['text'])

    def test_unsupported_final_revision_is_not_published_as_supported(self):
        a=Agent(rag=True);a.model=Model(final_supported=False);a.retriever=Retriever()
        result=a.ask('Explain both mechanisms.')
        self.assertEqual(result['status'],'abstained')
        self.assertEqual(result['claims'],[])
        self.assertEqual(result['sources'],[])
        self.assertIn('rejected_answer',result['parts'][0])
        self.assertEqual(len(result['llm_calls']),5)
        self.assertNotIn('The second mechanism',a.history[-1]['content'])

    def test_malformed_review_preserves_cost_and_history(self):
        a=Agent(rag=True);a.model=Model(malformed=True);a.retriever=Retriever()
        a.history=[{'role':'user','content':'Previous question'},{'role':'assistant','content':'Previous answer'}]
        original=copy.deepcopy(a.history)
        with self.assertRaises(ServiceError) as raised:a.ask('Explain both mechanisms.')
        self.assertEqual(raised.exception.code,'invalid_coverage_review')
        trace=raised.exception.detail['failure_trace']
        self.assertEqual(len(trace['llm_calls']),4)
        self.assertEqual(trace['usage']['total_tokens'],48)
        self.assertEqual(a.history,original)


if __name__=='__main__':unittest.main()
