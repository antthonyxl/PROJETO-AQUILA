"""Carga WebSocket com reruns, filtros e monitoramento de saúde."""
import argparse
import asyncio
import json
import math
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from websockets.asyncio.client import connect
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg


def stats(values):
    times = sorted(values)
    return {k: times[math.ceil(q*len(times))-1]
            for k, q in [('p50', .5), ('p95', .95), ('max', 1)]} if times else {}


async def main(args):
    release = asyncio.Event()
    results, health = [], []
    active = peak = 0
    urls = args.urls.split(',') if args.urls else [args.url]
    origins = [('https' if urlsplit(url).scheme == 'wss' else 'http') + '://' + urlsplit(url).netloc
               for url in urls]

    def probe(origin):
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(origin + '/_stcore/health', timeout=3) as r:
                return {'target': origin, 'ok': r.status == 200, 'seconds': round(time.perf_counter()-start, 3)}
        except Exception as exc:
            return {'target': origin, 'ok': False, 'error': type(exc).__name__}

    async def monitor():
        while not release.is_set():
            health.extend(await asyncio.gather(*(asyncio.to_thread(probe, origin) for origin in origins)))
            await asyncio.sleep(1)

    async def user(index):
        nonlocal active, peak
        if args.ramp_seconds:
            await asyncio.sleep((index-1) * args.ramp_seconds / args.users)
        start = time.perf_counter()
        backend = (index-1) % len(urls)
        row = {'user': index, 'backend': backend, 'ok': False, 'rounds': []}
        try:
            async with connect(urls[backend], subprotocols=['streamlit'], origin=origins[backend],
                               max_size=32*1024*1024, open_timeout=30,
                               close_timeout=3) as ws:
                active += 1
                peak = max(peak, active)
                try:
                    row['connection_s'] = round(time.perf_counter()-start, 3)
                    month_id = submit_id = None
                    month_options = []
                    navigation_id = theme_id = None
                    for iteration in range(args.rounds):
                        began = time.perf_counter()
                        msg = BackMsg()
                        msg.rerun_script.SetInParent()
                        filtered = bool(args.vary_filters and iteration and month_id and submit_id)
                        if filtered:
                            states = msg.rerun_script.widget_states.widgets
                            states.add(id=month_id).string_value = month_options[index % len(month_options)]
                            states.add(id=submit_id).trigger_value = True
                        if iteration and args.navigate and navigation_id:
                            msg.rerun_script.widget_states.widgets.add(id=navigation_id).trigger_value = True
                        if iteration and args.dark and theme_id:
                            msg.rerun_script.widget_states.widgets.add(id=theme_id).bool_value = True
                        await ws.send(msg.SerializeToString())
                        inputs = charts = 0
                        async with asyncio.timeout(args.timeout):
                            while True:
                                data = await ws.recv()
                                if not isinstance(data, bytes):
                                    continue
                                reply = ForwardMsg.FromString(data)
                                kind = reply.WhichOneof('type')
                                if kind == 'delta' and reply.delta.HasField('new_element'):
                                    e = reply.delta.new_element
                                    if e.HasField('exception'):
                                        raise RuntimeError('Streamlit exception: ' + e.exception.type)
                                    if e.HasField('text_input'):
                                        inputs += 1
                                    if e.HasField('plotly_chart'):
                                        charts += 1
                                    if e.HasField('selectbox') and e.selectbox.label == 'Mês':
                                        month_id = e.selectbox.id
                                        month_options = list(e.selectbox.options)
                                    if e.HasField('button') and e.button.is_form_submitter and e.button.label == 'Aplicar filtros':
                                        submit_id = e.button.id
                                    if e.HasField('button') and e.button.id.endswith('-nav_' + str(args.navigate)):
                                        navigation_id = e.button.id
                                    if e.HasField('checkbox') and e.checkbox.label == 'Modo escuro':
                                        theme_id = e.checkbox.id
                                    if e.HasField('alert') and e.alert.type == 3:
                                        raise RuntimeError('Streamlit error alert')
                                if kind == 'script_finished':
                                    if int(reply.script_finished) != 0:
                                        continue
                                    ok = charts > 0 if args.dashboard else inputs == 2
                                    row['rounds'].append({'seconds': round(time.perf_counter()-began, 3),
                                                          'ok': ok, 'charts': charts,
                                                          'login_widgets': inputs,
                                                          'filter_submitted': filtered})
                                    row['rounds'][-1]['navigation_submitted'] = bool(iteration and args.navigate and navigation_id)
                                    row['rounds'][-1]['dark_submitted'] = bool(iteration and args.dark and theme_id)
                                    if not ok:
                                        raise RuntimeError('Expected page elements missing')
                                    break
                        if iteration + 1 < args.rounds:
                            await asyncio.sleep(1)
                    row['ok'] = True
                    results.append(row)
                    # Drenar mensagens também durante o período de permanência.
                    while not release.is_set():
                        try:
                            await asyncio.wait_for(ws.recv(), timeout=.5)
                        except asyncio.TimeoutError:
                            pass
                finally:
                    active -= 1
        except Exception as exc:
            row['ok'] = False
            row['error'] = type(exc).__name__ + ': ' + str(exc)[:180]
            if row not in results:
                results.append(row)

    start = time.perf_counter()
    monitor_task = asyncio.create_task(monitor())
    tasks = [asyncio.create_task(user(i+1)) for i in range(args.users)]
    try:
        async with asyncio.timeout(args.timeout * args.rounds + 45):
            while len(results) < args.users:
                await asyncio.sleep(.1)
        await asyncio.sleep(args.hold)
    finally:
        release.set()
    await asyncio.gather(*tasks)
    await monitor_task
    health.extend(await asyncio.gather(*(asyncio.to_thread(probe, origin) for origin in origins)))
    summary = {
        'scope': ('Dashboard in isolated authenticated test session; read-only filters; authentication cost excluded'
                  if args.dashboard else 'Unauthenticated login; no browser rendering or database queries'),
        'users': args.users, 'peak_connected': peak,
        'ramp_seconds': args.ramp_seconds, 'hold_seconds': args.hold,
        'successful': sum(r['ok'] for r in results), 'failed': sum(not r['ok'] for r in results),
        'duration_s': round(time.perf_counter()-start, 3),
        'round_seconds': [stats(r['rounds'][i]['seconds'] for r in results
                               if len(r['rounds']) > i and r['rounds'][i]['ok'])
                          for i in range(args.rounds)],
        'health_failed': sum(not h['ok'] for h in health),
        'health_seconds': stats(h['seconds'] for h in health if h['ok']),
        'health': health, 'results': results,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('results', 'health')}, indent=2))
    return summary['failed'] or summary['health_failed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='ws://127.0.0.1:8501/_stcore/stream')
    parser.add_argument('--urls', help='Backends separados por vírgula; distribuição uniforme, sem testar o proxy')
    parser.add_argument('--users', type=int, default=100)
    parser.add_argument('--hold', type=float, default=15)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=90)
    parser.add_argument('--ramp-seconds', type=float, default=0)
    parser.add_argument('--dashboard', action='store_true')
    parser.add_argument('--vary-filters', action='store_true')
    parser.add_argument('--navigate', choices=['geral', 'mensal'])
    parser.add_argument('--dark', action='store_true')
    parser.add_argument('--output', default='reports/carga_sessoes.json')
    args = parser.parse_args()
    if args.users < 1 or args.rounds < 1 or args.hold < 0 or args.ramp_seconds < 0:
        parser.error('users/rounds devem ser positivos e hold não negativo')
    raise SystemExit(1 if asyncio.run(main(args)) else 0)
