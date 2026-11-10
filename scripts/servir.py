"""Inicia o Áquila com logs rotativos e sem observador de arquivos de produção."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--address', default='127.0.0.1')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    logs = root / 'logs'
    logs.mkdir(exist_ok=True)
    # Não depender de um pipe de terminal que pode deixar de ser consumido.
    output = open(logs / f'server-{args.port}.console.log', 'a', encoding='utf-8', buffering=1)
    sys.stdout = output
    sys.stderr = output
    handler = RotatingFileHandler(logs / f'server-{args.port}.log',
                                  maxBytes=5_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    for name in ('streamlit', 'uvicorn', 'uvicorn.error', 'uvicorn.access', 'psycopg.pool'):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False
    from streamlit.web.cli import main as streamlit_main
    streamlit_main(args=['run', str(root / 'app.py'),
                         f'--server.address={args.address}', f'--server.port={args.port}',
                         '--server.headless=true', '--server.fileWatcherType=none',
                         '--browser.gatherUsageStats=false'], prog_name='streamlit')


if __name__ == '__main__':
    main()
