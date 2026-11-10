#!/usr/bin/env python3
"""Analyze a reviewed Flight Atlas v1 ledger. No network or mailbox access."""
import argparse, collections, copy, datetime as dt, json, math, sys
from pathlib import Path
from trips import homes_for, build_trips, clarifications
from places import places as find_places

INCLUDED = {'reconstructed': {'flown','user_confirmed','strongly_supported','itinerary_only'}, 'confirmed': {'flown','user_confirmed'}}
STATUSES = INCLUDED['reconstructed'] | {'planned','cancelled','missed','superseded','other_traveler','unresolved'}
DISPLAY = 'id departure_date origin destination airline operating_flight status origin_lat origin_lon destination_lat destination_lon origin_country destination_country'.split()

def date(value):
    return dt.date.fromisoformat(value)

def report_date(report, key):
    value=report.get(key)
    if not value: raise ValueError(f'report.{key} is required (YYYY-MM-DD)')
    try: return date(str(value)[:10])
    except ValueError: raise ValueError(f'report.{key} {value!r} is not a date (use YYYY-MM-DD)') from None

def code(value):
    """Upper-case a three-letter airport code; anything else is returned unchanged for review."""
    if isinstance(value,str) and len(value.strip())==3 and value.strip().isascii() and value.strip().isalpha(): return value.strip().upper()
    return value

def flight_number(value):
    return str(value).replace(' ','').upper() if value else ''

def minutes_apart(a, b):
    try: return abs((timestamp(a)-timestamp(b)).total_seconds())/60
    except (ValueError,TypeError,AttributeError): return None

def timestamp(value):
    t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.utcoffset() is None: raise ValueError('timestamp requires explicit UTC offset')
    return t

def coordinates(leg, prefix):
    lat,lon=leg.get(prefix+'_lat'),leg.get(prefix+'_lon')
    if isinstance(lat,(int,float)) and not isinstance(lat,bool) and isinstance(lon,(int,float)) and not isinstance(lon,bool) and math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180: return lat,lon
    return None

def distance(leg):
    a,b=coordinates(leg,'origin'),coordinates(leg,'destination')
    if a is None or b is None: return None
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b))
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1,max(0,h))))

def duration(leg, warnings):
    ident=leg['id']; advertised=leg.get('scheduled_minutes'); calculated=None
    if isinstance(advertised,float) and math.isfinite(advertised) and advertised.is_integer(): advertised=int(advertised)
    if advertised is not None and (isinstance(advertised,bool) or not isinstance(advertised,int) or not 0<advertised<=1800):
        warnings.append(f'{ident}: invalid advertised duration; timing unresolved'); return None,'unknown'
    if leg.get('duration_basis') == 'estimated':
        warnings.append(f'{ident}: estimated duration excluded from scheduled subtotal'); return None,'estimated_excluded'
    if advertised is not None and leg.get('duration_basis') not in {'ticket_advertised','historical_schedule','schedule_calculated'}:
        warnings.append(f'{ident}: duration source basis absent; timing unresolved'); return None,'unknown'
    if leg.get('departure_scheduled') and leg.get('arrival_scheduled'):
        try:
            dep=timestamp(leg['departure_scheduled']); arr=timestamp(leg['arrival_scheduled'])
            if dep.date().isoformat()!=leg['departure_date']: raise ValueError('schedule departure date differs from ledger')
            raw=(arr.astimezone(dt.timezone.utc)-dep.astimezone(dt.timezone.utc)).total_seconds()/60
            if not 0<raw<=1800 or raw!=int(raw): raise ValueError('invalid elapsed scheduled minutes')
            calculated=int(raw)
        except (ValueError,TypeError) as e:
            warnings.append(f'{ident}: {e}; timing unresolved'); return None,'unknown'
    if advertised is not None and calculated is not None and advertised!=calculated:
        if not leg.get('duration_resolution'):
            warnings.append(f'{ident}: advertised {advertised}m differs from calculated {calculated}m; unresolved'); return None,'conflict'
        warnings.append(f'{ident}: timing discrepancy explicitly resolved in private ledger')
    if advertised is not None: return advertised,leg.get('duration_basis')
    if calculated is not None: return calculated,'schedule_calculated'
    return None,'unknown'

def analyze(data):
    if not isinstance(data,dict): raise ValueError('ledger must be a JSON object')
    if data.get('schema_version')!=1: raise ValueError('schema_version must be 1')
    if not isinstance(data.get('report'),dict): raise ValueError('ledger needs a "report" object with title, start_date, end_date and as_of')
    if not isinstance(data.get('legs'),list): raise ValueError('ledger needs a "legs" list (it may be empty)')
    data=copy.deepcopy(data)
    report={k:data['report'].get(k) for k in ('title','start_date','end_date','as_of','inclusion_mode','coverage_note','home_airports') if k in data['report']}; start=report_date(report,'start_date'); end=report_date(report,'end_date'); asof=report_date(report,'as_of')
    if end<start: raise ValueError('end_date precedes start_date')
    mode=report.get('inclusion_mode','reconstructed')
    if mode not in INCLUDED: raise ValueError('invalid inclusion_mode')
    report['inclusion_mode']=mode
    raw=data['legs']; ids=set(); warnings=[]; excluded=[]; selected=[]; seen={}
    if not all(isinstance(l,dict) for l in raw): raise ValueError('every entry in "legs" must be an object')
    for leg in raw:
        for side in ('origin','destination'):
            if leg.get(side) is not None: leg[side]=code(leg[side])
    # Ground transfers and manual gaps name airports too; normalise them the same way so continuity checks still match.
    for item in data.get('ground_segments',[])+data.get('manual_gaps',[]):
        if isinstance(item,dict):
            for side in ('from','to'):
                if item.get(side) is not None: item[side]=code(item[side])
    def in_window(leg):
        try: return start<=date(str(leg.get('departure_date',''))[:10])<=end
        except ValueError: return True
    # Only legs that could be counted decide the traveler; another person's trips outside the window do not block the run.
    travelers={l.get('traveler_id') for l in raw if l.get('status') in INCLUDED[mode] and in_window(l)}
    if None in travelers or '' in travelers: raise ValueError('included candidates require traveler_id')
    if len(travelers)>1: raise ValueError('analyze one traveler at a time; split ledgers')
    for leg in raw:
        ident=leg.get('id')
        if not ident or ident in ids: raise ValueError('missing or duplicate leg id')
        ids.add(ident)
        if leg.get('status') not in STATUSES: raise ValueError(f'{ident}: invalid status')
    byid={l['id']:l for l in raw}
    superseded=set()
    for leg in raw:
        old=leg.get('supersedes_id')
        if old:
            if old not in byid or old==leg['id']: raise ValueError(f"{leg['id']}: invalid supersedes_id")
            superseded.add(old)
        dup=leg.get('duplicate_of')
        if dup and (dup not in byid or dup==leg['id']): raise ValueError(f"{leg['id']}: invalid duplicate_of")
    for leg in raw:
        ident=leg['id']; reason=None
        if ident in superseded: reason='superseded by another reviewed record'
        elif leg.get('duplicate_of'): reason='reviewed duplicate of '+leg['duplicate_of']
        elif leg['status'] not in INCLUDED[mode]: reason='status: '+leg['status']
        try: day=date(leg.get('departure_date',''))
        except (ValueError,TypeError): day=None; reason=reason or 'exact departure date unresolved'
        if day and (day<start or day>end): reason=reason or 'outside departure-date window'
        if day and day>asof: reason=reason or 'future relative to evidence cutoff'
        if not reason:
            if not leg.get('origin') or not leg.get('destination'): reason='route unresolved'
            elif not leg.get('evidence_ids'):
                reason='no evidence references'
                warnings.append(f'{ident}: excluded because evidence_ids is empty; add the source reference (or user-statement id) to count it')
        if not reason and leg.get('operating_flight'):
            key=(leg['traveler_id'],leg['departure_date'],leg['origin'],leg['destination'],flight_number(leg['operating_flight']))
            if key in seen:
                reason='probable duplicate of '+seen[key]
                warnings.append(f'{ident}: duplicate candidate excluded; review schedule versions before finalizing')
            else: seen[key]=ident
        if reason:
            excluded.append({k:leg.get(k) for k in ('id','departure_date','origin','destination','status')} | {'reason':reason}); continue
        clean={k:leg.get(k) for k in DISPLAY}
        clean['airline']=clean.get('airline') or 'Unknown airline'
        minutes,basis=duration(leg,warnings)
        clean.update(scheduled_minutes=minutes,duration_basis=basis)
        # Only validated coordinates may reach a map.
        for prefix in ('origin','destination'):
            if coordinates(leg,prefix) is None:
                clean[prefix+'_lat']=clean[prefix+'_lon']=None
        clean['_sort']=leg.get('departure_scheduled') or leg['departure_date']
        clean['estimated_distance_km']=distance(clean)
        selected.append(clean)
    # Same traveler, date and route counted twice is usually one flight booked under two numbers (codeshare)
    # or two versions of one booking. Flag it loudly; a genuine second flight needs times at least an hour apart.
    groups=collections.defaultdict(list)
    for l in selected: groups[(l['departure_date'],l['origin'],l['destination'])].append(l)
    possible=0
    for (day,o,d),rows in groups.items():
        # Compare every earlier record, not just the neighbour, so ledger order cannot hide a copy.
        for j,b in enumerate(rows):
            for a in rows[:j]:
                gap=minutes_apart(a['_sort'],b['_sort']) if 'T' in a['_sort'] and 'T' in b['_sort'] else None
                if gap is None or gap<60: break
            else:
                continue
            fa,fb=flight_number(a.get('operating_flight')),flight_number(b.get('operating_flight'))
            possible+=1
            why=('different flight numbers '+fa+' and '+fb if fa and fb else 'no operating flight number on '+(b['id'] if fa else a['id']) if fa or fb else 'neither has an operating flight number')
            warnings.append(f"{b['id']}: possible codeshare or duplicate of {a['id']} ({o}-{d} on {day}, {why}); both are counted. Set duplicate_of or operating_flight after checking the source")
    # Date-local ordering with UTC tie-break where available; ambiguous same-day order is flagged.
    def order(l):
        try: return timestamp(l['_sort']).astimezone(dt.timezone.utc).isoformat()
        except ValueError: return l['departure_date']+'T00:00:00+00:00'
    selected.sort(key=order)
    # Two counted flights whose schedules overlap cannot both have been flown: usually an unused ticket or an old version.
    for x,y in zip(selected,selected[1:]):
        try: arr=timestamp(byid[x['id']]['arrival_scheduled']); dep=timestamp(byid[y['id']]['departure_scheduled'])
        except (KeyError,ValueError,TypeError,AttributeError): continue
        if dep<arr:
            warnings.append(f"{y['id']}: departs {y['origin']} before {x['id']} lands at {x['destination']} ({x['departure_date']}); both cannot have been flown. Mark the unused one superseded, cancelled or missed after checking the source")
    daily=collections.Counter(l['departure_date'] for l in selected)
    for l in selected:
        if daily[l['departure_date']]>1 and 'T' not in l['_sort']:
            warnings.append(f"{l['id']}: same-day segment order lacks timestamp; continuity needs review")
    ground={(g.get('after_id'),g.get('before_id')):g for g in data.get('ground_segments',[]) if g.get('status') in {'user_confirmed','documented'}}
    manual=[g for g in data.get('manual_gaps',[]) if isinstance(g,dict)]
    # A 'hint' only feeds a clarifying question; it is not a finding, so it stays out of the report's checks.
    findings=[g for g in manual if g.get('kind')!='hint']
    gaps=[{k:g.get(k) for k in ('kind','note','leg_id','after_id','before_id','from','to') if k in g} for g in findings]
    explained={(g.get('after_id'),g.get('before_id')) for g in findings if g.get('after_id') and g.get('before_id')}
    closed_ground=[]
    for a,b in zip(selected,selected[1:]):
        if a['destination']==b['origin']: continue
        g=ground.get((a['id'],b['id']))
        if g and g.get('from')==a['destination'] and g.get('to')==b['origin']:
            closed_ground.append({k:g.get(k) for k in ('id','after_id','before_id','from','to','status','mode','note','via') if k in g}); continue
        if (a['id'],b['id']) in explained: continue  # the ledger already says what happened here
        gaps.append({'kind':'unresolved_transfer','after_id':a['id'],'before_id':b['id'],'from':a['destination'],'to':b['origin'],'note':'Unexplained airport change; investigate flight, ground transfer or ordering. Not added to totals.'})
    homes,home_inferred=homes_for(data['report'],selected)
    trip_list=build_trips(selected,homes,[(g['after_id'],g['before_id']) for g in closed_ground])
    # Only this traveler's own bookings can stand in for a missing return.
    own_excluded=[x for x in excluded if byid.get(x['id'],{}).get('traveler_id') in travelers]
    questions=clarifications(trip_list,selected,homes,home_inferred,own_excluded,manual,[(g['after_id'],g['before_id']) for g in closed_ground])
    # The traveler's nearest flights just outside the period decide whether its first and last airports were stays.
    outside=sorted((byid[x['id']] for x in own_excluded if x['reason']=='outside departure-date window'),key=lambda l:(str(l.get('departure_date')),str(l.get('departure_scheduled') or '')))
    before=next((l for l in reversed(outside) if str(l.get('departure_date'))[:10]<str(start)),None)
    after=next((l for l in outside if str(l.get('departure_date'))[:10]>str(end)),None)
    visited=find_places(selected,homes,byid,closed_ground,before,after)
    for l in selected:
        l.pop('_sort')
        if l['scheduled_minutes'] is None: gaps.append({'kind':'unknown_duration','after_id':l['id'],'note':'Recorded flight has no reconciled scheduled duration; no hours assigned.'})
    monthly=[]; cursor=start.replace(day=1)
    while cursor<=min(end,asof):
        key=cursor.strftime('%Y-%m'); rows=[l for l in selected if l['departure_date'].startswith(key)]
        monthly.append({'month':key,'flights':len(rows),'minutes':sum(l['scheduled_minutes'] or 0 for l in rows),'unknown_duration_count':sum(l['scheduled_minutes'] is None for l in rows)})
        cursor=(cursor.replace(day=28)+dt.timedelta(days=4)).replace(day=1)
    annual=[]
    for year in range(start.year,end.year+1):
        rows=[l for l in selected if l['departure_date'].startswith(str(year))]
        annual.append({'year':year,'flights':len(rows),'minutes':sum(l['scheduled_minutes'] or 0 for l in rows),'unknown_duration_count':sum(l['scheduled_minutes'] is None for l in rows)})
    carriers=collections.defaultdict(lambda: {'flights':0,'minutes':0})
    routes=collections.Counter()
    for l in selected:
        carriers[l['airline']]['flights']+=1;carriers[l['airline']]['minutes']+=l['scheduled_minutes'] or 0
        routes[(l['origin'],l['destination'])]+=1
    known=[l for l in selected if l['scheduled_minutes'] is not None]
    countries={l.get(p+'_country') for l in selected for p in ('origin','destination')} - {None,''}
    airportset={l[p] for l in selected for p in ('origin','destination')}
    mapped=[l for l in selected if l['estimated_distance_km'] is not None]
    metrics={'flight_count':len(selected),'scheduled_minutes':sum(l['scheduled_minutes'] for l in known),'known_duration_count':len(known),'unknown_duration_count':len(selected)-len(known),'airport_count':len(airportset),'country_count':len(countries),'estimated_distance_km':round(sum(l['estimated_distance_km'] for l in mapped)),'mapped_flight_count':len(mapped),'unmapped_flight_count':len(selected)-len(mapped),'unknown_country_endpoint_count':sum(not l.get(p+'_country') for l in selected for p in ('origin','destination')),'possible_duplicate_count':possible,'trip_count':len(trip_list),'open_trip_count':sum(t['status'] in ('outbound_missing','return_missing','gap') for t in trip_list),**visited['counts']}
    return {'schema_version':1,'report':report,'metrics':metrics,'included_legs':selected,'monthly':monthly,'annual':annual,'airlines':[{'airline':k,**v} for k,v in sorted(carriers.items(),key=lambda kv:-kv[1]['flights'])],'routes':[{'origin':a,'destination':b,'flights':n} for (a,b),n in routes.most_common()],'gaps':gaps,'exclusions':excluded,'warnings':warnings,'status_counts':dict(collections.Counter(l['status'] for l in selected)),'duration_basis_counts':dict(collections.Counter(l['duration_basis'] for l in selected)),'longest_legs':sorted(known,key=lambda l:-l['scheduled_minutes'])[:5],'shortest_leg':min(known,key=lambda l:l['scheduled_minutes']) if known else None,'ground_segments':closed_ground,'home_airports':homes,'home_inferred':home_inferred,'trips':trip_list,'clarifications':questions,'places':{k:v for k,v in visited.items() if k!='counts'}}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--out',required=True);a=p.parse_args()
    try: data=json.loads(Path(a.input).read_text(encoding='utf-8'))
    except OSError as e: sys.exit(f'Could not read ledger {a.input}: {e.strerror}')
    except json.JSONDecodeError as e: sys.exit(f'Ledger {a.input} is not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}')
    try: result=analyze(data)
    except (ValueError,TypeError,KeyError,AttributeError) as e: sys.exit(f'Ledger problem: {e}')
    Path(a.out).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'metrics':result['metrics'],'warnings':result['warnings']},indent=2))
if __name__=='__main__':main()
