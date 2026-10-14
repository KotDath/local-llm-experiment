"""Reproducible four-condition local benchmark. Grades are joined separately."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import threading
import time
from agent import Agent
from common import ServiceError, append_jsonl, utc_now
from model import Model
from rag import RAG

ROOT = Path(__file__).resolve().parent
CASES = {'A': ('Q8', 'baseline'), 'B': ('Q8', 'optimized'),
         'C': ('Q4', 'baseline'), 'D': ('Q4', 'optimized')}


def resources(pid):
    result = {'utc': utc_now()}
    try:
        for line in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines():
            if line.startswith(('Rss:', 'Pss:')):
                result[line.split(':')[0].lower() + '_bytes'] = int(line.split()[1]) * 1024
        mem = {line.split(':')[0]: int(line.split()[1]) * 1024
               for line in Path('/proc/meminfo').read_text().splitlines() if line.split()[1].isdigit()}
        result['host_used_bytes'] = mem['MemTotal'] - mem['MemAvailable']
        for field in ['vram', 'gtt']:
            p = Path('/sys/class/drm/card1/device/mem_info_' + field + '_used')
            result[field + '_bytes'] = int(p.read_text()) if p.exists() else None
    except (OSError, ValueError):
        result['sampling_error'] = True
    return result


class Sampler:
    def __init__(self, pid):
        self.pid = pid
        self.stop = threading.Event()
        self.samples = []
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.is_set():
            self.samples.append(resources(self.pid))
            self.stop.wait(.2)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join()

    def peaks(self):
        return {key: max((s[key] for s in self.samples if isinstance(s.get(key), (int, float))), default=None)
                for key in ['rss_bytes', 'pss_bytes', 'host_used_bytes', 'vram_bytes', 'gtt_bytes']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    quant, profile = CASES[args.case]
    config = json.loads((ROOT / ('configs/' + profile + '.json')).read_text())
    model = Model()
    try:
        model.health()
        raise SystemExit('Port 8772 is in use. Stop your demo model before benchmark; no foreign process is killed.')
    except ServiceError:
        pass
    env = os.environ.copy()
    env.update({'QUANT': quant, 'PARALLEL': '1', 'CTX_PER_SLOT': str(config['context'])})
    (ROOT / 'runtime').mkdir(exist_ok=True)
    log = (ROOT / ('runtime/benchmark_' + args.case + '.log')).open('w')
    start = time.monotonic()
    process = subprocess.Popen(['bash', str(ROOT / 'run_model.sh')], env=env, stdout=log, stderr=log)
    try:
        while True:
            if process.poll() is not None:
                raise RuntimeError('model_launch_failed; see runtime log')
            try:
                model.health()
                break
            except ServiceError:
                if time.monotonic() - start > 180:
                    raise RuntimeError('model_load_timeout')
                time.sleep(1)
        load_ms = (time.monotonic() - start) * 1000
        info = model.info()
        assert info['total_slots'] == 1 and info['default_generation_settings']['n_ctx'] == config['context'], 'Actual context/slots mismatch'
        weights = Path(info['model_path'])
        source_hash = hashlib.sha256(b''.join((ROOT / n).read_bytes() for n in ['agent.py', 'rag.py', 'model.py', 'grounding.py', 'index.py'])).hexdigest()
        questions_bytes = (ROOT / 'eval/golden_questions.jsonl').read_bytes()
        questions = [json.loads(line) for line in questions_bytes.splitlines()]
        random.Random(42).shuffle(questions)
        run = args.case + '-' + str(time.time_ns())
        # Identity is known before planning: even failures before retrieval remain
        # valid measured rows and can be joined without missing metadata.
        retrieval = RAG()
        common = {'run_id': run, 'case': args.case, 'quant': quant, 'profile_name': profile,
                  'profile_settings': config, 'model_bytes': weights.stat().st_size, 'model_file': weights.name,
                  'model_build': info['build_info'], 'parallel': info['total_slots'],
                  'context_per_slot': info['default_generation_settings']['n_ctx'], 'load_ms': load_ms,
                  'source_sha256': source_hash, 'questions_sha256': hashlib.sha256(questions_bytes).hexdigest(),
                  'index_generation': retrieval.index.manifest['generation'],
                  'embedding_fingerprint': retrieval.index.manifest['fingerprint'],
                  'retrieval_config': retrieval.config, 'rerank': False,
                  'idle_resources': resources(process.pid)}
        warmup = Agent(profile=profile, rag=True).ask('Как MemGPT организует основную и внешнюю память?')
        if not warmup['llm_calls'] or not warmup.get('text') or warmup.get('status') == 'abstained':
            raise RuntimeError('Warmup did not exercise real generation; no measured rows written')
        append_jsonl(ROOT / 'results/benchmark_warmups.jsonl', {**common, 'excluded_from_measurements': True, 'trace': warmup})
        for repeat in range(args.repeats):
            for question in questions:
                record = {**common, 'id': question['id'], 'repeat': repeat, 'question': question['question'], 'utc': utc_now()}
                start = time.monotonic()
                with Sampler(process.pid) as sampler:
                    try:
                        record.update(Agent(profile=profile, rag=True).ask(question['question']))
                        record['ok'] = True
                    except ServiceError as exc:
                        if isinstance(exc.detail, dict) and 'failure_trace' in exc.detail:
                            record.update(exc.detail['failure_trace'])
                        record.update({'ok': False, 'error': exc.code, 'detail': exc.detail})
                record['total_ms'] = (time.monotonic() - start) * 1000
                record['resource_peak'] = sampler.peaks()
                append_jsonl(ROOT / 'results/benchmark_raw.jsonl', record)
                for sample in sampler.samples:
                    append_jsonl(ROOT / 'results/resource_samples.jsonl', {'run_id': run, 'id': question['id'], 'repeat': repeat, **sample})
                print(args.case, repeat, question['id'], record.get('status', record.get('error')), round(record['total_ms']), flush=True)
        export_csv()
    finally:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()


def export_csv():
    rows = [json.loads(line) for line in (ROOT / 'results/benchmark_raw.jsonl').read_text().splitlines()]
    output = []
    for row in rows:
        calls = row.get('llm_calls', [])
        tokens = sum(c.get('timings', {}).get('predicted_n', 0) for c in calls)
        millis = sum(c.get('timings', {}).get('predicted_ms', 0) for c in calls)
        output.append({key: row.get(key) for key in ['run_id', 'case', 'quant', 'profile_name', 'id', 'repeat', 'ok', 'status', 'error', 'total_ms']} |
                      {'llm_calls': len(calls), 'generation_tokens_s': tokens / millis * 1000 if millis else None,
                       'output_tokens': row.get('usage', {}).get('completion_tokens'),
                       'truncated': any(c.get('finish_reason') == 'length' for c in calls)} |
                      row.get('resource_peak', {}))
    with (ROOT / 'results/benchmark.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)


if __name__ == '__main__':
    main()
