"""Resolve selection and preflight runtime without importing reporting code."""
import json
from pathlib import Path


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def setup(args,project):
    from benchlib.catalogue import build_plan
    from benchlib.preparation import plan_preparation,execute_work_list,PreparationError
    from benchlib.runtime_v2 import inspect_dependency,prepare_dependency,runtime_plan
    selection=json.loads(args.selection)
    plan=build_plan(project,catalogue_path=args.catalogue.resolve() if args.catalogue else None,**selection)
    plan=runtime_plan(plan,project,args.runtime,args.container_runtime,args.container_image)
    kinds=('software','software_environment','container_image')
    inspectors={k:inspect_dependency for k in kinds};handlers={k:prepare_dependency for k in kinds}
    work=plan_preparation(plan,args.cache_dir,project,inspectors,offline=args.offline)
    write('plan.json',plan);write('preparation.json',work)
    if args.plan_only:return
    if args.offline:
        if not work['ready']:
            missing=[r['id']+': '+r.get('reason',r['status']) for r in work['items']+work['bootstrap'] if r['status']!='cached']
            raise PreparationError('Offline workload is not prepared: '+'; '.join(missing))
    else:
        invalid=[r for r in work['items'] if r['status']=='invalid']
        missing_local=[r for r in work['items'] if r['status']=='missing' and r.get('source',{}).get('path') and not Path(r['source']['path']).is_file()]
        if invalid or missing_local:raise PreparationError('Invalid/missing local dependencies: '+', '.join(r['id'] for r in invalid+missing_local))
        runtime_work=plan_preparation(plan,args.cache_dir,project,inspectors,kinds=kinds)
        execute_work_list(runtime_work,handlers=handlers)
