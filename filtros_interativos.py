"""Filtros cruzados de tabelas do dashboard ÁQUILA.

Somente acrescenta condições parametrizadas; não contém Streamlit e é
independente do cache/da sessão. Nenhum valor do usuário entra no SQL literal.
"""
from __future__ import annotations

from collections.abc import Mapping

ORIGEM_SQL = "POSITION('CSC' IN UPPER(COALESCE(fiscal_cx, ''))) > 0"


def filtros_vazios() -> dict:
    return {"motivo": None, "origem": None, "produto_codigo": None,
            "produto_nome": None, "produto_ativo": False}


def alternar_filtro(atuais: Mapping, categoria: str, valor, nome: str | None = None) -> dict:
    """Alterna seleção de uma categoria; preserva as demais."""
    novos = dict(filtros_vazios())
    novos.update(atuais or {})
    if categoria not in {"motivo", "origem", "produto"}:
        raise ValueError(f"Categoria inválida: {categoria}")
    if categoria == "produto":
        ativo = bool(novos["produto_ativo"])
        igual = ativo and novos["produto_codigo"] == valor and novos["produto_nome"] == nome
        novos["produto_ativo"] = not igual
        novos["produto_codigo"] = None if igual else valor
        novos["produto_nome"] = None if igual else nome
    else:
        novos[categoria] = None if novos[categoria] == valor else valor
    return novos


def condicoes_cruzadas(where: str, params: tuple, filtros: Mapping) -> tuple[str, tuple]:
    """Inclui motivo, origem e produto em qualquer SQL de descontos.

    O campo produto usa seu código quando disponível, não apenas a descrição.
    """
    f = dict(filtros_vazios())
    f.update(filtros or {})
    condicoes: list[str] = []
    valores = list(params)
    if f["motivo"] is not None:
        condicoes.append("COALESCE(NULLIF(TRIM(motivo),''),'Não informado') = %s")
        valores.append(f["motivo"])
    if f["origem"] == "CSC":
        condicoes.append(ORIGEM_SQL)
    elif f["origem"] == "Loja":
        condicoes.append(f"NOT ({ORIGEM_SQL})")
    if f["produto_ativo"]:
        if f["produto_codigo"] is not None:
            condicoes.append("cod_produto = %s")
            valores.append(f["produto_codigo"])
        else:
            condicoes.append("cod_produto IS NULL")
            condicoes.append("COALESCE(NULLIF(TRIM(produto),''),'Não informado') = %s")
            valores.append(f["produto_nome"])
    if condicoes:
        where = f"{where} AND {' AND '.join(condicoes)}" if where else f"WHERE {' AND '.join(condicoes)}"
    return where, tuple(valores)
