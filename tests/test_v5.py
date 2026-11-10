"""Regressões do ranking compacto e do novo gráfico mensal."""
from __future__ import annotations

import ast
from pathlib import Path

from ranking_compacto import preparar_ranking_compacto

BASE = Path(__file__).resolve().parents[1]


def test_ranking_mostra_so_loja_e_percentual_sem_opcoes():
    linha = {
        'rank': 1, 'loja': '023-PEDRA FG', 'valor': 'R$ 24.995,36',
        'participacao': '8,70%', 'rob': 'R$ 10.043.334,86',
        'percent_rob': '0,249%', 'media': '+714%',
    }
    footer = {**linha, 'loja': 'TOTAL TOP 10', 'percent_rob': '0,089%'}
    cols, rows, total, nums, fortes = preparar_ranking_compacto([linha], footer)
    assert cols == [('loja', 'Loja'), ('percent_rob', '% Desc / Receita')]
    assert rows == [('023-PEDRA FG', '0,249%')]
    assert total == ('TOTAL TOP 10', '0,089%')
    assert nums == (1,)
    assert fortes == (0, 1)


def test_ranking_opcionais_aparecem_somente_quando_solicitadas():
    linha = {'rank': 1, 'loja': '023-PEDRA FG', 'percent_rob': '0,249%',
             'valor': 'R$ 24.995,36', 'media': '+714%'}
    cols, rows, total, _, _ = preparar_ranking_compacto(
        [linha], linha, ['Valor rebaixado', 'vs. média rede', 'coluna desconhecida']
    )
    assert [ch for ch, _ in cols] == ['loja', 'percent_rob', 'valor', 'media']
    assert rows[0] == ('023-PEDRA FG', '0,249%', 'R$ 24.995,36', '+714%')
    assert len(rows[0]) == len(total) == len(cols)


def test_painel_historico_ignora_mes_mas_respeita_loja_ano_e_origem():
    app = (BASE / 'app.py').read_text(encoding='utf-8')
    ast.parse(app)
    assert "escopo['ano'], 'Todos', escopo['lojas'], escopo['origem']" in app
    assert "DATE_TRUNC('month', dta_movimento)::date AS mes" in app
    assert 'GROUP BY 1 ORDER BY 1' in app
    assert "len(escopo['lojas']) == 1" in app
    assert "with st.popover('Exibir mais colunas'" in app
    assert "preparar_ranking_compacto(" in app


def test_tema_escuro_corrige_fundo_e_texto_dos_campos():
    css = (BASE / 'aquila_visual.py').read_text(encoding='utf-8')
    ast.parse(css)
    assert '"input_bg": "#182E3C"' in css
    assert '"input_text": "#F4FBFF"' in css
    assert 'data-testid="stSegmentedControl"' in css
    assert 'data-baseweb="select"' in css
    assert '-webkit-text-fill-color:var(--aq-input-text)' in css
