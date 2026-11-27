"""Carga integral e atômica da planilha ROB de três colunas (loja, receita, ano/mês)."""
from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from aquila_seguranca import salvar_upload_xlsx_temporario, validar_arquivo_xlsx


CABECALHO = ("Loja", "Vlr Venda Atual", "Ano/Mês")
REGEX_CODIGO = re.compile(r"^\s*(\d{3})(?:\D|$)")
REGEX_MES = re.compile(r"^(20\d{2})/(0[1-9]|1[0-2])$")


def converter_linha(linha: tuple, numero_linha: int) -> tuple[str, str, dt.date, decimal.Decimal]:
    if len(linha) != 3:
        raise ValueError(f"Linha {numero_linha}: esperadas 3 colunas, recebidas {len(linha)}")
    loja_original, venda, mes_original = linha
    loja = str(loja_original or "").strip()
    m = REGEX_CODIGO.match(loja)
    if not m:
        raise ValueError(f"Linha {numero_linha}: código de loja inválido: {loja!r}")
    if isinstance(mes_original, (dt.date, dt.datetime)):
        mes = dt.date(mes_original.year, mes_original.month, 1)
    else:
        padrao = REGEX_MES.fullmatch(str(mes_original or "").strip())
        if not padrao:
            raise ValueError(f"Linha {numero_linha}: Ano/Mês inválido: {mes_original!r}; use AAAA/MM")
        mes = dt.date(int(padrao.group(1)), int(padrao.group(2)), 1)
    try:
        receita = decimal.Decimal(str(venda))
        if not receita.is_finite():
            raise decimal.InvalidOperation
        # Precisão compatível com numeric(20,2); não arredondar valores monetários silenciosamente.
        receita = receita.quantize(decimal.Decimal('0.01'))
    except (TypeError, decimal.InvalidOperation, ValueError) as erro:
        raise ValueError(f"Linha {numero_linha}: valor de receita inválido: {venda!r}") from erro
    return m.group(1), loja, mes, receita


def importar_rob_excel(
    arquivo: str | Path, conexao: str, nome_arquivo: str | None = None,
    progresso: Callable[[int], None] | None = None, tamanho_lote: int = 1500,
) -> dict:
    caminho = Path(arquivo)
    validar_arquivo_xlsx(caminho)
    import psycopg
    from openpyxl import load_workbook
    wb = load_workbook(caminho, read_only=True, data_only=True)
    lote_id = uuid.uuid4()
    criadas = 0
    negativos = 0
    sem_receita = 0
    duplicatas: set[tuple[str, dt.date]] = set()
    try:
        if "BASE" not in wb.sheetnames:
            raise ValueError("Planilha deve conter a aba 'BASE'. ROB anterior preservada.")
        linhas = wb["BASE"].iter_rows(values_only=True)
        cabecalho = next(linhas, None)
        if tuple(str(x).strip() if x is not None else "" for x in (cabecalho or ())) != CABECALHO:
            raise ValueError(f"Colunas incorretas. Esperado: {CABECALHO}; recebido: {cabecalho}")
        with psycopg.connect(conexao, autocommit=False) as con:
            con.execute("INSERT INTO public.rob_lotes(id,nome_arquivo) VALUES(%s,%s)",
                        (lote_id, nome_arquivo or caminho.name))
            con.commit()
            lote_sql = "COPY public.rob_receitas (lote_id,codigo_loja,loja,mes_vigencia,receita_bruta,linha_excel) FROM STDIN"
            buffer = []
            for n, valores in enumerate(linhas, start=2):
                if not any(x is not None and str(x).strip() for x in valores):
                    continue
                codigo, loja, mes, receita = converter_linha(tuple(valores), n)
                chave = (codigo, mes)
                if chave in duplicatas:
                    raise ValueError(f"Duplicidade de ROB para a loja {codigo} em {mes:%m/%Y} (linha {n}). A base atual foi preservada.")
                duplicatas.add(chave)
                if receita < 0:
                    negativos += 1
                if receita == 0:
                    sem_receita += 1
                buffer.append((lote_id, codigo, loja, mes, receita, n))
                if len(buffer) >= tamanho_lote:
                    with con.cursor() as cur, cur.copy(lote_sql) as copy:
                        for registro in buffer:
                            copy.write_row(registro)
                    con.commit()
                    criadas += len(buffer)
                    buffer.clear()
                    if progresso:
                        progresso(criadas)
            if buffer:
                with con.cursor() as cur, cur.copy(lote_sql) as copy:
                    for registro in buffer:
                        copy.write_row(registro)
                con.commit()
                criadas += len(buffer)
                if progresso:
                    progresso(criadas)
            if not criadas:
                raise ValueError("A planilha ROB está vazia. A base anterior foi preservada.")
            con.execute("SELECT public.rob_ativar_lote(%s)", (lote_id,))
            con.commit()
        return {"linhas": criadas, "lote_id": str(lote_id), "arquivo": nome_arquivo or caminho.name,
                "negativas": negativos, "zeradas": sem_receita}
    except Exception:
        # Limpa somente o lote ainda não ativado; ROB ativa e descontos não são tocados.
        try:
            with psycopg.connect(conexao) as con:
                con.execute("DELETE FROM public.rob_lotes WHERE id=%s AND status='carregando'", (lote_id,))
        except Exception:
            pass
        raise
    finally:
        wb.close()


def importar_upload_rob(upload: BinaryIO, conexao: str, progresso=None) -> dict:
    caminho = salvar_upload_xlsx_temporario(upload)
    try:
        return importar_rob_excel(caminho, conexao, getattr(upload, "name", "rob.xlsx"), progresso)
    finally:
        if os.path.exists(caminho):
            os.unlink(caminho)
