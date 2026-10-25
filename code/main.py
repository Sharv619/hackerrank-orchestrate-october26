"""Run from the repository root: python3 code/main.py [--samples]."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import time
from corpus import read_csv
from pipeline import Pipeline
from validate import validate
from evaluation.metrics import evaluate,display


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',action='store_true')
    parser.add_argument('--media',action='store_true',default=True,help='Enable local media adapters (default)')
    parser.add_argument('--structured-only',action='store_true',help='Explicitly skip PDF/image adapters for the structured baseline')
    parser.add_argument('--dataset',type=Path,default=root/'dataset')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();args.media=not args.structured_only;started=time.perf_counter()
    if args.samples:
        from evaluation.runner import run_samples
        run_samples(args.dataset, args.media, root / '.run')
        return
    pipeline=Pipeline(args.dataset,args.media)
    requests=args.dataset/('sample_deletion_requests.csv' if args.samples else 'deletion_requests.csv')
    results,diagnostics=pipeline.run(requests)
    output=args.output or root/('sample_output.generated.csv' if args.samples else 'output.csv')
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                     dir=output.parent, suffix='.csv', delete=False) as f:
        pending = Path(f.name)
        writer=csv.DictWriter(f,fieldnames=['case_id','deletion_status','steps_json']);writer.writeheader()
        for r in results:writer.writerow(dict(case_id=r['case_id'],deletion_status=r['deletion_status'],steps_json=json.dumps(r['steps'],ensure_ascii=False,separators=(',',':'))))
    try:
        count=validate(pending,requests,args.dataset)
        pending.replace(output)
    finally:
        pending.unlink(missing_ok=True)
    artifacts=root/'.run';artifacts.mkdir(exist_ok=True)
    prefix='sample' if args.samples else 'full'
    (artifacts/f'{prefix}_diagnostics.json').write_text(json.dumps(diagnostics,indent=2))
    (artifacts/'coverage.json').write_text(json.dumps(pipeline.corpus.coverage,indent=2))
    print('Coverage:',json.dumps(pipeline.corpus.summary()))
    if args.samples:
        report=evaluate(results,read_csv(args.dataset/'sample_output.csv'));display(report)
        (artifacts/'sample_metrics.json').write_text(json.dumps(report,indent=2))
    elapsed=time.perf_counter()-started
    usage=dict(cases=count,seconds=elapsed,model_calls=0,input_tokens=0,output_tokens=0,cost_usd=0,output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),media=args.media)
    (artifacts/f'{prefix}_usage.json').write_text(json.dumps(usage,indent=2))
    print(f'Validated {count} rows -> {output.name} ({elapsed:.3f}s)')


if __name__=='__main__':main()
