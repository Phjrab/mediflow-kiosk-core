#!/usr/bin/env python3
"""Loopback-only UI fixture server. Never imports eye_server or deployment config.

Render the repository's actual Jinja templates, with synthetic, in-memory API
adapters. This exercises frontend contracts; it is not an inference server.
"""
import argparse
import base64
import io
import json
import re
from pathlib import Path
import sqlite3
import tempfile

from flask import Flask, jsonify, render_template, request, session, Response
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님'
ROUTES = {
    '/': ('index', 'index.html'), '/login': ('login', 'login.html'),
    '/screening': ('screening_select', 'screening_select.html'),
    '/screening/survey': ('screening_survey', 'screening_survey.html'),
    '/screening/capture': ('screening_capture', 'screening_capture.html'),
    '/screening/result': ('screening_result', 'screening_result.html'),
    '/screening/summary': ('screening_summary', 'screening_summary.html'),
    '/capture': ('capture', 'capture.html'), '/result': ('result', 'result.html'),
    '/survey': ('survey', 'survey.html'), '/report': ('report', 'report.html'),
    '/report/pdf': ('report_pdf', 'report_pdf.html'),
    '/training': ('training', 'training.html'),
    '/m': ('mobile_login_page', 'm_login.html'),
    '/m/dashboard': ('mobile_dashboard_page', 'm_dashboard.html'),
    '/admin/config': ('admin_config', 'admin_config.html'),
    '/admin/ai-experiments': ('admin_ai_experiments', 'admin_ai_experiments.html'),
}


def create_app(source=ROOT, data_dir=None):
    source = Path(source)
    app = Flask(__name__, template_folder=str(source / 'web/templates'),
                static_folder=str(source / 'web/static'))
    app.secret_key = 'synthetic-preview-only-not-an-operational-secret'
    app.config.update(TESTING=True, SESSION_COOKIE_HTTPONLY=True, TEMPLATES_AUTO_RELOAD=True)
    image = Image.new('RGB', (960, 600), '#183b39')
    draw = ImageDraw.Draw(image)
    draw.rectangle((180, 150, 780, 440), outline='#b7ded2', width=4)
    draw.ellipse((270, 240, 410, 320), outline='#b7ded2', width=4)
    draw.ellipse((550, 240, 690, 320), outline='#b7ded2', width=4)
    draw.text((300, 390), 'SYNTHETIC IMAGE - NO PATIENT', fill='white')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    png = buffer.getvalue()
    photo = 'data:image/png;base64,' + base64.b64encode(png).decode()
    eye = {'disease': 'Normal', 'confidence': 73.0, 'redness': 0.06,
           'bbox': [270, 240, 410, 320], 'gradcam_status': 'not_generated'}
    analysis = {'left_eye': eye, 'right_eye': None,
                'meta': {'source_resolution': [960, 600], 'fixture_id': 'mediflow-ui-v1'}}
    # Temporary SQLite is deliberately a fixture store, not the clinical schema.
    db = sqlite3.connect(str(Path(data_dir) / 'ui-fixture.sqlite') if data_dir else ':memory:',
                         check_same_thread=False)
    db.execute('CREATE TABLE IF NOT EXISTS surveys (id INTEGER PRIMARY KEY, payload TEXT)')
    app.extensions['ui_fixture_db'] = db
    app.extensions['ui_fixture'] = {'photo': photo, 'analysis': analysis, 'requests': []}

    def page(template):
        if request.path.startswith('/admin/') and not session.get('admin'):
            return Response('Synthetic admin authentication required', status=401)
        return render_template(template, request_id='synthetic-session')

    for route, (endpoint, template) in ROUTES.items():
        app.add_url_rule(route, endpoint, lambda template=template: page(template))
    # Dormant mobile templates can be inspected without claiming production routes.
    for template in ('m_index', 'm_login_start', 'm_survey', 'm_capture', 'm_result', 'm_report'):
        app.add_url_rule('/__fixture/template/' + template, template,
                         lambda template=template: page(template + '.html'))

    @app.after_request
    def mark_fixture(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-MediFlow-Fixture'] = 'synthetic-only'
        if response.mimetype == 'text/html':
            badge = f'<div style="position:absolute;top:0;left:0;right:0;height:28px;z-index:20000;background:#173534;color:white;padding:6px 12px;font:12px sans-serif;text-align:center">{LABEL}</div>'
            html = response.get_data(as_text=True).replace('</head>', '<style>body,body.mf-patient,body.mf-clinical{padding-top:28px}</style></head>')
            response.set_data(re.sub(r'(<body[^>]*>)', lambda match: match.group(1) + badge, html, count=1))
        return response

    @app.route('/__fixture/state', methods=['GET', 'POST'])
    def state():
        if request.method == 'POST':
            session['scenario'] = (request.get_json(silent=True) or {}).get('scenario', 'ready')
        return jsonify(app.extensions['ui_fixture'])

    @app.route('/video_feed')
    @app.route('/video_frame')
    @app.route('/__fixture/image.png')
    def frame():
        return Response(png, mimetype='image/png')

    @app.route('/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def api(path):
        path = '/' + path
        body = request.get_json(silent=True) or {}
        app.extensions['ui_fixture']['requests'].append({'path': path, 'method': request.method})
        scenario = session.get('scenario', 'ready')
        if path == '/api/admin/login':
            if body.get('password') != 'synthetic-admin':
                return jsonify(status='error', message='synthetic credentials rejected'), 401
            session['admin'] = True
            return jsonify(status='ok', csrf_token='fixture-csrf')
        if path.startswith('/api/admin/'):
            if not session.get('admin'):
                return jsonify(status='error', error_code='unauthorized'), 401
            if request.method != 'GET' and request.headers.get('X-Admin-CSRF') != 'fixture-csrf':
                return jsonify(status='error', error_code='csrf'), 403
        if path == '/api/screening/config':
            if scenario == 'config-error':
                return jsonify(status='error'), 503
            return jsonify(status='ok', **json.loads((source / 'config/screening_modalities.json').read_text()))
        if path == '/api/mobile_connected':
            return jsonify(status='ok')
        if path == '/api/verify_pin':
            if body.get('request_id') != 'synthetic-session' or body.get('pin') != '1234':
                return jsonify(status='error', message='Synthetic PIN rejected'), 403
            session['mobile_verified'] = True
            return jsonify(status='ok', redirect_url='/m/dashboard?request_id=synthetic-session')
        if path == '/api/survey':
            if request.method == 'POST':
                db.execute('INSERT INTO surveys(payload) VALUES (?)', (json.dumps(body),))
                db.commit()
                return jsonify(status='ok', survey=body.get('survey', {}))
            return jsonify(status='ok', surveys=[])
        if path == '/api/history':
            return jsonify(status='ok', history=[{
                'id': 1, 'created_at': '2026-10-07 06:00:00', 'image_url': '/__fixture/image.png',
                'analysis': analysis, 'analysis_json': json.dumps(analysis), 'survey': {'age': '30'},
            }])
        if path == '/api/chat/status':
            return jsonify(status='ok', enabled=False, ready=False, provider='local', available=False,
                           reason='provider_unavailable', error_code='provider_unavailable')
        if path == '/detect_status':
            if scenario == 'camera-error':
                return jsonify(detected=False, error='synthetic disconnect'), 503
            return jsonify(detected=scenario == 'ready', confidence=0.85 if scenario == 'ready' else 0,
                           camera_state='streaming' if scenario == 'ready' else 'missing', frame_age_ms=10 if scenario == 'ready' else None,
                           message='눈을 맞춰주세요' if scenario != 'ready' else '눈이 감지되었습니다!')
        if path == '/camera/session/start':
            if scenario == 'camera-missing':
                return jsonify(status='error', message='synthetic camera missing'), 503
            return jsonify(status='ok', camera_role='webcam', camera_device_index=0)
        if path == '/camera/session/stop':
            return jsonify(status='ok')
        if path == '/analyze':
            return jsonify(**analysis)
        if path == '/api/report/dependencies':
            return jsonify(status='ok', ready=False, pdf_ready=False, qr_ready=False)
        if path == '/api/report/share':
            return jsonify(status='ok', share_url='/__fixture/report', qr_url='/__fixture/image.png')
        if path == '/api/admin/config' and request.method == 'GET':
            return jsonify(status='ok', csrf_token='fixture-csrf',
                           config={'CAMERA_DEVICE_INDEX': 0, 'DEBUG_MODE': False},
                           editable_keys=['CAMERA_DEVICE_INDEX', 'DEBUG_MODE'],
                           llm_settings={'LLM_PROVIDER': 'local', 'AI_DEPLOYMENT_PROFILE': 'chat_only'},
                           ai_control={'enabled': True, 'node_id': 'synthetic-node', 'drafts_enabled': True,
                                       'mutations_enabled': False, 'research_guard_ready': True})
        if path == '/api/admin/ai-control/generation':
            return jsonify(status='ok', generation={'temperature': 0.2, 'top_p': 0.9,
                                                    'max_tokens': 256, 'generation_revision': 1})
        if path.endswith('/overview'):
            cache = {'connection_state': 'connected', 'stale': False}
            return jsonify(status='ok', overview={
                'state': {'cache': cache, 'observed_at': '2026-10-07T06:00:00Z',
                          'observed_profile': 'chat_only', 'lifecycle_state': 'ready',
                          'engine': {'process_running': False, 'model_loaded': False, 'inference_ready': False},
                          'telemetry': {}, 'active_operation_id': None,
                          'activity': {'source': 'managed_ingress', 'admission': 'open', 'inflight': 0, 'unknown_inflight': 0}},
                'current_config': {'cache': cache, 'config_revision': 1, 'deployment_generation': 1},
                'capabilities': {'cache': cache, 'drafts_enabled': True, 'mutations_enabled': False,
                                 'managed_ingress_verified': True},
                'models': {'models': [{'engine_kind': kind, 'artifact_id': 'synthetic-' + kind,
                                      'display_name': 'Synthetic ' + kind, 'quantization': 'fixture',
                                      'eligible_for_activation': True, 'presets': [{'preset_id': 'fixture'}]}
                                     for kind in ['chat', 'vlm']]}})
        if path.endswith('/drafts'):
            return jsonify(status='ok', draft={'draft_id': 'fixture-draft'})
        if path.endswith('/plans'):
            return jsonify(status='ok', plan={'plan_id': 'fixture-plan', 'restart_required': True,
                                              'blocking_reasons': ['mutations_disabled'],
                                              'expected_config_revision': 1, 'expected_deployment_generation': 1})
        if path == '/api/admin/ai-experiments/capabilities':
            return jsonify(csrf_token='fixture-csrf', capabilities={
                'enabled': False, 'baseline_enabled': False, 'vlm_enabled': False,
                'survey_enabled': False, 'explanation_enabled': False, 'hybrid_enabled': False,
                'operational_import_ready': False, 'mode': 'research', 'deployment_profile': 'chat_only'})
        if path == '/api/admin/ai-experiments/jobs':
            return jsonify(jobs=[])
        # All unimplemented writes fail closed. No external calls are made.
        return jsonify(status='error', error_code='fixture_action_blocked', message='Synthetic fixture blocks this action'), 403 if request.method != 'GET' else 404

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5097)
    parser.add_argument('--source', type=Path, default=ROOT)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mediflow-ui-fixture-') as directory:
        create_app(args.source, directory).run(host='127.0.0.1', port=args.port,
                                              debug=False, use_reloader=False)
