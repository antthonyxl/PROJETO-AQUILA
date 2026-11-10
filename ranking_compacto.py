"""Configuração segura das colunas exibidas no ranking da Visão Geral."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

PADRAO = (("rank", "#"), ("loja", "Loja"), ("valor", "Valor rebaixado (R$)"), ("percent_rob", "% Desc / Receita"))
EXTRAS = {
    "% do total": ("participacao", "% do total"),
    "Receita bruta": ("rob", "Receita bruta"),
    "vs. média rede": ("media", "vs. média rede"),
}


def preparar_ranking_compacto(
    linhas: Sequence[Mapping[str, object]],
    total: Mapping[str, object],
    opcionais: Sequence[str] = (),
) -> tuple[list[tuple[str, str]], list[tuple], tuple, tuple[int, ...], tuple[int, ...]]:
    """Exibe posição, loja, soma do desconto e % Desc / Receita como colunas fixas.

    Cada coluna extra precisa ser expressamente selecionada no popover. O rodapé
    segue as mesmas colunas, sem utilizar dados de outras linhas ou consultas.
    """
    colunas = list(PADRAO)
    colunas.extend(EXTRAS[nome] for nome in opcionais if nome in EXTRAS)
    chaves = [chave for chave, _ in colunas]
    registros = [tuple(linha.get(chave, "—") for chave in chaves) for linha in linhas]
    rodape = tuple(total.get(chave, "—") for chave in chaves) if linhas else ()
    numeros = tuple(i for i, chave in enumerate(chaves) if chave not in {"loja"})
    fortes = tuple(i for i, chave in enumerate(chaves) if chave in {"loja", "percent_rob", "valor"})
    return colunas, registros, rodape, numeros, fortes
