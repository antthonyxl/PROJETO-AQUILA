"""Ingestão substitutiva: importa arquivo inteiro antes de ativar a nova versão."""
from __future__ import annotations
import datetime as dt
import decimal
import os
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import psycopg
from openpyxl import load_workbook

COLUNAS = [
    'empresa', 'dta_movimento', 'hora_emissao', 'segmento', 'seqpessoa', 'cliente',
    'cnpjcpf', 'caixa', 'turno', 'cupom_coo', 'cod_produto', 'cod_ean', 'produto',
    'quantidade', 'qtd_emb', 'vlrunitario', 'vlrtotal', 'vlr_desconto',
    'cod_operador', 'op_caixa', 'cod_fiscal', 'fiscal_cx', 'nro_doc', 'status',
    'tipo', 'motivo', 'tipo_desconto'
]
NUMERICAS = {'quantidade', 'qtd_emb', 'vlrunitario', 'vlrtotal', 'vlr_desconto'}


def _valor(campo: str, dado):
    if dado is None or dado == '':
        return None
    if campo == 'dta_movimento':
        if isinstance(dado, dt.datetime):
            return dado.date()
        if isinstance(dado, dt.date):
            return dado
        raise ValueError(f'Data inválida: {dado!r}')
    if campo == 'hora_emissao':
        if isinstance(dado, dt.datetime):
            return dado.time()
        if isinstance(dado, dt.time):
            return dado
        if isinstance(dado, (int, float)):
            seconds = round(float(dado) * 86400) % 86400
            return (dt.datetime.min + dt.timedelta(seconds=seconds)).time()
        return dt.time.fromisoformat(str(dado))
    if campo in NUMERICAS:
        return decimal.Decimal(str(dado))
    return str(dado).strip()


def importar_excel(
    arquivo: str | Path, conexao: str, nome_arquivo: str | None = None,
    progresso: Callable[[int], None] | None = None,
    tamanho_lote: int = 2000,
) -> dict:
    caminho = Path(arquivo)
    wb = load_workbook(caminho, read_only=True, data_only=True)
    lote = uuid.uuid4()
    linhas = 0
    try:
        ws = wb['descontos_pdv'] if 'descontos_pdv' in wb.sheetnames else wb.active
        it = ws.iter_rows(values_only=True)
        cabecalho = next(it)
        real = [str(x or '').strip().lower() for x in cabecalho]
        if real != COLUNAS:
            raise ValueError('Colunas do Excel são diferentes do modelo esperado. A base atual foi preservada.\n'
                             f'Esperado: {COLUNAS}\nRecebido: {real}')
        with psycopg.connect(conexao, autocommit=False) as con:
            with con.cursor() as cur:
                cur.execute('INSERT INTO public.pdv_lotes(id, nome_arquivo) VALUES (%s,%s)',
                            (lote, nome_arquivo or caminho.name))
            con.commit()
            sql = ('COPY public.pdv_descontos (lote_id, linha_excel, ' +
                   ', '.join(COLUNAS) + ') FROM STDIN')
            buffer = []
            for n, linha in enumerate(it, start=2):
                if all(v is None for v in linha):
                    continue
                try:
                    valores = [_valor(col, v) for col, v in zip(COLUNAS, linha, strict=True)]
                except (ValueError, TypeError, decimal.InvalidOperation) as e:
                    raise ValueError(f'Falha na linha {n}: {e}') from e
                buffer.append((lote, n, *valores))
                if len(buffer) >= tamanho_lote:
                    with con.cursor() as cur, cur.copy(sql) as copy:
                        for registro in buffer:
                            copy.write_row(registro)
                    con.commit()  # o lote ainda NÃO está ativo
                    linhas += len(buffer)
                    buffer.clear()
                    if progresso:
                        progresso(linhas)
            if buffer:
                with con.cursor() as cur, cur.copy(sql) as copy:
                    for registro in buffer:
                        copy.write_row(registro)
                con.commit()
                linhas += len(buffer)
                if progresso:
                    progresso(linhas)
            if not linhas:
                raise ValueError('O arquivo não possui registros. A base atual foi preservada.')
            with con.cursor() as cur:
                cur.execute('SELECT public.pdv_ativar_lote(%s)', (lote,))
            con.commit()
        return {'lote_id': str(lote), 'linhas': linhas, 'arquivo': nome_arquivo or caminho.name}
    except Exception:
        # Se der erro antes da ativação, apaga somente o lote novo, sem tocar no ativo.
        try:
            with psycopg.connect(conexao) as con:
                con.execute('DELETE FROM public.pdv_lotes WHERE id=%s AND status=%s', (lote, 'carregando'))
        except Exception:
            pass
        raise
    finally:
        wb.close()


def importar_upload(upload: BinaryIO, conexao: str, progresso=None) -> dict:
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        caminho = tmp.name
        while chunk := upload.read(1024 * 1024):
            tmp.write(chunk)
    try:
        return importar_excel(caminho, conexao, getattr(upload, 'name', 'base.xlsx'), progresso)
    finally:
        os.unlink(caminho)
