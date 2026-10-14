"""Regression invariants for fusion, canonical windows and citation identity."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rag import RAG,fuse
from grounding import citation_catalog,materialize
from agent import Agent


class RetrievalQualityTests(unittest.TestCase):
    def test_rank_fusion_ignores_incomparable_raw_scores(self):
        a={'chunk':{'id':'formula'},'dense_score':.3}
        b={'chunk':{'id':'overview'},'dense_score':.99}
        rows=fuse([('specific',[a,b],1),('other',[a,b],1)])
        self.assertEqual(rows[0]['chunk']['id'],'formula')
        self.assertEqual(rows[0]['retrieval_ranks'],{'specific':1,'other':1})

    def test_neighbor_window_is_exact_original_utf16_span(self):
        r=RAG();chunk=r.index.chunks[1];window=r.expand({'chunk':chunk})['chunk']
        from index import utf16_slice
        doc=r.documents[chunk['source']]
        self.assertEqual(window['text'],utf16_slice(doc['text'],window['start'],window['end']))
        self.assertIn(chunk['id'],window['native_chunk_ids'])
        self.assertGreater(len(window['text']),len(chunk['text']))

    def test_pack_prioritizes_every_part_before_second_window(self):
        entries=[{'chunk':{'id':str(i)}} for i in range(4)]
        records=[{'retrieval':{'evidence':entries[:2]}},{'retrieval':{'evidence':entries[2:]}}]
        rows=Agent._pack_evidence(records)
        self.assertEqual([r['chunk']['id'] for r in rows],['0','2','1','3'])
        self.assertEqual([r['part_indices'] for r in rows],[[0],[1],[0],[1]])

    def test_citation_ids_materialize_verbatim_unicode_not_model_text(self):
        c={'id':'unicode','source':'fixture','revision':'fixture','section':'fixture','start':7,
           'text':'The 😀 mathematical object is retained exactly.','title':'Fixture'}
        evidence=[{'chunk':c}];catalog=citation_catalog(evidence);ident=next(iter(catalog))
        answer=materialize(json.dumps({'status':'answered','claims':[{'text':'Supported claim','citations':[ident]}]}),evidence,catalog)
        self.assertEqual(answer['sources'][0]['quote'],c['text'])
        self.assertEqual(answer['sources'][0]['start_utf16'],7)
        self.assertEqual(answer['sources'][0]['end_utf16'],7+len(c['text'].encode('utf-16-le'))//2)


if __name__=='__main__':unittest.main()
