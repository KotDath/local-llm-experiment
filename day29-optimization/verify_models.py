"""Read GGUF v3 headers with stdlib and verify the pinned Q8/Q4 pair.

Format reference: ggml-org/ggml docs/gguf.md, value type IDs checked against
llama.cpp b10679 gguf-py/gguf/constants.py. No runtime import of llama.cpp code.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
FORMATS = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'f',
           7: '?', 10: 'Q', 11: 'q', 12: 'd'}


def sha_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read_gguf(path):
    with Path(path).open('rb') as f:
        def scalar(fmt):
            raw = f.read(struct.calcsize('<' + fmt))
            return struct.unpack('<' + fmt, raw)[0]

        def string(keep=True):
            size = scalar('Q')
            if size > 512 << 20:
                raise ValueError('gguf_string_too_large')
            if not keep:
                f.seek(size, 1)
                return
            return f.read(size).decode('utf-8')

        def skip(kind, depth=0):
            if depth > 16:
                raise ValueError('gguf_array_depth')
            if kind in FORMATS:
                f.seek(struct.calcsize('<' + FORMATS[kind]), 1)
            elif kind == 8:
                string(False)
            elif kind == 9:
                child, count = scalar('I'), scalar('Q')
                if count > 100_000_000:
                    raise ValueError('gguf_array_too_large')
                if child in FORMATS:
                    f.seek(count * struct.calcsize('<' + FORMATS[child]), 1)
                else:
                    for _ in range(count):
                        skip(child, depth + 1)
            else:
                raise ValueError('unknown_gguf_metadata_type')

        assert f.read(4) == b'GGUF' and scalar('I') == 3, 'Expected little-endian GGUF v3'
        tensor_count, count = scalar('Q'), scalar('Q')
        assert tensor_count < 100_000 and count < 100_000
        metadata = {}
        for _ in range(count):
            key, kind = string(), scalar('I')
            if kind in FORMATS:
                value = scalar(FORMATS[kind])
            elif kind == 8:
                value = string()
            else:
                start = f.tell()
                skip(kind)
                end = f.tell()
                f.seek(start)
                h = hashlib.sha256()
                left = end - start
                while left:
                    block = f.read(min(left, 1 << 20))
                    if not block:
                        raise ValueError('truncated_gguf_metadata')
                    h.update(block)
                    left -= len(block)
                value = {'encoded_array_sha256': h.hexdigest(), 'bytes': end - start}
            metadata[key] = value
        tensors, types = {}, Counter()
        for _ in range(tensor_count):
            name, dimensions = string(), scalar('I')
            assert dimensions <= 4
            tensors[name] = [scalar('Q') for _ in range(dimensions)]
            types[scalar('I')] += 1
            scalar('Q')  # tensor data offset; weights are not mapped/read here
        return {'metadata': metadata, 'tensor_shapes': tensors, 'tensor_type_counts': dict(types)}


def main():
    config = json.loads((ROOT / 'configs/models.json').read_text())
    directory = Path(os.getenv('MODEL_DIR', '/home/kotdath/omp/personal/amd-strix-halo-toolboxes/models/tiel-coder'))
    models, headers = {}, {}
    for quant in ['Q8', 'Q4']:
        path = directory / config[quant]['file']
        digest = sha_file(path)
        assert digest == config[quant]['sha256'] and path.stat().st_size == config[quant]['bytes']
        headers[quant] = read_gguf(path)
        models[quant] = {'file': path.name, 'bytes': path.stat().st_size, 'actual_sha256': digest,
                         'tensor_count': len(headers[quant]['tensor_shapes']),
                         'tensor_type_counts': headers[quant]['tensor_type_counts'],
                         'general_file_type': headers[quant]['metadata'].get('general.file_type')}
    a, b = headers['Q8']['metadata'], headers['Q4']['metadata']
    architecture = a['general.architecture']
    relevant = {k for k in a | b if k.startswith(('tokenizer.', architecture + '.')) or k == 'general.architecture'}
    different = sorted(k for k in relevant if a.get(k) != b.get(k))
    report = {'snapshot': config['snapshot'], 'models': models,
              'architecture': architecture, 'metadata_differences': different,
              'chat_template_sha256': hashlib.sha256(a['tokenizer.chat_template'].encode()).hexdigest(),
              'tensor_names_shapes_equal': headers['Q8']['tensor_shapes'] == headers['Q4']['tensor_shapes'],
              'quant_types_differ': headers['Q8']['tensor_type_counts'] != headers['Q4']['tensor_type_counts']}
    report['passed'] = not different and report['tensor_names_shapes_equal'] and report['quant_types_differ']
    (ROOT / 'results/model_pair_metadata.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    assert report['passed'], 'Q8/Q4 architecture, tokenizer, template or tensor structure differs'
    print('Pinned model hashes, architecture/tokenizer/template/tensor shapes verified; quant types differ', flush=True)


if __name__ == '__main__':
    main()
