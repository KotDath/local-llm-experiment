"""Article provenance/page tests. Synthetic rebuild never invokes inference."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import index as index_module
import rag as rag_module
from common import ServiceError
from grounding import validate
from index import Index

NATIVE_INDEX_SHA = 'ba0e9524fb2947802b4121f99944b40b65f936995feafcad77742fe55b4690f3'
NATIVE_GENERATION = '29297553d6b1cd8636c4024a587544c8320b17bcfb0582d35216f54703e203eb'
PAPERS = {
    '2310.08560v2': (13, 48, 663708, '9f674bcff69c86f11c813dcfad613d8841f5f8ed17979e3c4df06a91df7762e0'),
    '2305.10250v3': (11, 33, 516536, '6c60f7f95a872de85179b770edaba584da7a30da37490522394a3e4888aa0059'),
    '2304.03442v2': (22, 101, 11947867, '1b31e77fb24d25d7598f2c49e955d12a28b95a6dabad34acdac40f44bfb7a139'),
}


def cited(quote, chunk):
    answer = {'status': 'answered', 'claims': [{'text': 'Citation mapping fixture',
              'evidence': [{'chunk_id': chunk['id'], 'quote': quote}]}]}
    return validate(json.dumps(answer, ensure_ascii=False), [{'chunk': chunk}])


class ArticleProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = ROOT / 'data/week6/fixed.jsonl'
        cls.index = Index(cls.native)
        cls.assets = json.loads((ROOT / 'data/corpus/manifest.json').read_text())

    def test_original_week6_three_paper_index_identity(self):
        self.assertEqual(hashlib.sha256(self.native.read_bytes()).hexdigest(), NATIVE_INDEX_SHA)
        self.assertEqual(self.index.manifest['generation'], NATIVE_GENERATION)
        self.assertEqual(len(self.index.documents), 3)
        self.assertEqual(len(self.index.chunks), 182)
        self.assertEqual(self.index.matrix.shape, (182, 1024))
        for document in self.index.documents:
            version = document['source_revision']
            pages, count, pdf_bytes, _ = PAPERS[version]
            self.assertEqual(document['source'], 'https://arxiv.org/pdf/' + version)
            self.assertEqual(len(document['page_starts']), pages)
            self.assertEqual(document['page_starts'][0], 0)
            self.assertTrue(all(type(n) is int for n in document['page_starts']))
            self.assertEqual(document['page_starts'], sorted(set(document['page_starts'])))
            self.assertEqual(document['pdf_size'], pdf_bytes)
            self.assertEqual(sum(c['source'] == document['source'] for c in self.index.chunks), count)

    def test_original_pdf_and_canonical_text_hashes(self):
        self.assertEqual(len(self.assets), 3)
        for asset in self.assets:
            version = asset['revision']
            pages, _, pdf_bytes, expected_hash = PAPERS[version]
            with self.subTest(version=version):
                original = (ROOT / asset['pdf_file']).read_bytes()
                self.assertTrue(original.startswith(b'%PDF-'))
                self.assertEqual(len(original), pdf_bytes)
                self.assertEqual(hashlib.sha256(original).hexdigest(), expected_hash)
                self.assertEqual(asset['pdf_sha256'], expected_hash)
                self.assertEqual(asset['pages'], pages)
                canonical = (ROOT / 'data/corpus' / asset['asset']).read_text()
                document = next(d for d in self.index.documents if d['source'] == asset['source'])
                self.assertEqual(canonical, document['text'])
                self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), document['revision'])

    def test_real_supplementary_math_quote_has_precise_page_and_utf16(self):
        # Frozen native paper contains 87 supplementary mathematical characters.
        chunk = next(c for c in self.index.chunks if c['id'] ==
                     '90fe259fcde59fc032f91b8e901db0fdbd9aab68dc46d98a06e18b51888bd570')
        first = next(i for i, char in enumerate(chunk['text']) if ord(char) > 0xffff)
        quote = chunk['text'][first - 10:first + 30]
        self.assertGreater(len(quote.encode('utf-16-le')) // 2, len(quote))
        source = cited(quote, chunk)['sources'][0]
        self.assertEqual((source['start_utf16'], source['end_utf16']), (44259, 44320))
        self.assertEqual((source['page_start'], source['page_end']), (9, 9))
        self.assertEqual(source['source_revision'], '2304.03442v2')
        self.assertEqual(source['pdf_sha256'], PAPERS['2304.03442v2'][3])
        self.assertEqual(source['quote'], quote)

    def test_quote_specific_pages_across_boundary_with_surrogate_pair(self):
        # Coordinates are independently counted: page2 starts at14, page3 at45.
        text = '😀First page.\nSecond 😀page exact quotation.\nThird page starts here.'
        chunk = {'id': 'fixture', 'source': 'https://example.invalid/paper.pdf',
                 'revision': 'fixture', 'source_revision': 'fixture-v1', 'title': 'Fixture',
                 'section': 'Fixture', 'start': 0, 'text': text, 'page_starts': [0, 14, 45],
                 'page_start': 1, 'page_end': 3, 'pdf_file': 'fixture.pdf', 'pdf_sha256': 'fixture'}
        page2 = cited('Second 😀page exact quotation.', chunk)['sources'][0]
        self.assertEqual((page2['start_utf16'], page2['end_utf16']), (14, 44))
        self.assertEqual((page2['page_start'], page2['page_end']), (2, 2))
        crossing = cited('page.\nSecond 😀page exact quotation.', chunk)['sources'][0]
        self.assertEqual((crossing['start_utf16'], crossing['end_utf16']), (8, 44))
        self.assertEqual((crossing['page_start'], crossing['page_end']), (1, 2))

    def test_import_rejects_wrong_pages_even_with_recomputed_footer(self):
        records = [json.loads(line) for line in self.native.read_bytes().splitlines()]
        chunk = next(row['data'] for row in records if row.get('type') == 'chunk')
        chunk['page_start'] += 1
        payload = b''.join((json.dumps(row, ensure_ascii=False) + '\n').encode()
                           for row in records[:-1])
        footer = {'type': 'end', 'version': 1, 'hash': hashlib.sha256(payload).hexdigest()}
        payload += (json.dumps(footer) + '\n').encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'wrong-pages.jsonl'
            path.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, 'chunk_pdf_page_mismatch'):
                Index(path)

    def test_rebuild_retains_document_and_quote_pages_without_embedding_calls(self):
        # Deterministic controller fixture, not quality or real embedding evidence.
        text = '😀First page.\nSecond 😀page exact quotation.\nThird page starts here.'
        fixture_pdf = b'%PDF-1.4\n% synthetic controller fixture only\n'

        class OfflineEmbeddingFixture:
            def health(self):
                return {'fingerprint': 'synthetic-only'}

            def offsets(self, value):
                return [[i, i + 1] for i in range(len(value))]

            def encode(self, values, fingerprint, query=False):
                return [[1.0] + [0.0] * 1023 for _ in values]

        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary)
            corpus = fixture_root / 'data/corpus'
            corpus.mkdir(parents=True)
            (corpus / 'fixture.txt').write_text(text)
            (fixture_root / 'fixture.pdf').write_bytes(fixture_pdf)
            entry = {'source': 'https://example.invalid/paper.pdf', 'title': 'Fixture',
                     'asset': 'fixture.txt', 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                     'revision': 'fixture-v1', 'page_starts': [0, 14, 45],
                     'pdf_ref': 'fixture', 'pdf_size': len(fixture_pdf), 'pdf_file': 'fixture.pdf',
                     'pdf_sha256': hashlib.sha256(fixture_pdf).hexdigest(), 'pages': 3}
            (corpus / 'manifest.json').write_text(json.dumps([entry]))
            output = fixture_root / 'rebuilt.jsonl'
            with patch.object(index_module, 'ROOT', fixture_root), \
                 patch.object(index_module, 'Embeddings', OfflineEmbeddingFixture), \
                 patch.object(index_module, 'http_json', side_effect=AssertionError('No network allowed')):
                index_module.rebuild(output)
                rebuilt = Index(output)
                self.assertEqual(rebuilt.documents[0]['page_starts'], [0, 14, 45])
                self.assertEqual(rebuilt.documents[0]['source_revision'], 'fixture-v1')
                chunk = rebuilt.chunks[0]
                self.assertEqual((chunk['page_start'], chunk['page_end']), (1, 3))
                mapped = cited('Second 😀page exact quotation.', chunk)['sources'][0]
                self.assertEqual((mapped['page_start'], mapped['page_end']), (2, 2))
                self.assertEqual(mapped['pdf_sha256'], entry['pdf_sha256'])

    def test_calibration_drift_rejected_before_network(self):
        stale = {'index_generation': 'different-article-generation'}
        with patch.object(rag_module, 'open', return_value=io.StringIO(json.dumps(stale)), create=True), \
             patch.object(rag_module, 'http_json', side_effect=AssertionError('No network allowed')):
            with self.assertRaises(ServiceError) as caught:
                rag_module.RAG()
        self.assertEqual(caught.exception.code, 'retrieval_calibration_drift')
        self.assertEqual(caught.exception.status, 409)


if __name__ == '__main__':
    unittest.main()
