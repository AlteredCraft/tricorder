"""Shared strict runtime and task-stack evidence for isolated workloads."""

def assess_cpu(meta):
    errors=[];missing=[]
    cpu=[];snapshots=[]
    for key in ('cpu_before','cpu_after'):
        snapshot=meta.get(key,{})
        tasks=snapshot.get('tasks',[])
        if type(snapshot.get('total_ticks')) is not int or not tasks:
            missing.append(key+' runtime evidence');continue
        if any(type(task.get('id')) is not int or not isinstance(task.get('name'),str)
               or type(task.get('ticks')) is not int or type(task.get('stack_margin_bytes')) is not int for task in tasks):
            missing.append(key+' task counters/stack');continue
        if len({t['id'] for t in tasks})!=len(tasks) or any(t['ticks']<0 or t['stack_margin_bytes']<=0 for t in tasks):
            errors.append('Invalid CPU task evidence');continue
        snapshots.append(snapshot)
    if len(snapshots)==2:
        before,after=snapshots;span=(after['total_ticks']-before['total_ticks']) & 0xffffffff
        old={t['id']:t for t in before['tasks']}
        if not span:errors.append('Invalid CPU runtime span')
        else:
            for task in after['tasks']:
                prior=old.get(task['id'])
                if not prior or prior['name']!=task['name']:
                    missing.append('CPU task lifetime '+task['name']);continue
                cpu.append({'task':task['name'],'runtime_fraction_of_wall':((task['ticks']-prior['ticks']) & 0xffffffff)/span,
                            'stack_margin_bytes':min(task['stack_margin_bytes'],prior['stack_margin_bytes'])})
    return cpu,errors,missing
