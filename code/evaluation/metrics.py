"""Explicit positional metrics with insertions/deletions penalized."""
import json
from collections import Counter


def evaluate(results,expected):
    gold={r['case_id']:(r['deletion_status'],json.loads(r['steps_json'])) for r in expected}
    status=exact=steps=fields=sequence=total_steps=0;failures=[];confusion=Counter()
    citations=policy=0
    for row in results:
        label,target=gold[row['case_id']];actual=row['steps']
        same_status=row['deletion_status']==label
        status+=same_status;exact+=same_status and actual==target;sequence+=actual==target
        confusion[(label,row['deletion_status'])]+=1
        total_steps+=max(len(actual),len(target))
        for a,b in zip(actual,target):
            steps+=a==b;fields+=sum(a.get(k)==v for k,v in b.items())
            citations+=a.get('evidence_id')==b['evidence_id']
            policy+=(a.get('operation'),a.get('state'))==(b['operation'],b['state'])
        if not same_status or actual!=target:
            failures.append(dict(case_id=row['case_id'],expected_status=label,actual_status=row['deletion_status'],expected=target,actual=actual))
    n=len(results)
    return dict(cases=n,status_accuracy=status/n,exact_case_accuracy=exact/n,step_accuracy=steps/max(total_steps,1),field_accuracy=fields/max(7*total_steps,1),sequence_accuracy=sequence/n,evidence_citation_accuracy=citations/max(total_steps,1),policy_action_accuracy=policy/max(total_steps,1),confusion_matrix={f'{a}->{b}':v for (a,b),v in sorted(confusion.items())},failures=failures)


def display(report):
    for key in ('status_accuracy','exact_case_accuracy','step_accuracy','field_accuracy','sequence_accuracy'):
        print(f'{key}: {report[key]:.2%}')
    print('Mismatched cases:',', '.join(f['case_id'] for f in report['failures']) or 'none')
