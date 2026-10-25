from evidence.normalize import normalize


def parse(path,source):
    facts=[]
    for n,line in enumerate(path.read_text().splitlines(),1):
        parts=[s.strip() for s in line.removeprefix('- ').split('|')]
        if len(parts)!=6:continue
        time,system,resource,category,state,subject=parts
        row=dict(system=system,resource_id=resource,record_type=category,state=state,subject_reference=subject)
        fact=normalize(row,source,observed=time,locator=f'line:{n}')
        if fact:facts.append(fact)
    return facts,[]
