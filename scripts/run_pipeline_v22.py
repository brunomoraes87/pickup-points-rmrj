"""Run every v22 scientific stage in a fresh output directory, offline.

Original Olist files are read-only inputs. This command downloads nothing and
does not push commits or write Google Docs. The caller must provide a fresh work
directory, preventing old checkpoints from standing in for a cold reproduction.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
PINS = {'numpy':'2.5.3', 'pandas':'3.0.1', 'scikit-learn':'1.9.1',
        'scipy':'1.18.1', 'shapely':'2.1.2', 'pyproj':'3.8.0', 'matplotlib':'3.11.2'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--solver-time-limit', type=float, default=300)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    if work.exists():
        parser.error('A cold reproduction requires a non-existent --work-dir')
    raw = args.raw_dir.resolve()
    inputs = [raw/f'olist_{name}_dataset.csv' for name in ['customers', 'orders', 'order_items', 'geolocation']]
    for source in inputs:
        if not source.is_file():
            parser.error(f'Missing original input: {source}')
    environment = {name: importlib.metadata.version(name) for name in PINS}
    if environment != PINS:
        parser.error('Pinned reproduction environment differs: '+repr(environment))
    if sys.version_info[:2] != (3, 12):
        parser.error('Use Python 3.12 for the cold reproduction')
    work.mkdir(parents=True)
    data, main_out, exact, sensitivity, figs, verification = [work/p for p in ['processed', 'results/main', 'results/exact', 'results/sensitivity', 'figures', 'verification']]
    shutil.copytree(REPO/'data/geography', data/'geography')
    record = dict(started_at_utc=utc(), python=sys.version, platform=platform.platform(),
                  versions=environment, original_input_hashes={p.name: digest(p) for p in inputs},
                  code_hashes={str(p.relative_to(REPO)).replace('\\','/'): digest(p)
                               for folder in ['scripts','tests'] for p in sorted((REPO/folder).rglob('*.py'))},
                  thread_environment={name:'1' for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']},
                  commands=[], complete=False,
                  checkpoints_policy='Fresh output directory; every fit and solver call executes from cold inputs')
    record_path = work/'pipeline_execution.json'
    def write_record():
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    write_record()
    env = os.environ.copy()
    env.update(record['thread_environment'], PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONPATH='')
    stages = [
        ('tests', ['-m', 'pytest', '-q']),
        ('01_prepare_data', ['scripts/01_prepare_data.py', '--raw-dir', str(raw), '--out-dir', str(data), '--geography-dir', str(data/'geography')]),
        ('05_main_search', ['scripts/05_select_service_k.py', '--data-dir', str(data), '--out-dir', str(main_out)]),
        ('07_exact_benchmarks', ['scripts/07_run_exact_benchmarks.py', '--data-dir', str(data), '--reference-dir', str(main_out), '--out-dir', str(exact), '--time-limit', str(args.solver_time_limit)]),
        ('08_sensitivities', ['scripts/08_run_sensitivities.py', '--raw-dir', str(raw), '--data-dir', str(data), '--out', str(sensitivity)]),
        ('09_figures', ['scripts/09_plot_v22.py', '--data-dir', str(data), '--results-dir', str(main_out), '--figures-dir', str(figs)]),
        ('10_independent_verification', ['scripts/10_verify_v22_independent.py', '--data-dir', str(data), '--main-dir', str(main_out), '--exact-dir', str(exact), '--sensitivity-dir', str(sensitivity), '--out-dir', str(verification)]),
        ('11_manuscript_values', ['scripts/11_export_paper_values.py', '--data-dir', str(data), '--main-dir', str(main_out), '--exact-dir', str(exact), '--sensitivity-dir', str(sensitivity), '--out', str(work/'paper_values_v22.json')]),
    ]
    for label, arguments in stages:
        entry = dict(stage=label, command=[sys.executable, *arguments], started_at_utc=utc())
        record['commands'].append(entry); write_record()
        start = time.perf_counter()
        with (work/f'{label}.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(entry['command'], cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
            entry['exit_code'] = process.wait()
        entry.update(elapsed_wall_s=time.perf_counter()-start, finished_at_utc=utc())
        write_record()
        print(f'{label}: exit={entry["exit_code"]}, elapsed={entry["elapsed_wall_s"]:.2f}s', flush=True)
        if entry['exit_code']:
            raise RuntimeError(f'Stage {label} failed; see {work/label}.log')
    after = {p.name:digest(p) for p in inputs}
    if after != record['original_input_hashes']:
        raise AssertionError('An original input changed during the run')
    code_after = {str(p.relative_to(REPO)).replace('\\','/'):digest(p)
                  for folder in ['scripts','tests'] for p in sorted((REPO/folder).rglob('*.py'))}
    if code_after != record['code_hashes']:
        raise AssertionError('Code changed during the cold reproduction')
    record.update(finished_at_utc=utc(), complete=True, original_inputs_unchanged=True,
                  output_hashes={str(p.relative_to(work)).replace('\\','/'):digest(p)
                                 for p in sorted(work.rglob('*')) if p.is_file() and p != record_path})
    write_record()
    print(json.dumps({'complete': True, 'work_dir': str(work), 'files':len(record['output_hashes'])}), flush=True)


if __name__ == '__main__':
    main()
