#!/usr/bin/env python3
"""Render a Flight Atlas summary to a self-contained HTML report (stdlib only)."""
import argparse
import html
import json
import math
from pathlib import Path
from layouts import points_svg, globe_svg, timeline_svg
from airports import lookup

ASSETS = Path(__file__).resolve().parent.parent / 'assets'

def esc(value):
    return html.escape(str(value if value is not None else '—'), quote=True)

def number(value):
    return f'{float(value or 0):,.0f}'

def duration(value):
    if value is None:
        return 'Unknown'
    minutes = round(float(value))
    return f'{minutes // 60:,}h {minutes % 60:02d}m'

def project(lon, lat):
    return (lon + 180) * 2.5, (90 - lat) * 2.5

def arc(lat1, lon1, lat2, lon2, steps=80):
    """Spherical linear interpolation, with deterministic antipodal fallback."""
    def xyz(lat, lon):
        p, l = math.radians(lat), math.radians(lon)
        return (math.cos(p)*math.cos(l), math.cos(p)*math.sin(l), math.sin(p))
    a, b = xyz(lat1, lon1), xyz(lat2, lon2)
    angle = math.acos(max(-1, min(1, sum(x*y for x, y in zip(a, b)))))
    if angle < 1e-9:
        return [(lon1, lat1), (lon2, lat2)]
    if abs(math.sin(angle)) < 1e-7:
        # Exact antipodes have no unique shortest arc; choose a stable orthogonal plane.
        axis = (0, 0, 1) if abs(a[2]) < .9 else (1, 0, 0)
        dot = sum(x*y for x,y in zip(a,axis))
        v = tuple(x-dot*y for x,y in zip(axis,a))
        norm = math.sqrt(sum(x*x for x in v))
        v = tuple(x/norm for x in v)
    else:
        v = tuple((y-x*math.cos(angle))/math.sin(angle) for x,y in zip(a,b))
    result = []
    for i in range(steps+1):
        t = angle*i/steps
        x,y,z = [u*math.cos(t)+w*math.sin(t) for u,w in zip(a,v)]
        result.append((math.degrees(math.atan2(y,x)), math.degrees(math.atan2(z,math.hypot(x,y)))))
    return result

def route_path(points):
    """Clip arc at +/-180, never draw a spurious line across the world."""
    chunks = []
    previous = None
    for lon,lat in points:
        if previous is None:
            x,y = project(lon,lat); chunks.append(f'M{x:.2f},{y:.2f}')
        else:
            oldlon,oldlat = previous
            if abs(lon-oldlon) > 180:
                adjusted = lon-360 if lon>oldlon else lon+360
                edge = -180 if adjusted<oldlon else 180
                fraction = (edge-oldlon)/(adjusted-oldlon)
                crossing = oldlat+(lat-oldlat)*fraction
                x,y=project(edge,crossing); chunks.append(f'L{x:.2f},{y:.2f}')
                x,y=project(-edge,crossing); chunks.append(f'M{x:.2f},{y:.2f}')
            x,y=project(lon,lat); chunks.append(f'L{x:.2f},{y:.2f}')
        previous=(lon,lat)
    return ' '.join(chunks)

def coordinates(leg):
    keys=('origin_lat','origin_lon','destination_lat','destination_lon')
    try:
        p=[float(leg[k]) for k in keys]
        if all(math.isfinite(v) for v in p) and abs(p[0])<=90 and abs(p[2])<=90 and abs(p[1])<=180 and abs(p[3])<=180:
            return p
    except (KeyError,TypeError,ValueError):
        pass
    return None

def map_svg(legs, theme):
    geo=json.loads((ASSETS/'world-land.geojson').read_text())
    land=[]
    for feature in geo['features']:
        geom=feature['geometry']
        polygons=[geom['coordinates']] if geom['type']=='Polygon' else geom['coordinates']
        for polygon in polygons:
            d=[]
            for ring in polygon:
                d.append('M'+' L'.join(f'{project(lon,lat)[0]:.2f},{project(lon,lat)[1]:.2f}' for lon,lat,*_ in ring)+' Z')
            land.append('<path d="'+' '.join(d)+'"/>')
    airports={}; mapped=0; pairs={}
    for leg in legs:
        p=coordinates(leg)
        if p is None: continue
        mapped+=1
        a,b=str(leg.get('origin','?')),str(leg.get('destination','?'))
        airports[a]=(p[1],p[0]); airports[b]=(p[3],p[2])
        # Each airport pair is drawn once; line weight shows how often it was flown (both directions).
        key=tuple(sorted((a,b)))
        entry=pairs.setdefault(key,{'coords':p if (a,b)==key else (p[2],p[3],p[0],p[1]),'flights':0})
        entry['flights']+=1
    busiest=max([e['flights'] for e in pairs.values()]+[1])
    routes=[]
    for (a,b),entry in sorted(pairs.items(),key=lambda kv:kv[1]['flights']):
        share=(entry['flights']-1)/(busiest-1) if busiest>1 else 1
        width=0.9+3.1*share if busiest>1 else 1.6
        label=f'{a} and {b} · {entry["flights"]} flight'+('s' if entry['flights']!=1 else '')
        routes.append(f'<path d="{route_path(arc(*entry["coords"]))}" stroke-width="{width:.2f}" stroke-opacity="{0.45+0.55*share:.2f}"><title>{esc(label)}</title></path>')
    grid=[]
    for lon in range(-150,180,30):
        x,_=project(lon,0);grid.append(f'<path d="M{x},0V450"/>')
    for lat in range(-60,90,30):
        _,y=project(0,lat);grid.append(f'<path d="M0,{y}H900"/>')
    marks=[]
    for code,(lon,lat) in sorted(airports.items()):
        x,y=project(lon,lat)
        marks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3"><title>{esc(code)}</title></circle>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 450" role="img" aria-labelledby="map-title map-desc"><title id="map-title">Flight route map</title><desc id="map-desc">{mapped} of {len(legs)} legs mapped as {len(pairs)} route{'s' if len(pairs)!=1 else ''} with approximate great-circle arcs; thicker lines were flown more often. Airport list and route details are in the ledger.</desc><rect width="900" height="450" fill="{theme['ocean']}"/><g fill="none" stroke="{theme['line']}" stroke-width=".6">{''.join(grid)}</g><g fill="{theme['land']}" fill-rule="evenodd">{''.join(land)}</g><g fill="none" stroke="{theme['accent']}" stroke-linecap="round">{''.join(routes)}</g><g fill="{theme['accent']}" stroke="{theme['paper']}" stroke-width="1">{''.join(marks)}</g></svg>''',mapped

def places_svg(places, theme):
    """World map with the countries stayed in shaded, transit-only countries lightly tinted, and a pin per city."""
    visited={c['country'] for c in places.get('countries',[])}
    transit={c['country'] for c in places.get('transit_only_countries',[])}
    geo=json.loads((ASSETS/'world-countries.geojson').read_text(encoding='utf-8'))
    shapes=[]
    for feature in geo['features']:
        code=feature['properties'].get('iso_a2'); geom=feature['geometry']
        polygons=[geom['coordinates']] if geom['type']=='Polygon' else geom['coordinates']
        d=' '.join('M'+' L'.join(f'{project(lon,lat)[0]:.1f},{project(lon,lat)[1]:.1f}' for lon,lat,*_ in ring)+' Z' for polygon in polygons for ring in polygon)
        fill=theme['accent'] if code in visited or code in transit else theme['land']
        extra=' fill-opacity=".9"' if code in visited else (' fill-opacity=".28"' if code in transit else '')
        name=feature['properties'].get('name') or code or ''
        shapes.append(f'<path d="{d}" fill="{fill}"{extra}><title>{esc(name)}</title></path>')
    pins=[]
    for city in places.get('cities',[]):
        ref=lookup((city.get('airports') or [None])[0]) or {k:city.get(k) for k in ('lat','lon')}
        if not isinstance(ref.get('lat'),(int,float)) or not isinstance(ref.get('lon'),(int,float)): continue
        x,y=project(ref['lon'],ref['lat'])
        pins.append(f'<g transform="translate({x:.1f} {y:.1f})"><title>{esc(city["city"])}</title><path d="M0 0C-1.6-3.2-5-5.4-5-8.6a5 5 0 0 1 10 0C5-5.4 1.6-3.2 0 0Z" fill="{theme["ink"]}" stroke="{theme["paper"]}" stroke-width="1"/><circle cy="-8.6" r="1.8" fill="{theme["paper"]}"/></g>')
    n=len(visited); m=len(places.get('cities',[]))
    legend=(f'<g font-family="Arial, sans-serif" font-size="11" fill="{theme["ink"]}"><rect x="16" y="410" width="12" height="12" fill="{theme["accent"]}" fill-opacity=".9"/><text x="34" y="420">Stayed in</text>'
            f'<rect x="100" y="410" width="12" height="12" fill="{theme["accent"]}" fill-opacity=".28"/><text x="118" y="420">Changed planes only</text>'
            f'<path transform="translate(256 422)" d="M0 0C-1.6-3.2-5-5.4-5-8.6a5 5 0 0 1 10 0C5-5.4 1.6-3.2 0 0Z" fill="{theme["ink"]}"/><text x="266" y="420">City</text></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 450" role="img" aria-labelledby="places-title places-desc"><title id="places-title">Countries and cities visited</title>'
            f'<desc id="places-desc">{n} countries and {m} cities where the flight record shows a stay; transit-only countries are tinted lightly. The lists below name them all.</desc>'
            f'<rect width="900" height="450" fill="{theme["ocean"]}"/><g stroke="{theme["paper"]}" stroke-width=".4" fill-rule="evenodd">{"".join(shapes)}</g><g>{"".join(pins)}</g>{legend}</svg>')

def cover_svg(world, report, metrics, theme):
    """Designed, standalone vector cover; all fonts use local system fallbacks."""
    title=str(report.get('title','Flight Atlas'))
    words=title.split(); lines=[]; current=''
    for word in words:
        if len(current)+len(word)>38 and current:
            lines.append(current); current=''
        current=(current+' '+word).strip()
    if current: lines.append(current)
    if len(lines)>3: lines=lines[:2]+[(lines[2][:35]+'…')]
    lines=lines or ['Flight Atlas']
    title_nodes=''.join(f'<tspan x="60" dy="{0 if i==0 else 54}">{esc(line)}</tspan>' for i,line in enumerate(lines))
    # The layout reserves three title lines; shorter titles pull everything below up instead of leaving a blank band.
    lift=(3-len(lines))*54; height=1080-lift
    period=f"{report.get('start_date','Unspecified start')} to {report.get('end_date','Unspecified end')}"
    stats=[(number(metrics.get('flight_count',0)),'INCLUDED LEGS'),(duration(metrics.get('scheduled_minutes',0)),'SCHEDULED TIME'),(number(metrics.get('airport_count',0)),'AIRPORTS')]
    if 'visited_country_count' in metrics:
        stats=stats[:2]+[(number(metrics['visited_country_count']),'COUNTRIES VISITED'),(number(metrics.get('visited_city_count',0)),'CITIES')]
    step=880//len(stats) if len(stats)>3 else 290
    stat_nodes=''.join(f'<text x="{60+i*step}" y="358" font-size="38" font-weight="700">{esc(value)}</text><text x="{60+i*step}" y="384" font-size="12" letter-spacing="2" fill="{theme["muted"]}">{label}</text>' for i,(value,label) in enumerate(stats))
    country_note='Countries visited leave out airports used only to change planes.' if 'visited_country_count' in metrics else 'Airport countries include transit stops.'
    nested=world.replace('viewBox="0 0 900 450"','x="40" y="430" width="920" height="460" viewBox="0 0 900 450"',1)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}" viewBox="0 0 1000 {height}" role="img" aria-labelledby="cover-title"><title id="cover-title">{esc(title)} report cover</title><rect width="1000" height="{height}" fill="{theme['background']}"/><rect x="24" y="24" width="952" height="{height-48}" rx="12" fill="{theme['paper']}"/><g font-family="Arial, sans-serif" fill="{theme['ink']}"><text x="60" y="77" font-size="13" letter-spacing="3" fill="{theme['accent']}">FLIGHT ATLAS</text><text x="60" y="146" font-size="47" font-family="{theme['heading']}">{title_nodes}</text><g transform="translate(0 {-lift})"><text x="60" y="292" font-size="17" fill="{theme['muted']}">{esc(period)}</text><path d="M60 313H940" stroke="{theme['line']}"/>{stat_nodes}<text x="{60+step}" y="410" font-size="12" fill="{theme['muted']}">{number(metrics.get('known_duration_count',0))} of {number(metrics.get('flight_count',0))} legs with known duration</text>{nested}<text x="60" y="932" font-size="15">Evidence-led. Not a complete travel history.</text><text x="60" y="960" font-size="12" fill="{theme['muted']}">Scheduled travel time is not actual airborne time. Unknown durations are excluded.</text><text x="60" y="981" font-size="12" fill="{theme['muted']}">Great-circle arcs are approximate, not recorded flight tracks. Natural Earth / public domain.</text><text x="60" y="1016" font-size="11" fill="{theme['muted']}">Snapshot: {esc(report.get('as_of','Not supplied'))} · {country_note}</text><a href="https://AR.bd"><text x="940" y="1016" font-size="10" text-anchor="end" fill="{theme['muted']}" opacity=".85">Made with Flight Atlas by M Asif Rahman · AR.bd</text></a></g></g></svg>'''

def luminance(color):
    try:
        r,g,b=(int(color.lstrip('#')[i:i+2],16)/255 for i in (0,2,4))
    except (ValueError,AttributeError):
        return 1.0
    return 0.2126*r+0.7152*g+0.0722*b

MONTH_NAMES='Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()

def short_date(value, year=True):
    try:
        y,mo,d=(int(x) for x in str(value)[:10].split('-'))
        return f'{d} {MONTH_NAMES[mo-1]}'+(f' {y}' if year else '')
    except (ValueError,IndexError):
        return str(value or 'Unknown')

def trip_dates(trip):
    a,b=trip.get('start_date'),trip.get('end_date')
    if a==b: return short_date(a)
    return f'{short_date(a,str(a)[:4]!=str(b)[:4])} – {short_date(b)}'

def trip_name(trip):
    if trip.get('status')=='between_homes' and trip.get('route'):
        ends=[(lookup(c) or {}).get('city') or c for c in (trip['route'][0],trip['route'][-1])]
        return ' → '.join(ends)
    names=[]
    for code in trip.get('destinations',[]):
        city=(lookup(code) or {}).get('city') or code
        if city not in names: names.append(city)
    return ', '.join(names[:3])+(f' +{len(names)-3}' if len(names)>3 else '') or 'Trip'

OPEN_TRIP=('outbound_missing','return_missing','gap')

def trip_status(trip):
    status=trip.get('status'); route=trip.get('route') or []
    if status=='complete' and route and route[0]!=route[-1]:
        return 'Ended at '+((lookup(route[-1]) or {}).get('city') or route[-1])
    if status=='return_after_snapshot' and trip.get('return_booked'):
        return 'Return booked '+short_date(trip['return_booked'].get('date'),False)
    return {'complete':'Round trip','between_homes':'Between homes','outbound_missing':'Outbound not found','return_missing':'Return not found','return_after_snapshot':'Return booked later','return_after_period':'Continues after the report','outbound_before_period':'Began before the report','gap':'Gap mid-trip','explained':'Open end explained'}.get(status,str(status).replace('_',' ').capitalize())

def bars(items, label, value, title, formatter=number, theme=None):
    if not items: return '<p class="muted">No data in this period.</p>'
    maximum=max([float(x.get(value,0) or 0) for x in items]+[1])
    theme=theme or {}; accent=theme.get('accent','#007c78'); ink=theme.get('ink','#142f36'); paper=theme.get('paper','#ffffff')
    # Print turns the page white. Dark themes keep their own card behind the chart so light labels stay legible,
    # matching the map, which also prints in its theme colours.
    backing=f'<rect x="-8" y="-4" width="521" height="{len(items)*39+8}" rx="6" fill="{paper}"/>' if luminance(paper)<0.4 else ''
    rows=[]
    for i,item in enumerate(items):
        val=float(item.get(value,0) or 0); y=i*39
        rows.append(f'<text x="0" y="{y+17}" font-size="12">{esc(str(item.get(label,"Unknown"))[:28])}</text><rect x="195" y="{y+5}" width="{val/maximum*275:.1f}" height="17" rx="3" fill="{accent}"/><text x="495" y="{y+18}" text-anchor="end" font-size="12">{esc(formatter(val))}</text>')
    # Literal colours, not CSS variables: PDF and print renderers often ignore var() inside SVG attributes.
    return f'<svg class="chart" viewBox="-8 -4 521 {len(items)*39+8}" role="img" aria-label="{esc(title)}"><title>{esc(title)}</title>{backing}<g fill="{ink}" font-family="Arial,sans-serif">{"".join(rows)}</g></svg>'

def render(summary, theme_name='atlas', layout='routes', cover_page=False):
    """Return (html, cover_svg). cover_page=True puts the cover on its own first page: the full report for PDF."""
    if layout=='journey':layout='timeline'
    themes=json.loads((ASSETS/'themes.json').read_text())
    if theme_name not in themes:raise ValueError(f'Unknown theme {theme_name!r}; choose one of: '+', '.join(themes))
    t=themes[theme_name];r=summary.get('report',{});m=summary.get('metrics',{})
    legs=summary.get('included_legs',[]);gaps=summary.get('gaps',[]);exclusions=summary.get('exclusions',[])
    world,mapped=map_svg(legs,t)
    descriptions={
        'routes':('The shape of your journeys','Each route is drawn once; thicker lines were flown more often. Great-circle arcs are approximate, not actual flight tracks. Natural Earth land · Equirectangular projection.'),
        'points':('Your airport footprint','Only evidenced airport endpoints are marked, including transit. No country visits are inferred. Natural Earth land · Equirectangular projection.'),
        'globe':('Your world in perspective','Two orthographic views, centred on where your airports are, together show every located endpoint. Each view clips back-side geography and arcs at its horizon. Arcs are approximate, not actual tracks.'),
        'timeline':('A journey, one leg at a time','Departure-date sequence; same-date order follows source evidence. Up to eight legs are shown one by one; longer histories are grouped into periods. No missing connection is invented.')}
    if layout not in descriptions:raise ValueError('Unknown layout: '+str(layout))
    graphic_title,graphic_note=descriptions[layout]
    unconfirmed=any(l.get('status') in ('itinerary_only','strongly_supported') for l in legs)
    if unconfirmed:graphic_note+=' Reconstructed records include unconfirmed itineraries.'
    if layout=='points':world=points_svg(legs,t,map_svg)
    elif layout=='globe':world=globe_svg(legs,t,ASSETS/'world-land.geojson',arc,coordinates)
    elif layout=='timeline':world=timeline_svg(legs,t)
    variables=';'.join(f'--{key}:{t[key]}' for key in ('background','paper','ink','muted','accent','land','ocean','line'))
    metrics=[(number(m.get('flight_count',len(legs))),'included flight legs'),(duration(m.get('scheduled_minutes',0)),f'scheduled travel time · {number(m.get("known_duration_count",0))}/{number(m.get("flight_count",len(legs)))} legs known'),(number(m.get('airport_count',0)),'airports'),(number(m.get('country_count',0)),'airport countries (incl. transit)') if 'visited_country_count' not in m else (number(m['visited_country_count']),f'countries visited · {number(m.get("visited_city_count",0))} cities'),(number(m.get('estimated_distance_km',0))+' km','estimated great-circle distance')]
    cards=''.join(f'<div class="metric"><strong>{a}</strong><span>{b}</span></div>' for a,b in metrics)
    places=summary.get('places') or {}
    places_html=''
    if places.get('countries'):
        country_items=''.join(f'<li><strong>{esc(c["name"])}</strong>{" <small>home</small>" if c.get("home") else ""}<br><span class="muted">{esc(", ".join(c.get("cities",[])))}</span></li>' for c in places['countries'])
        transit=places.get('transit_only_countries',[])
        transit_html=(f'<p class="muted">Changed planes only in {esc(", ".join(c["name"] for c in transit))}: not counted as visited.</p>' if transit else '')
        places_html=(f'<section class="panel places"><div class="section-number">Places</div><h2>Where you stayed</h2>'
                     f'<p class="muted">{number(len(places["countries"]))} countries and {number(len(places.get("cities",[])))} cities, worked out from the order of your flights. '
                     f'A stop counts as a visit when you next left from another airport, stayed at least {places.get("stay_hours",16)} hours, or flew straight back; '
                     f'a shorter connection onwards counts as changing planes. Someone who left the airport on a short connection is still counted as in transit, so these are minimum counts.</p>'
                     f'{places_svg(places,t)}<ul class="country-list">{country_items}</ul>{transit_html}</section>')
    rows=[]
    for leg in legs:
        rows.append('<tr>'+''.join(f'<td>{esc(v)}</td>' for v in (leg.get('departure_date'),f'{leg.get("origin","?")} → {leg.get("destination","?")}',leg.get('airline','Unknown'),leg.get('status','Unknown'),duration(leg.get('scheduled_minutes')),leg.get('duration_basis','Unknown')) )+'</tr>')
    gap_items=[]
    for g in gaps:
        kind=str(g.get('kind','Coverage note')).replace('_',' ').capitalize()
        if g.get('from') and g.get('to'):
            heading=f"{g['from']} → {g['to']} · {kind}"
        else:
            refs=[str(g[k]) for k in ('leg_id','after_id','before_id') if g.get(k)]
            heading=kind+(' · '+', '.join(dict.fromkeys(refs)) if refs else '')
        gap_items.append(f'<li><strong>{esc(heading)}</strong><br>{esc(g.get("note","Evidence is incomplete for this part of the journey."))}</li>')
    gap_html=''.join(gap_items)
    if not gaps:gap_html='<li>No continuity gaps flagged in the supplied data. This does not establish complete travel history.</li>'
    exclusion_html=''.join(f'<li>{esc(x.get("reason",x.get("kind","Excluded")))}{": "+esc(x.get("origin",""))+" → "+esc(x.get("destination","")) if x.get("origin") else ""}</li>' if isinstance(x,dict) else f'<li>{esc(x)}</li>' for x in exclusions)
    routes=summary.get('routes',[])
    route_list=''.join(f'<li><span>{esc(x.get("origin"))} → {esc(x.get("destination"))}</span><strong>{number(x.get("flights"))}</strong></li>' for x in sorted(routes,key=lambda x:x.get('flights',0),reverse=True)[:8]) or '<li>No routes recorded.</li>'
    annual=summary.get('annual',[])
    annual_html=''
    if len(annual)>1:
        annual_rows=''.join('<tr>'+''.join(f'<td>{esc(value)}</td>' for value in (a.get('year'),number(a.get('flights')),duration(a.get('minutes')),number(a.get('unknown_duration_count'))))+'</tr>' for a in annual)
        annual_html='<section class="panel"><div class="section-number">Year over year</div><h2>Annual comparison</h2><div class="scroll"><table><thead><tr><th scope="col">Year</th><th scope="col">Legs</th><th scope="col">Known scheduled time</th><th scope="col">Unknown duration legs</th></tr></thead><tbody>'+annual_rows+'</tbody></table></div></section>'
    time_html='<section class="panel"><div class="section-number">Time in transit</div><h2>Monthly scheduled hours</h2><p class="muted">Known durations only. Missing time is not zero travel.</p>'+bars(summary.get('monthly',[]),'month','minutes','Known scheduled duration by month',duration,t)+'</section>'
    status_html='<h3>Evidence status</h3><ul class="notes">'+''.join(f'<li>{esc(k)}: {number(v)} legs</li>' for k,v in sorted(summary.get('status_counts',{}).items()))+'</ul>'
    warnings_html='<h3>Review warnings</h3><ul class="notes">'+''.join(f'<li>{esc(w)}</li>' for w in summary.get('warnings',[]))+'</ul>' if summary.get('warnings') else ''
    longest_html='<section class="panel"><div class="section-number">Longest scheduled legs</div><h2>The longer journeys</h2><ul class="route-list">'+''.join(f'<li><span>{esc(l.get("origin"))} → {esc(l.get("destination"))}<br><small>{esc(l.get("departure_date"))}</small></span><strong>{duration(l.get("scheduled_minutes"))}</strong></li>' for l in summary.get('longest_legs',[]))+'</ul><p class="muted">Ranked only among legs with known scheduled duration.</p></section>' if summary.get('longest_legs') else ''
    ground_html=''
    if summary.get('ground_segments'):
        ground_html='<h3>Ground transfers (not flights)</h3><ul class="notes">'+''.join(f'<li><strong>{esc(g.get("from","Unspecified origin"))} → {esc(g.get("to","Unspecified destination"))}</strong> · {esc(str(g.get("mode","ground transfer")).replace("_"," "))}<br>{esc(g.get("note","Validated ground connection; excluded from flight counts, flight time, and flight distance."))}</li>' for g in summary['ground_segments'])+'</ul>'
    known=[l for l in legs if l.get('scheduled_minutes') is not None]
    shortest=summary.get('shortest_leg') or (min(known,key=lambda l:l['scheduled_minutes']) if known else None)
    if shortest:
        longest_html=longest_html.replace('</section>',f'<h3>Shortest known scheduled leg</h3><p>{esc(shortest.get("origin"))} → {esc(shortest.get("destination"))} · {duration(shortest.get("scheduled_minutes"))}<br><span class="muted">{esc(shortest.get("departure_date"))}</span></p></section>') if longest_html else f'<section class="panel"><h3>Shortest known scheduled leg</h3><p>{esc(shortest.get("origin"))} → {esc(shortest.get("destination"))} · {duration(shortest.get("scheduled_minutes"))}</p></section>'
    coverage_html=f'<p class="muted">Geographic coverage: {mapped}/{len(legs)} legs mapped; {len(legs)-mapped} unmapped. {number(m.get("unknown_country_endpoint_count",0))} airport occurrences have unknown country. Country counts include departure, arrival, and transit airports, not countries entered.</p>'
    trips=summary.get('trips',[])
    trips_html=''
    if trips:
        homes=', '.join(summary.get('home_airports',[])) or 'not set'
        trip_rows=''.join('<tr>'+''.join(f'<td>{v}</td>' for v in (esc(trip_name(x)),esc(trip_dates(x)),esc(' → '.join(x.get('route',[]))),number(x.get('flights')),esc(duration(x.get('minutes')) if x.get('minutes') else 'Unknown')+(f' <small>+{x["unknown_duration_count"]} unknown</small>' if x.get('unknown_duration_count') and x.get('minutes') else ''),f'<span class="status {esc(x.get("status"))}">{esc(trip_status(x))}</span>'))+'</tr>' for x in trips)
        open_trips=sum(x.get('status') in OPEN_TRIP for x in trips)
        moves=sum(x.get('status')=='between_homes' for x in trips)
        lead=(f'{number(len(trips)-moves)} trips away from home ({esc(homes)}{", assumed" if summary.get("home_inferred") else ""}) and {number(moves)} flight{"s" if moves!=1 else ""} between homes.'
              if moves else f'{number(len(trips))} trips from home ({esc(homes)}{", assumed" if summary.get("home_inferred") else ""}) and back.')
        trips_html=f'<section class="panel trips"><div class="section-number">05 / Trips</div><h2>Every trip, start to finish</h2><p class="muted">{lead} {number(open_trips)} {"is" if open_trips==1 else "are"} not closed by the evidence; open legs are listed, never filled in.</p><div class="scroll"><table><thead><tr><th scope="col">Trip</th><th scope="col">Dates</th><th scope="col">Route</th><th scope="col">Flights</th><th scope="col">Scheduled time</th><th scope="col">Status</th></tr></thead><tbody>{trip_rows}</tbody></table></div></section>'
    title=r.get('title','Flight Atlas')
    css='''.country-list{columns:3 220px;column-gap:28px;padding:0;margin:18px 0 0;list-style:none}.country-list li{break-inside:avoid;margin:0 0 10px}.country-list small{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}*{box-sizing:border-box}body{margin:0;background:var(--background);color:var(--ink);font:15px/1.55 Arial,sans-serif}main{max-width:1200px;margin:auto;padding:54px 36px}a{color:var(--accent)}.eyebrow,.section-number{text-transform:uppercase;letter-spacing:.18em;font-size:11px;font-weight:700;color:var(--accent)}header{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;border-bottom:1px solid var(--line);padding-bottom:30px}h1{font:normal clamp(38px,6vw,72px)/1.06 var(--heading);letter-spacing:-.045em;margin:14px 0 20px;max-width:850px}h2{font:normal 28px/1.2 var(--heading);margin:8px 0 12px}h3{font-size:15px;margin:0 0 15px}.muted,.caption{color:var(--muted)}.stamp{min-width:135px;text-align:right;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:20px;padding:28px 0}.metric strong{display:block;font-size:clamp(22px,2.6vw,34px);letter-spacing:-.04em}.metric span{font-size:11px;color:var(--muted)}.panel{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:26px;margin:18px 0}.map{padding:0;overflow:hidden}.map-head{padding:26px 26px 0}.map svg{display:block;width:100%;height:auto}.caption{font-size:12px;margin:0;padding:16px 26px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.grid .panel{margin:0}.panel svg{width:100%;height:auto}.notes{padding-left:18px;font-size:13px}.notes li{margin:10px 0}.route-list{list-style:none;padding:0;margin:0}.route-list li{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding:10px 0}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:12px}th{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}th,td{padding:13px 10px;border-bottom:1px solid var(--line);vertical-align:top}td:nth-child(2){white-space:nowrap;font-weight:700}footer{font-size:11px;color:var(--muted);padding-top:18px}body.boarding-pass .panel{border-radius:0;border-style:dashed}body.boarding-pass header{border-bottom:2px dashed var(--accent)}body.boarding-pass .eyebrow,body.boarding-pass .stamp{font-family:monospace}body.executive .panel{border-radius:2px}body.executive h1{font-size:48px;font-weight:700}body.midnight .map{box-shadow:0 12px 50px #0003}@media(max-width:760px){main{padding:28px 16px}header{display:block}.stamp{text-align:left;margin-top:18px}.metrics{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.panel{padding:18px}.map{padding:0}.map-head{padding:18px 18px 0}.caption{padding:14px 18px}}td .status{white-space:nowrap;font-weight:700}.status.complete{color:var(--muted);font-weight:400}.cover-page{margin:0 0 36px}.cover-page svg{display:block;width:100%;height:auto;max-width:760px;margin:auto}@media print{.cover-page{break-after:page;margin:0}.cover-page svg{width:100%;max-width:100%;height:auto;max-height:265mm}body{--background:#fff;--paper:#fff;--ink:#182d35;--muted:#53636b;--accent:#116c70;--line:#d0d9dd;color:#182d35}main{max-width:none;padding:0}header{padding-bottom:12px}h1{font-size:40px}@page{margin:12mm}body{font-size:12px}h1{font-size:32px;margin:8px 0 10px}h2{font-size:21px;margin:4px 0 8px}.panel{break-inside:avoid;box-shadow:none!important;margin:10px 0;padding:16px}.map{padding:0}.map-head{padding:14px 16px 0}.caption{padding:10px 16px}.metrics{padding:14px 0}footer{break-before:avoid}.panel.long,.ledger{break-inside:auto}h2,h3,.section-number,.ledger .muted{break-after:avoid}.grid{gap:12px}thead{display:table-header-group}tr{break-inside:avoid}.scroll{overflow:visible}.metrics{gap:12px}.metric strong{font-size:24px}a{color:inherit}footer{font-size:9px}}'''
    cover=cover_svg(world,r,m,t)
    cover=cover.replace('Great-circle arcs are approximate, not recorded flight tracks. Natural Earth / public domain.',{'routes':'Each route drawn once, thicker when flown more often · Approximate great-circle arcs.','points':'Evidenced airport endpoints only, including transit. No country visits are inferred.','globe':'Two orthographic views centred on your airports · Horizon-clipped approximate arcs.','timeline':('Every leg by departure date. ' if len(legs)<=8 else 'All legs grouped by period. ')+'Same-date order follows evidence; transfers are not inferred.'}[layout])
    if unconfirmed:cover=cover.replace('Evidence-led. Not a complete travel history.','Reconstructed records include unconfirmed itineraries.')
    output=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="{'dark' if theme_name=='midnight' else 'light'}"><title>{esc(title)}</title><style>:root{{{variables};--heading:{t['heading']}}}{css}</style></head><body class="{theme_name}"><main>{f'<section class="cover-page" aria-label="Report cover">{cover}</section>' if cover_page else ''}<header><div><div class="eyebrow">Flight Atlas · {esc(t['eyebrow'])}</div><h1>{esc(title)}</h1><div class="muted">{esc(r.get('start_date','Unspecified start'))} to {esc(r.get('end_date','Unspecified end'))}</div></div><div class="stamp">REPORT SNAPSHOT<br>{esc(r.get('as_of','Not supplied'))}<br>Evidence-led · Offline edition</div></header><section class="metrics" aria-label="Summary metrics">{cards}</section><section class="panel map"><div class="map-head"><div class="section-number">01 / Geography</div><h2>{graphic_title}</h2></div>{world}<p class="caption">{esc(graphic_note)} Full flight details and geographic coverage appear below.</p></section>{places_html}<div class="grid"><section class="panel"><div class="section-number">02 / Rhythm</div><h2>Flights by month</h2>{bars(summary.get('monthly',[]),'month','flights','Included flight legs by month',number,t)}</section><section class="panel"><div class="section-number">03 / Carriers</div><h2>Airline mix</h2>{bars(sorted(summary.get('airlines',[]),key=lambda x:x.get('flights',0),reverse=True),'airline','flights','Included flight legs by airline',number,t)}</section></div>{annual_html}<div class="grid">{time_html}{longest_html}</div><section class="panel long"><div class="section-number">04 / Confidence & coverage</div><h2>What this report can tell you</h2><p>{esc(r.get('coverage_note','Based only on supplied evidence; not a complete travel record.'))}</p><p class="muted">Time is scheduled travel time, not measured airborne time. {number(m.get('known_duration_count',0))} legs have a duration; {number(m.get('unknown_duration_count',0))} remain unknown and contribute no time to the total. Distance is estimated from airport coordinates, not miles actually flown.</p>{coverage_html}{status_html}{warnings_html}{ground_html}<div class="grid"><div><h3>Continuity checks</h3><ul class="notes">{gap_html}</ul></div><div><h3>Most frequent routes</h3><ul class="route-list">{route_list}</ul></div></div>{'<h3>Excluded evidence</h3><ul class="notes">'+exclusion_html+'</ul>' if exclusions else ''}</section>{trips_html}<section class="panel ledger"><div class="section-number">{"06" if trips else "05"} / Flight ledger</div><h2>Every included leg</h2><p class="muted">One row per included leg. Status reflects source evidence, not independent confirmation of travel.</p><div class="scroll"><table><thead><tr><th scope="col">Departure date</th><th scope="col">Route</th><th scope="col">Airline</th><th scope="col">Status</th><th scope="col">Scheduled duration</th><th scope="col">Duration basis</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="6">No included flights in this period.</td></tr>'}</tbody></table></div></section><footer>Made with <a href="https://AR.bd">Flight Atlas by M Asif Rahman · AR.bd</a> · Dates follow the supplied source data. Unknown values are not inferred. No raw email text, ticket numbers, booking references, or passenger identifiers are included by this renderer. Map: <a href="https://www.naturalearthdata.com/">Natural Earth</a> (public domain).</footer></main></body></html>'''
    return output,cover

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--theme',choices=['atlas','midnight','boarding-pass','executive'],default='atlas')
    parser.add_argument('--layout',choices=['routes','points','globe','journey','timeline'],default='routes',help='Visualization layout, independent of color theme')
    parser.add_argument('--cover-page',action='store_true',help='Put the cover on its own first page (the full report, ready for PDF)')
    parser.add_argument('--cover',type=Path,help='Also save a designed, self-contained report cover SVG to this path')
    args=parser.parse_args()
    summary=json.loads(args.summary.read_text(encoding='utf-8'))
    if not isinstance(summary,dict):parser.error('summary must be a JSON object')
    rendered,cover=render(summary,args.theme,args.layout,args.cover_page)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(rendered,encoding='utf-8')
    if args.cover:
        args.cover.parent.mkdir(parents=True,exist_ok=True)
        args.cover.write_text(cover,encoding='utf-8')
    print(args.out)

if __name__=='__main__':
    main()
