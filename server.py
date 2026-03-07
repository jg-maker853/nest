import json, gzip, threading, os, webbrowser, traceback, time
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor, install_opener
from urllib.error import HTTPError
from urllib.parse import quote, unquote_plus
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT          = int(os.environ.get('PORT', 8765))
RENTCAST_KEY  = '3aaba50e374f4bbc84b627083fa3abd8'
GMAPS_KEY     = os.environ.get('GMAPS_KEY', 'AIzaSyDjpA9ue8guByOHNZJEmZzGssVpqtdOqyQ')

CITIES = [
    {'city': 'Gatlinburg',   'state': 'TN'},
    {'city': 'Pigeon Forge', 'state': 'TN'},
    {'city': 'Townsend',     'state': 'TN'},
    {'city': 'Sevierville',  'state': 'TN'},
]

install_opener(build_opener(HTTPCookieProcessor(CookieJar())))
HERE      = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(HERE, 'zillow-dashboard.html')
print(f'Dashboard: {DASHBOARD}  exists={os.path.exists(DASHBOARD)}')

def get_photo_url(lat, lng, address, city, state, zipcode):
    """Return a Street View image URL for a property."""
    if lat and lng:
        loc = f'{lat},{lng}'
    else:
        loc = quote(f'{address}, {city}, {state} {zipcode}'.strip(', '))
    return f'https://maps.googleapis.com/maps/api/streetview?size=800x450&location={loc}&fov=90&pitch=5&key={GMAPS_KEY}'


def fetch_rentcast(city, state):
    url = f'https://api.rentcast.io/v1/listings/sale?city={quote(city)}&state={state}&maxPrice=700000&limit=500&status=Active'
    req = Request(url, headers={'X-Api-Key': RENTCAST_KEY, 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=20) as r:
            raw = r.read()
            if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            text = raw.decode('utf-8')
            print(f'  [{city}] HTTP {r.status} | {len(text):,}b')
            data  = json.loads(text)
            props = data if isinstance(data, list) else (data.get('listings') or data.get('data') or [])
            print(f'  [{city}] {len(props)} listings')
            return props
    except HTTPError as e:
        print(f'  [{city}] HTTP {e.code}: {e.read()[:200].decode("utf-8","replace")}')
    except Exception as e:
        print(f'  [{city}] ERROR: {e}'); traceback.print_exc()
    return []

def norm(p, city):
    price    = p.get('price') or 0
    beds     = p.get('bedrooms') or 0
    baths    = p.get('bathrooms') or 0
    sqft     = p.get('squareFootage') or 0
    lot_sf   = p.get('lotSize') or 0
    ptype    = (p.get('propertyType') or '').lower()
    is_land  = 'land' in ptype or 'lot' in ptype
    lot_disp = f'{lot_sf/43560:.2f} ac' if lot_sf else 'N/A'
    days_on  = p.get('daysOnMarket') or 0
    lat      = p.get('latitude')
    lng      = p.get('longitude')
    addr     = p.get('addressLine1') or p.get('formattedAddress') or ''
    zip_     = p.get('zipCode') or ''
    city_p   = p.get('city') or city
    state_p  = p.get('state') or 'TN'
    agent_obj = p.get('listingAgent') or {}
    agent    = (agent_obj.get('name') if isinstance(agent_obj, dict) else None) or p.get('agentName') or p.get('brokerName') or 'Listed Agent'
    city_str = f"{city_p}, {state_p} {zip_}".strip()

    # Zillow search URL for "View on Zillow" button
    search_q  = f'{addr}, {city_p}, {state_p} {zip_}'.strip(', ')
    zillow_url = f'https://www.zillow.com/homes/{quote(search_q)}_rb/'

    # Photo: Street View using lat/lng
    img = get_photo_url(lat, lng, addr, city_p, state_p, zip_)

    return {
        'id':          str(p.get('id') or id(p)),
        'rawCity':     city,
        'type':        'land' if is_land else 'house',
        'badge':       'New' if days_on <= 2 else '',
        'badgeClass':  '',
        'price':       price,
        'addr':        addr or 'Address unavailable',
        'city':        city_str,
        'beds':        beds,
        'baths':       baths,
        'sqft':        sqft,
        'lot':         lot_disp,
        'daysAgo':     days_on,
        'psf':         round(price / sqft) if price and sqft else 0,
        'lat':         lat,
        'lng':         lng,
        'img':         img,
        'imgFallback': img,
        'photos':      [img],
        'agent':       agent,
        'initials':    ''.join(w[0] for w in str(agent).split())[:2].upper() or 'AG',
        'desc':        f"{beds} bed, {baths} bath {'lot' if is_land else 'home'} in {city_p}, TN.",
        'detailUrl':   zillow_url,
        'zillowUrl':   zillow_url,
        'zestimate':   0,
    }

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200); self.cors(); self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        qs   = self.path[len(path)+1:] if '?' in self.path else ''

        # ── /api/listings ──────────────────────────────────────────────────────
        if path == '/api/listings':
            print('\n=== FETCH ===')
            all_l, errs = [], []
            for c in CITIES:
                props = fetch_rentcast(c['city'], c['state'])
                if not props: errs.append(c['city'])
                for p in props:
                    try:
                        all_l.append(norm(p, c['city']))
                    except Exception as ex:
                        print(f'  norm err: {ex}')
            print(f'=== DONE: {len(all_l)} listings ===\n')
            body = json.dumps({'listings': all_l, 'errors': errs}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.cors(); self.end_headers(); self.wfile.write(body)

        # ── /api/photo ─────────────────────────────────────────────────────────
        elif path == '/api/photo':
            params = {}
            for part in qs.split('&'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    params[k] = unquote_plus(v)
            addr  = params.get('addr', '')
            city  = params.get('city', '')
            state = params.get('state', 'TN')
            zip_  = params.get('zip', '')
            lat   = params.get('lat', '')
            lng   = params.get('lng', '')
            try: lat = float(lat); lng = float(lng)
            except: lat = lng = None
            photo_url = get_photo_url(lat, lng, addr, city, state, zip_)
            result = json.dumps({'url': photo_url}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.cors(); self.end_headers(); self.wfile.write(result)

        # ── / (dashboard) ──────────────────────────────────────────────────────
        elif path in ('/', '/index.html'):
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(open(DASHBOARD, 'rb').read())
            except FileNotFoundError:
                self.send_response(404); self.end_headers()
                self.wfile.write(b'Put zillow-dashboard.html next to server.py')
        else:
            self.send_response(404); self.end_headers()

print('='*52)
print(f'  Nest Server  ->  http://localhost:{PORT}')
print('  Ctrl+C to stop')
print('='*52)
server = HTTPServer(('0.0.0.0', PORT), H)
if PORT == 8765:
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(f'http://localhost:{PORT}')), daemon=True).start()
try:
    server.serve_forever()
except KeyboardInterrupt:
    print('Stopped.')
