"""Exercise every deployed scenario for both demo pairs; retain raw evidence."""
import http.cookiejar
import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenarios', nargs='+', help='Only run these scenario IDs')
    parser.add_argument('--output', default='.deploy/scenario-verification.json')
    parser.add_argument('--adaptive', action='store_true', help='Use adaptive thinking for source-model thinking scenarios')
    parser.add_argument('--source-api', choices=['converse', 'invoke', 'chat', 'responses'], default='converse')
    parser.add_argument('--target-api', choices=['converse', 'invoke', 'chat', 'responses'], default='converse')
    parser.add_argument('--source-model', help='Override source model; requires --target-model')
    parser.add_argument('--target-model', help='Override target model; requires --source-model')
    args = parser.parse_args()
    if bool(args.source_model) != bool(args.target_model):
        parser.error('--source-model and --target-model must be provided together')
    base = json.loads((ROOT / '.deploy/state.json').read_text())['url']
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        with opener.open(urllib.request.Request(base + path, data=data,
                headers={'Content-Type': 'application/json'}), timeout=65) as response:
            return json.load(response)

    request('/api/login', {'username': 'admin', 'password': (ROOT / '.deploy/login-password.txt').read_text().strip()})
    catalog = request('/api/catalog')
    if args.scenarios and set(args.scenarios) - set(catalog['scenarios']):
        raise ValueError('Unknown scenario ID')
    evidence = {'url': base, 'startedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'adaptiveSource': args.adaptive, 'sourceApi': args.source_api,
                'targetApi': args.target_api, 'jobs': []}
    path = ROOT / args.output
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    pairs = [(args.source_model, args.target_model)] if args.source_model else [
        ('us.anthropic.claude-opus-4-8', 'us.openai.gpt-5.6-sol'),
        ('us.anthropic.claude-fable-5-1', 'us.openai.gpt-6-astra')]
    for source, target in pairs:
        for scenario, spec in catalog['scenarios'].items():
            if args.scenarios and scenario not in args.scenarios:
                continue
            payload = {'source': source, 'target': target,
                'scenario': scenario, 'input': spec['input'], 'sourceApi': args.source_api, 'targetApi': args.target_api}
            if args.adaptive and spec.get('thinking'):
                payload['sourceFields'] = {'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'medium'}}
            job = request('/api/compare', payload)
            deadline = time.monotonic() + 600
            while job['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(2)
                job = request('/api/jobs/' + job['id'])
            evidence['jobs'].append({'source': source, 'target': target, 'scenario': scenario, 'job': job})
            path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            print(json.dumps({'scenario': scenario, 'target': target, 'status': job['status'],
                'results': [{'model': r['model'], 'error': r.get('error'), 'stop': r.get('stopReason'),
                             'checks': r.get('checks')} for r in job.get('report', {}).get('results', [])]}, ensure_ascii=False), flush=True)
            if job['status'] == 'running':
                raise TimeoutError('Scenario still running; evidence saved')
    request('/api/logout', {})
    print('Evidence: ' + str(path), flush=True)


if __name__ == '__main__':
    main()
