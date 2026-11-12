"""Explicit-denominator repeatability and reference-independent read-order comparisons."""
from collections import defaultdict,Counter
from .read_order import assess_tool
from .common import fingerprint


def compare_results(results,plan):
    expected={(s['case_id'],s['assembler']) for s in plan['slots']}
    if len(expected)!=len(plan['slots']):
        raise ValueError('Comparison plan has duplicate slots')
    metadata={c['id']:c for c in plan['cases']}
    observed={}
    for result in results:
        key=(result['case']['id'],result['assembler'])
        if key not in expected or key in observed or result['case']!=metadata[key[0]]:
            raise ValueError('Unexpected, duplicated or changed comparison result slot')
        observed[key]=result
    groups=defaultdict(list)
    for key in sorted(expected):
        case=metadata[key[0]]
        category=case.get('category')
        if category not in ('S3','S7'):
            continue
        source=case['legacy_case_id'] if category=='S3' else case['input_recipe']['source']['case_id']
        configuration=case.get('configuration_id',case['mode'])
        stratum=(category,source,key[1],case['threads'],case['mode'],configuration)
        result=observed.get(key,{})
        sig=result.get('signatures',{})
        complete=result.get('assessment',{}).get('status')=='completed' and bool(sig)
        row={'case_id':key[0],'repeat':case['repeat'],'status':'pass' if complete else 'not_assessed',
             'version':plan['assembler_definitions'][key[1]]['version'],
             'signature':sig.get('reference_independent',{}),
             'byte_sha256':sig.get('byte_sha256'),
             'normalised_sequence_sha256':sig.get('truth_anchored',{}).get('sha256'),
             'biological_sha256':sig.get('biological_sha256'),
             'secondary_reference_status':result.get('sequence_outcome'),
             'reads_sha256':result.get('execution',{}).get('reads_sha256'),
             'truth_sha256':result.get('provenance',{}).get('reference_sha256')}
        if category=='S7':
            row.update(order_id=case['diagnostic_case']['read_order']['order_id'],
                       input_admission=result.get('read_order_input',{}))
        groups[stratum].append(row)
    summaries=[]
    for (category,source,assembler,threads,mode,configuration),rows in sorted(groups.items()):
        summary={'category':category,'source_case_id':source,'assembler':assembler,
                 'threads':threads,'mode':mode,'configuration_id':configuration,'expected_runs':len(rows),'runs':rows,
                 'status_counts':dict(Counter(r['status'] for r in rows))}
        if category=='S7':
            orders=sorted({r['order_id'] for r in rows})
            counts=Counter(r['order_id'] for r in rows)
            if len(set(counts.values()))!=1:
                raise ValueError('S7 plan has unequal repeats per order')
            inputs=[r['input_admission'] for r in rows]
            admitted=all(i.get('record_multiset_sha256') and i.get('record_count') for i in inputs)
            admitted=admitted and len({(i.get('record_multiset_sha256'),i.get('record_count')) for i in inputs})==1
            hashes=defaultdict(set)
            for row in rows:
                hashes[row['order_id']].add(row['input_admission'].get('record_order_sha256'))
            admitted=admitted and all(len(h)==1 and None not in h for h in hashes.values())
            admitted=admitted and len({next(iter(h)) for h in hashes.values()})==len(orders)
            selected=rows if admitted else [{**r,'status':'not_assessed','signature':{}} for r in rows]
            summary.update(input_equivalence_verified=bool(admitted),
                end_sensitive=assess_tool(selected,orders,next(iter(counts.values())),'end_sensitive_sha256'),
                circular_representation=assess_tool(selected,orders,next(iter(counts.values())),'circular_representation_sha256'),
                endpoint='Reference-independent output agreement; reference recovery is secondary only.')
            summary['complete']=summary['end_sensitive']['complete']
        else:
            complete=all(r['status']=='pass' for r in rows)
            identical=complete and all(r['reads_sha256'] and r['truth_sha256'] for r in rows)
            identical=identical and len({(r['reads_sha256'],r['truth_sha256']) for r in rows})==1
            summary.update(complete=complete,inputs_identical=bool(identical) if complete else None,
                endpoint='Observed repeatability on frozen input, not proof of determinism.')
            for label in ('byte','normalised_sequence','biological'):
                values=[r[label+'_sha256'] for r in rows]
                summary[label+'_variants']=len({v for v in values if v})
                summary[label+'_identical']=len(set(values))==1 if identical and all(values) else None
        summaries.append(summary)
    across=[]
    strata=defaultdict(list)
    for group in summaries:
        if group['category']=='S3':
            strata[(group['source_case_id'],group['assembler'],group['mode'],group['configuration_id'])].append(group)
    for (source,assembler,mode,configuration),selected in sorted(strata.items()):
        rows=[r for g in selected for r in g['runs']]
        complete=all(g['complete'] and g['inputs_identical'] for g in selected)
        complete=complete and len({(r['reads_sha256'],r['truth_sha256']) for r in rows})==1
        row={'source_case_id':source,'assembler':assembler,'mode':mode,'configuration_id':configuration,
             'threads':[g['threads'] for g in selected],'complete':complete}
        for label in ('byte','normalised_sequence','biological'):
            hashes=[r[label+'_sha256'] for r in rows]
            row[label+'_identical']=len(set(hashes))==1 if complete and all(hashes) else None
        across.append(row)
    return {'schema_version':1,'method':'diagnostic-comparison-v1','plan_sha256':plan['plan_sha256'],
            'groups':summaries,'across_threads':across,
            'complete':bool(summaries) and all(g['complete'] for g in summaries),
            'reference_recovery':'Secondary only for S7; never used to decide output agreement.'}
