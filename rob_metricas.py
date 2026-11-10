"""Cálculo financeiro sem misturar valores de desconto e receita em granularidades diferentes."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal


def d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def pct(valor, receita) -> Decimal | None:
    receita = d(receita)
    return d(valor) * 100 / receita if receita > 0 else None


def calc_linhas(linhas: list[tuple], metas: list[tuple]) -> dict:
    """Linhas: (codigo, mes date, nome, desconto, receita opcional).

    ROB entra uma vez por loja/mês (já agregados na SQL). Metas são percentuais,
    e.g. 0.04 significa 0,04%, não 4%.
    """
    historico = sorted((mes, d(valor)) for mes, valor in metas)
    lojas = defaultdict(lambda: {"desconto": Decimal(0), "desconto_coberto": Decimal(0),
                               "receita": Decimal(0), "teto": Decimal(0), "faltantes": 0,
                               "meses": 0, "nome": "", "oportunidade": Decimal(0)})
    meses = defaultdict(lambda: {"desconto": Decimal(0), "desconto_coberto": Decimal(0),
                               "receita": Decimal(0), "teto": Decimal(0), "faltantes": 0,
                               "meses": 0, "oportunidade": Decimal(0)})
    faltantes = []
    for codigo, mes, nome, desconto_raw, receita_raw in linhas:
        desconto = d(desconto_raw)
        vigentes = [valor for data, valor in historico if data <= mes]
        meta = vigentes[-1] if vigentes else Decimal('0.04')
        unidade = lojas[codigo or (nome or 'SEM-CODIGO')]
        mensal = meses[mes]
        unidade["nome"] = min(unidade["nome"], str(nome)) if unidade["nome"] else str(nome)
        unidade["desconto"] += desconto
        mensal["desconto"] += desconto
        unidade["meses"] += 1
        mensal["meses"] += 1
        if receita_raw is None or d(receita_raw) <= 0:
            unidade["faltantes"] += 1
            mensal["faltantes"] += 1
            faltantes.append((codigo, mes, "sem correspondência" if receita_raw is None else "ROB não positiva"))
            continue
        receita = d(receita_raw)
        teto = receita * meta / Decimal(100)
        oportunidade = max(Decimal(0), desconto - teto)
        for obj in (unidade, mensal):
            obj["receita"] += receita
            obj["desconto_coberto"] += desconto
            obj["teto"] += teto
            obj["oportunidade"] += oportunidade
    def finalizar(grupo):
        desconto = grupo['desconto']
        receita = grupo['receita']
        completo = grupo['faltantes'] == 0 and receita > 0
        return {**grupo,
                'cobertura_completa': completo,
                'percentual': pct(desconto, receita) if completo else None,
                'meta_pct_ponderada': pct(grupo['teto'], receita) if completo else None,
                'excesso': grupo['oportunidade'] if completo else None}
    lojas = {chave: finalizar(valor) for chave, valor in lojas.items()}
    meses = {chave: finalizar(valor) for chave, valor in meses.items()}
    soma = {campo: sum((v[campo] for v in lojas.values()), Decimal(0))
            for campo in ('desconto', 'desconto_coberto', 'receita', 'teto', 'oportunidade')}
    soma['faltantes'] = sum(v['faltantes'] for v in lojas.values())
    soma['meses'] = sum(v['meses'] for v in lojas.values())
    soma = finalizar(soma)
    return {'total': soma, 'lojas': lojas, 'meses': meses, 'faltantes': faltantes}
