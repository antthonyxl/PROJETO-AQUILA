"""Carga de sessões Streamlit via WebSocket, sem modificar dados."""
import argparse
import asyncio
import json
import math
import time
from pathlib import Path

from websockets.asyncio.client import connect
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg


async def main(args):
    gate = asyncio.Event()
    release = asyncio.Event()
    results = []
    active = 0
    peak = 0

    async def user(index):
        nonlocal active, peak
        await gate.wait()
        start = time.perf_counter()
        row = {'user': index, 'ok': False, 'login_widgets': 0}
        try:
            async with connect(args.url, subprotocols=['streamlit'],
                               origin='http://127.0.0.1:8501',
                               max_size=32 * 1024 * 1024, open_timeout=30) as ws:
                active += 1
                peak = max(peak, active)
                try:
                    row['connection_s'] = round(time.perf_counter() - start, 3)
                    msg = BackMsg()
                    msg.rerun_script.SetInParent()
                    await ws.send(msg.SerializeToString())
                    async with asyncio.timeout(60):
                        while True:
                            data = await ws.recv()
                            if not isinstance(data, bytes):
                                continue
                            reply = ForwardMsg.FromString(data)
                            kind = reply.WhichOneof('type')
                            if kind == 'delta' and reply.delta.HasField('new_element'):
                                element = reply.delta.new_element
                                if element.HasField('exception'):
                                    raise RuntimeError('Streamlit application exception')
                                if element.HasField('text_input'):
                                    row['login_widgets'] += 1
                                if element.HasField('alert') and element.alert.type == 3:
                                    raise RuntimeError('Streamlit error alert')
                            if kind == 'script_finished':
                                row['script_status'] = int(reply.script_finished)
                                row['ready_s'] = round(time.perf_counter() - start, 3)
                                row['ok'] = row['login_widgets'] == 2 and int(reply.script_finished) == 0
                                break
                    results.append(row)
                    await release.wait()
                finally:
                    active -= 1
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)[:180]
            if row not in results:
                results.append(row)

    tasks = [asyncio.create_task(user(i + 1)) for i in range(args.users)]
    start = time.perf_counter()
    gate.set()
    while len(results) < args.users and time.perf_counter() - start < 95:
        await asyncio.sleep(.1)
    await asyncio.sleep(args.hold)
    release.set()
    await asyncio.gather(*tasks)
    times = sorted(r['ready_s'] for r in results if r['ok'])
    summary = {
        'scope': 'Unauthenticated Streamlit login; no browser rendering or database queries',
        'users': args.users, 'peak_connected': peak,
        'successful': sum(r['ok'] for r in results),
        'failed': sum(not r['ok'] for r in results),
        'hold_seconds_after_all_results': args.hold,
        'duration_s': round(time.perf_counter() - start, 3),
        'ready_seconds': {k: times[min(len(times)-1, max(0, math.ceil(q*len(times))-1))]
                          for k, q in [('p50', .5), ('p95', .95), ('max', 1)]} if times else {},
        'results': results,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'results'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='ws://127.0.0.1:8501/_stcore/stream')
    parser.add_argument('--users', type=int, default=50)
    parser.add_argument('--hold', type=float, default=15)
    parser.add_argument('--output', default='reports/carga_50_login.json')
    asyncio.run(main(parser.parse_args()))
