"""Distinct offline SVG travel layouts. Geography is Natural Earth, never invented."""
import collections,datetime as dt,html,json,math
from pathlib import Path

def e(v): return html.escape(str(v if v is not None else 'Unknown'),quote=True)

def endpoints(legs):
    result={}
    for leg in legs:
        for side in ('origin','destination'):
            try:
                lat,lon=float(leg[side+'_lat']),float(leg[side+'_lon'])
                if not (math.isfinite(lat) and math.isfinite(lon) and abs(lat)<=90 and abs(lon)<=180):continue
                code=str(leg[side]);result[code]=(lon,lat)
            except (KeyError,TypeError,ValueError):continue
    return result

def orthographic(lon,lat,center_lon,center_lat):
    l,p,l0,p0=map(math.radians,(lon,lat,center_lon,center_lat))
    z=math.sin(p0)*math.sin(p)+math.cos(p0)*math.cos(p)*math.cos(l-l0)
    return math.cos(p)*math.sin(l-l0), -(math.cos(p0)*math.sin(p)-math.sin(p0)*math.cos(p)*math.cos(l-l0)),z

def visible_path(points,center,cx=300,cy=225,r=195):
    """Clip every segment at the orthographic horizon (z=0)."""
    out=[];prev=None;active=False
    for lon,lat in points:
        x,y,z=orthographic(lon,lat,*center)
        if prev is not None:
            px,py,pz=prev
            if (z>=0)!=(pz>=0):
                f=pz/(pz-z);hx=px+(x-px)*f;hy=py+(y-py)*f
                # Put the interpolated crossing exactly on the horizon circle.
                length=math.hypot(hx,hy)
                if length:hx/=length;hy/=length
                if pz>=0:out.append(f'L{cx+r*hx:.2f},{cy+r*hy:.2f}');active=False
                else:out.append(f'M{cx+r*hx:.2f},{cy+r*hy:.2f}');active=True
        if z>=0:
            out.append(f'{"L" if active else "M"}{cx+r*x:.2f},{cy+r*y:.2f}');active=True
        else:active=False
        prev=(x,y,z)
    return ' '.join(out)

def svg(body,title,t):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 450" role="img" aria-label="{e(title)}"><title>{e(title)}</title><rect width="900" height="450" fill="{t["ocean"]}"/><g font-family="Arial,sans-serif" fill="{t["ink"]}">{body}</g></svg>'

def points_svg(legs,t,map_svg):
    # Numbered airport badges with a separate key prevent code-label collisions.
    base,_=map_svg([],t);marks=[];placed=[];pts=endpoints(legs)
    base=base.replace('Flight route map','Airport footprint').replace('0 of 0 legs mapped as 0 routes with approximate great-circle arcs; thicker lines were flown more often. Airport list and route details are in the ledger.','Numbered evidenced airport locations, including transit. No country visits are inferred.')
    for i,(code,(lon,lat)) in enumerate(sorted(pts.items())):
        x,y=(lon+180)*2.5,(90-lat)*2.5;bx,by=x,y
        candidates=[(x,y)]
        for radius in range(22,133,22):
            candidates.extend((x+radius*math.cos(a*math.pi/6),y+radius*math.sin(a*math.pi/6)) for a in range(12))
        for px,py in candidates:
            if 12<=px<=888 and 12<=py<=438 and all(math.hypot(px-qx,py-qy)>=23 for qx,qy in placed):bx,by=px,py;break
        placed.append((bx,by))
        marks.append(f'<g data-airport="{e(code)}"><title>{i+1}: {e(code)}</title><path d="M{x:.1f},{y:.1f}L{bx:.1f},{by:.1f}" stroke="{t["accent"]}" stroke-width="1"/><circle cx="{x:.1f}" cy="{y:.1f}" r="2.3" fill="{t["accent"]}"/><circle cx="{bx:.1f}" cy="{by:.1f}" r="9" fill="{t["accent"]}"/><text x="{bx:.1f}" y="{by+3.4:.1f}" text-anchor="middle" fill="{t["paper"]}" font-size="10" font-family="Arial,sans-serif">{i+1}</text></g>')
    base=base.replace('</svg>',''.join(marks)+'</svg>').replace('viewBox="0 0 900 450"','x="0" y="0" width="900" height="332" viewBox="0 0 900 450"',1)
    key=[]
    for i,code in enumerate(sorted(pts)[:24]):
        x=40+(i%8)*108;y=356+(i//8)*22
        key.append(f'<text x="{x}" y="{y}" font-size="12"><tspan fill="{t["accent"]}" font-weight="700">{i+1:02d}</tspan>  {e(code)}</text>')
    key.append(f'<text x="40" y="432" font-size="10" fill="{t["muted"]}">{len(pts)} evidenced airports, including transit. '+('Key shows first 24; see ledger for all airports. ' if len(pts)>24 else '')+'No country visits are inferred.</text>')
    return svg(base+''.join(key),'Airport footprint with numbered markers and airport-code key',t)

def _xyz(lon,lat):
    l,p=math.radians(lon),math.radians(lat)
    return (math.cos(p)*math.cos(l),math.cos(p)*math.sin(l),math.sin(p))

def _mean_center(points):
    """Centre of a weighted set of (lon,lat) points on the sphere, or None if they cancel out."""
    x=y=z=0.0
    for (lon,lat),w in points:
        a,b,c=_xyz(lon,lat);x+=a*w;y+=b*w;z+=c*w
    norm=math.sqrt(x*x+y*y+z*z);total=sum(w for _,w in points) or 1
    if norm/total<0.05:return None
    return (math.degrees(math.atan2(y,x)),math.degrees(math.asin(max(-1,min(1,z/norm)))))

def _antipode(center):
    return ((center[0]+360)%360-180,-center[1])

def globe_centers(legs,pts):
    """Pick two views from where the airports are: the busiest region first, then whatever it hides."""
    if not pts:return [(0,20),(180,-20)],True
    visits=collections.Counter()
    for leg in legs:
        for side in ('origin','destination'):
            if str(leg.get(side)) in pts:visits[str(leg.get(side))]+=1
    weighted=[(pts[c],visits.get(c,1)) for c in pts]
    first=_mean_center(weighted) or max(weighted,key=lambda pw:pw[1])[0]
    hidden=[(pt,w) for pt,w in weighted if orthographic(*pt,*first)[2]<0.25]
    second=None
    if hidden:
        # Of the hidden airports' own positions, their centre and the antipode, take the view that faces them best.
        candidates=[pt for pt,_ in hidden]+[c for c in (_mean_center(hidden),_antipode(first)) if c]
        covers=lambda c:all(max(orthographic(*pt,*first)[2],orthographic(*pt,*c)[2])>=0 for pt,_ in weighted)
        ranked=sorted(candidates,key=lambda c:-sum(w*max(0,orthographic(*pt,*c)[2]) for pt,w in hidden))
        second=next((c for c in ranked if covers(c)),None)
    if second is None:
        return [first,_antipode(first)],True
    opposite=sum(a*b for a,b in zip(_xyz(*first),_xyz(*second)))<-0.85
    return [first,second],opposite

def globe_svg(legs,t,asset,arc,coordinates):
    pts=endpoints(legs);centers,opposite=globe_centers(legs,pts)
    geo=json.loads(Path(asset).read_text());coasts=[]
    for feature in geo['features']:
        geom=feature['geometry'];polys=[geom['coordinates']] if geom['type']=='Polygon' else geom['coordinates']
        for polygon in polys:
            for ring in polygon:
                dense=[]
                for a,b in zip(ring,ring[1:]):
                    lon,lat=a[:2];dl=(b[0]-lon+180)%360-180;steps=max(1,int(max(abs(dl),abs(b[1]-lat))))
                    dense.extend((lon+dl*i/steps,lat+(b[1]-lat)*i/steps) for i in range(steps))
                if dense:coasts.append(dense)
    body=[]
    for side,center in enumerate(centers):
        cx=230+side*440;cy=228;radius=172
        def path(points):return visible_path(points,center,cx,cy,radius)
        paths=[f'<path d="{path(c)}"/>' for c in coasts]
        grid=[]
        for lon in range(-180,180,30):grid.append(f'<path d="{path([(lon,lat) for lat in range(-90,91,2)])}"/>')
        for lat in range(-60,90,30):grid.append(f'<path d="{path([(lon,lat) for lon in range(-180,181,2)])}"/>')
        routes=[];drawn=set()
        for leg in legs:
            p=coordinates(leg);pair=tuple(sorted((str(leg.get('origin')),str(leg.get('destination')))))
            if p and pair not in drawn:drawn.add(pair);routes.append(f'<path d="{path(arc(*p,steps=180))}"/>')
        marks=[]
        for code,(lon,lat) in pts.items():
            x,y,z=orthographic(lon,lat,*center)
            if z< -1e-12:continue
            marks.append(f'<circle data-airport="{e(code)}" cx="{cx+radius*x:.2f}" cy="{cy+radius*y:.2f}" r="3.7" fill="{t["accent"]}"><title>{e(code)}</title></circle>')
        body.append(f'<defs><clipPath id="globe-clip-{side}"><circle cx="{cx}" cy="{cy}" r="{radius}"/></clipPath></defs><text x="{cx}" y="30" text-anchor="middle" font-size="11" letter-spacing="3" fill="{t["accent"]}">{("FIRST HEMISPHERE" if opposite else "FIRST VIEW") if side==0 else ("OPPOSITE HEMISPHERE" if opposite else "SECOND VIEW")}</text><circle cx="{cx}" cy="{cy}" r="{radius+7}" fill="none" stroke="{t["line"]}"/><circle cx="{cx}" cy="{cy}" r="{radius}" fill="{t["paper"]}"/><g clip-path="url(#globe-clip-{side})"><g fill="none" stroke="{t["line"]}" stroke-width=".7">{"".join(grid)}</g><g fill="none" stroke="{t["muted"]}" stroke-width=".9" opacity=".7">{"".join(paths)}</g><g fill="none" stroke="{t["accent"]}" stroke-width="2">{"".join(routes)}</g>{"".join(marks)}</g>')
    body.append(f'<text x="450" y="431" text-anchor="middle" font-size="11" fill="{t["muted"]}">{len(pts)} evidenced airport locations · Two orthographic views centred on your airports · Approximate route arcs</text>')
    return svg(''.join(body),'Two opposite orthographic hemispheres with horizon-clipped routes',t)

def ordered_legs(legs):
    # Stable sorting preserves evidence order for same-date legs; do not invent times.
    return sorted(legs,key=lambda l:str(l.get('departure_date') or '9999'))

MONTHS='Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()

def _span(first,last):
    a,b=first.split('-'),last.split('-')
    if first==last:return f'{MONTHS[int(a[1])-1]} {a[0]}'
    if a[0]==b[0]:return f'{MONTHS[int(a[1])-1]}–{MONTHS[int(b[1])-1]} {a[0]}'
    return f'{MONTHS[int(a[1])-1]} {a[0]} – {MONTHS[int(b[1])-1]} {b[0]}'

def journey_periods(legs,limit=8):
    """Group many legs into at most `limit` calendar periods (months, quarters, years or wider)."""
    dated=[l for l in ordered_legs(legs) if len(str(l.get('departure_date') or ''))>=7]
    if not dated:return []
    def bucket(l,months):
        y,m=map(int,str(l['departure_date'])[:7].split('-'));index=(y*12+m-1)//months
        return index
    for months in (1,3,6,12,24,36,60,120):
        groups=collections.OrderedDict()
        for l in dated:groups.setdefault(bucket(l,months),[]).append(l)
        if len(groups)<=limit:break
    periods=[]
    for rows in groups.values():
        airports=collections.Counter()
        for l in rows:airports.update(str(l.get(k)) for k in ('origin','destination') if l.get(k))
        routes=collections.Counter(f"{l.get('origin')} → {l.get('destination')}" for l in rows)
        known=[l.get('scheduled_minutes') for l in rows if isinstance(l.get('scheduled_minutes'),(int,float))]
        periods.append({'label':_span(str(rows[0]['departure_date'])[:7],str(rows[-1]['departure_date'])[:7]),'legs':len(rows),'airports':[c for c,_ in airports.most_common(4)],'airport_count':len(airports),'top_route':routes.most_common(1)[0],'minutes':sum(known),'unknown':len(rows)-len(known)})
    return periods

def timeline_svg(legs,t):
    ordered=ordered_legs(legs)
    if len(ordered)>8:return journey_summary_svg(ordered,t)
    shown=ordered[:8];body=[]
    for i,leg in enumerate(shown):
        col=i//4;row=i%4;x=45+col*445;y=55+row*87
        if row<3 and i+1<len(shown):body.append(f'<path d="M{x+16},{y+24}V{y+86}" stroke="{t["line"]}" stroke-width="2" stroke-dasharray="4 4"/>')
        body.append(f'<circle cx="{x+16}" cy="{y+13}" r="16" fill="{t["accent"]}"/><text x="{x+16}" y="{y+17}" text-anchor="middle" font-size="11" fill="{t["paper"]}">{i+1:02d}</text><text x="{x+45}" y="{y}" font-size="11" fill="{t["muted"]}">{e(leg.get("departure_date"))}</text><text x="{x+45}" y="{y+27}" font-size="24" font-weight="700">{e(leg.get("origin"))} → {e(leg.get("destination"))}</text><text x="{x+45}" y="{y+48}" font-size="11" fill="{t["muted"]}">{e(str(leg.get("airline","Unknown carrier"))[:32])} · {e(str(leg.get("status","unknown")).replace("_"," "))}</text>')
    if not shown:body.append('<text x="45" y="100" font-size="22">No included journeys.</text>')
    body.append(f'<text x="45" y="420" font-size="11" fill="{t["muted"]}">Showing {len(shown)} of {len(ordered)} legs in departure-date order. Same-date order follows evidence; no transfer is implied.</text>')
    return svg(''.join(body),'Journey timeline in departure-date order',t)

def journey_summary_svg(ordered,t):
    periods=journey_periods(ordered);body=[];shown=sum(p['legs'] for p in periods)
    for i,p in enumerate(periods):
        col=i//4;row=i%4;x=45+col*445;y=55+row*87
        if row<3 and i+1<len(periods):body.append(f'<path d="M{x+16},{y+24}V{y+86}" stroke="{t["line"]}" stroke-width="2" stroke-dasharray="4 4"/>')
        hours=f'{p["minutes"]//60:,}h {p["minutes"]%60:02d}m' if p['minutes'] else 'time unknown'
        if p['unknown'] and p['minutes']:hours+=f' + {p["unknown"]} unknown'
        codes=' · '.join(e(c) for c in p['airports'])+(f' +{p["airport_count"]-len(p["airports"])}' if p['airport_count']>len(p['airports']) else '')
        route,count=p['top_route']
        body.append(f'<circle cx="{x+16}" cy="{y+13}" r="16" fill="{t["accent"]}"/><text x="{x+16}" y="{y+17}" text-anchor="middle" font-size="11" fill="{t["paper"]}">{p["legs"]}</text><text x="{x+45}" y="{y}" font-size="11" fill="{t["muted"]}">{e(p["label"])} · {p["legs"]} leg{"s" if p["legs"]!=1 else ""} · {e(hours)}</text><text x="{x+45}" y="{y+27}" font-size="22" font-weight="700">{codes}</text><text x="{x+45}" y="{y+48}" font-size="11" fill="{t["muted"]}">Most flown: {e(route)}{f" ×{count}" if count>1 else ""}</text>')
    count=f'All {shown} legs' if shown==len(ordered) else f'{shown} of {len(ordered)} legs ({len(ordered)-shown} without a month)'
    body.append(f'<text x="45" y="420" font-size="11" fill="{t["muted"]}">{count}, grouped into {len(periods)} periods. Circles count legs; airports are the busiest in each period. No transfer is implied.</text>')
    return svg(''.join(body),'Journey timeline grouped by period',t)
