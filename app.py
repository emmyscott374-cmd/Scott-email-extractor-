from flask import Flask, request, jsonify, send_file, render_template
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from io import BytesIO, StringIO
from threading import Lock
import csv, re, time, uuid
import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
JOBS = {}
LOCK = Lock()
EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+")
HEADERS = {'User-Agent': 'PublicBusinessEmailFinder/1.0 (public page contact discovery; respectful rate limits)'}


def normalize_url(value):
    value = (value or '').strip()
    if not value:
        return ''
    if not re.match(r'^https?://', value, re.I):
        value = 'https://' + value
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return ''
    return value


def robots_allows(url):
    parsed = urlparse(url)
    robots_url = f'{parsed.scheme}://{parsed.netloc}/robots.txt'
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = requests.get(robots_url, headers=HEADERS, timeout=8)
        if response.status_code == 404:
            return True
        if response.status_code >= 400:
            return False
        parser.parse(response.text.splitlines())
        return parser.can_fetch(HEADERS['User-Agent'], url)
    except requests.RequestException:
        return False


def scan_one(item, delay=0.8):
    store = normalize_url(item.get('store_url', ''))
    if not store:
        return result(item, '', 'Invalid store URL', 'invalid_url')

    # Default two-page workflow: Shopify privacy policy and contact page.
    # Paths can be customized in the UI, but both pages are always checked.
    source_paths = item.get('source_paths') or ['/policies/privacy-policy', '/pages/contact']
    if isinstance(source_paths, str):
        source_paths = [p.strip() for p in source_paths.split(',') if p.strip()]
    source_urls = []
    found_emails = set()
    statuses = []
    notes = []

    for source_path in source_paths[:2]:
        source_path = (source_path or '').strip()
        if not source_path:
            continue
        if not source_path.startswith('/'):
            source_path = '/' + source_path
        source = urljoin(store.rstrip('/') + '/', source_path)
        if urlparse(source).netloc.lower() != urlparse(store).netloc.lower():
            statuses.append('external_source_blocked')
            notes.append(f'{source}: source page must belong to the supplied store domain')
            continue
        if not robots_allows(source):
            statuses.append('blocked_by_robots')
            notes.append(f'{source}: robots.txt disallows access or could not be checked')
            continue
        time.sleep(delay)
        try:
            response = requests.get(source, headers=HEADERS, timeout=15, allow_redirects=True)
            if response.status_code >= 400:
                statuses.append('http_error')
                notes.append(f'{source}: HTTP {response.status_code}')
                continue
            if urlparse(response.url).netloc.lower() != urlparse(store).netloc.lower():
                statuses.append('external_redirect_blocked')
                notes.append(f'{source}: redirected outside the store domain; not scanned')
                continue
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type and 'text/plain' not in content_type:
                statuses.append('unsupported_content')
                notes.append(f'{source}: page is not HTML or plain text')
                continue
            source_urls.append(response.url)
            soup = BeautifulSoup(response.text, 'html.parser')
            for node in soup(['script', 'style', 'noscript', 'svg']):
                node.decompose()
            page_emails = set(EMAIL_RE.findall(soup.get_text(' ', strip=True)))
            for link in soup.select('a[href^="mailto:"]'):
                address = link.get('href', '').split(':', 1)[1].split('?', 1)[0].strip()
                if EMAIL_RE.fullmatch(address):
                    page_emails.add(address)
            page_emails = {e.strip('.,;:()[]{}<>').lower() for e in page_emails
                           if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.svg'))
                           and 'example.com' not in e.lower() and 'yourdomain' not in e.lower()}
            found_emails.update(page_emails)
            statuses.append('checked_with_email' if page_emails else 'checked_no_email')
        except requests.RequestException as exc:
            statuses.append('request_error')
            notes.append(f'{source}: could not access page ({exc.__class__.__name__})')

    source_display = '; '.join(source_urls)
    if found_emails:
        return {'store_url': item.get('store_url', ''), 'source_url': source_display,
                'emails': '; '.join(sorted(found_emails)), 'status': 'found',
                'notes': '; '.join(notes)}
    if 'checked_no_email' in statuses:
        status = 'no_email_found' if all(s in ('checked_no_email', 'checked_with_email') for s in statuses) else 'partial_no_email_found'
        return {'store_url': item.get('store_url', ''), 'source_url': source_display,
                'emails': '', 'status': status,
                'notes': '; '.join(notes) or 'No email was publicly listed on the checked pages.'}
    status = statuses[0] if statuses else 'request_error'
    return {'store_url': item.get('store_url', ''), 'source_url': source_display,
            'emails': '', 'status': status, 'notes': '; '.join(notes) or 'No pages could be checked.'}


def result(item, source, value, status):
    return {'store_url': item.get('store_url', ''), 'source_url': source, 'emails': value if status in ('found', 'no_email_found') else '', 'status': status, 'notes': '' if status in ('found', 'no_email_found') else value}


def run_job(job_id, items):
    with LOCK:
        JOBS[job_id]['status'] = 'running'
        JOBS[job_id]['total'] = len(items)
    # Conservative concurrency and a per-request pause; does not bypass site controls.
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(scan_one, item, 0.8) for item in items]
        for future in as_completed(futures):
            row = future.result()
            with LOCK:
                results.append(row)
                JOBS[job_id]['results'] = results.copy()
                JOBS[job_id]['completed'] = len(results)
    with LOCK:
        JOBS[job_id]['results'] = sorted(results, key=lambda r: items.index(next(i for i in items if i.get('store_url') == r['store_url']))) if results else []
        JOBS[job_id]['status'] = 'completed'


@app.get('/')
def index():
    return render_template('index.html')


@app.post('/api/start')
def start_job():
    payload = request.get_json(silent=True) or {}
    items = payload.get('items') or []
    source_paths = payload.get('source_paths') or ['/policies/privacy-policy', '/pages/contact']
    if isinstance(source_paths, str):
        source_paths = [p.strip() for p in source_paths.split(',') if p.strip()]
    source_paths = [p for p in source_paths if isinstance(p, str) and p.strip()][:2]
    if not source_paths:
        source_paths = ['/policies/privacy-policy', '/pages/contact']
    if not isinstance(items, list) or not items:
        return jsonify(error='Add at least one store URL or upload a CSV.'), 400
    if len(items) > 2000:
        return jsonify(error='A batch can contain at most 2,000 stores.'), 400
    cleaned = []
    for item in items:
        if isinstance(item, str):
            item = {'store_url': item}
        if not isinstance(item, dict):
            continue
        store_url = normalize_url(item.get('store_url', item.get('store', '')))
        source_url = normalize_url(item.get('source_url', item.get('page_url', '')))
        if store_url:
            cleaned.append({'store_url': store_url, 'source_url': source_url, 'source_paths': ([urlparse(source_url).path or '/'] + [p for p in source_paths if p != (urlparse(source_url).path or '/')])[:2] if source_url else source_paths})
    if not cleaned:
        return jsonify(error='No valid store URLs were found.'), 400
    job_id = uuid.uuid4().hex[:12]
    with LOCK:
        JOBS[job_id] = {'status': 'queued', 'total': len(cleaned), 'completed': 0, 'results': []}
    from threading import Thread
    Thread(target=run_job, args=(job_id, cleaned), daemon=True).start()
    return jsonify(job_id=job_id, total=len(cleaned))


@app.get('/api/status/<job_id>')
def status(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify(error='Job not found. Jobs are stored only while this server process is running.'), 404
        return jsonify(job)


@app.post('/api/upload')
def upload():
    file = request.files.get('file')
    if not file:
        return jsonify(error='Choose a CSV file.'), 400
    try:
        text = file.stream.read().decode('utf-8-sig')
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            return jsonify(error='CSV needs a header such as store_url and optional source_url.'), 400
        normalized_headers = {h.lower().strip(): h for h in reader.fieldnames if h}
        store_key = next((normalized_headers[k] for k in ('store_url', 'store', 'website', 'url', 'shop_url') if k in normalized_headers), None)
        source_key = next((normalized_headers[k] for k in ('source_url', 'page_url', 'email_page', 'contact_page') if k in normalized_headers), None)
        if not store_key:
            return jsonify(error='Could not find a store_url column. Use columns store_url and optionally source_url.'), 400
        items = []
        for row in reader:
            item = {'store_url': row.get(store_key, '').strip()}
            if source_key:
                item['source_url'] = row.get(source_key, '').strip()
            if item['store_url']:
                items.append(item)
        return jsonify(items=items, count=len(items))
    except UnicodeDecodeError:
        return jsonify(error='Please upload a UTF-8 CSV file.'), 400


def export_rows(job):
    headers = ['store_url', 'source_url', 'emails', 'status', 'notes']
    return headers, job['results']


@app.get('/api/export/<job_id>/<kind>')
def export(job_id, kind):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify(error='Job not found.'), 404
        headers, rows = export_rows(job)
    output = BytesIO()
    if kind == 'csv':
        text_buffer = StringIO()
        writer = csv.DictWriter(text_buffer, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        return send_file(BytesIO(text_buffer.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name=f'shopify-email-results-{job_id}.csv')
    if kind == 'xlsx':
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Email results'
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(h, '') for h in headers])
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for column, width in {'A': 38, 'B': 48, 'C': 48, 'D': 24, 'E': 52}.items():
            sheet.column_dimensions[column].width = width
        workbook.save(output)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f'shopify-email-results-{job_id}.xlsx')
    return jsonify(error='Export type must be csv or xlsx.'), 400


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
