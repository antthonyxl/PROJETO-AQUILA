from pathlib import Path
import ast
import sys
from decimal import Decimal

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ranking_compacto import preparar_ranking_compacto


def test_ranking_completo_69_lojas_e_colunas_fixas():
    linhas = [dict(rank=i, loja=f"{i:03}-LOJA", valor=f"R$ {i*10},00", percent_rob="0,04%") for i in range(1, 70)]
    total = dict(rank="", loja="TOTAL LOJAS", valor="R$ 24.150,00", percent_rob="0,04%")
    cols, rows, foot, nums, fortes = preparar_ranking_compacto(linhas, total)
    assert [key for key, _ in cols] == ['rank', 'loja', 'valor', 'percent_rob']
    assert len(rows) == 69
    assert rows[0][1] == '001-LOJA' and rows[-1][1] == '069-LOJA'
    assert foot[1] == 'TOTAL LOJAS' and foot[2] == 'R$ 24.150,00'
    assert 2 in nums and 3 in nums


def test_opcionais_nao_duplicam_valor():
    linha = {'rank': 1, 'loja': '023-LOJA', 'valor': 'R$ 99,00', 'percent_rob': '0,05%', 'rob': 'R$ 100.000,00'}
    cols, rows, total, *_ = preparar_ranking_compacto([linha], linha, ['Receita bruta', 'Valor rebaixado', 'Posição (#)'])
    assert [key for key, _ in cols] == ['rank','loja','valor','percent_rob','rob']
    assert len(rows[0]) == len(cols)


def test_app_nao_corta_ranking_e_preserva_sql():
    app = (ROOT/'app.py').read_text(encoding='utf8')
    ast.parse(app)
    block = app.split('def visao_geral(',1)[1].split('def evolucao_mensal(',1)[0]
    assert 'lojas_ranking = ranking_ordenado' in block
    assert 'top = ranking_ordenado[:10]' not in block
    assert 'for i, (loja, valor, contagem) in enumerate(lojas_ranking' in block
    assert "'loja': 'TOTAL LOJAS'" in block
    assert 'SUM(vlr_desconto)' in block
    assert "escopo['ano'], 'Todos', escopo['lojas'], escopo['origem']" in block


def test_sidebar_css_isolado_e_scroll():
    css = (ROOT/'aquila_visual.py').read_text(encoding='utf8')
    ast.parse(css)
    assert '.st-key-aq_ranking_panel .aq-table-wrap {' in css
    assert 'height:520px;' in css
    assert 'overflow-y:auto;' in css
    assert 'position:sticky;' in css
    assert 'st-key-nav_geral' in css and 'st-key-nav_mensal' in css and 'st-key-nav_administracao' in css
    assert '[data-testid="stSidebar"] :is(.st-key-nav_geral' in css
    assert '#EFF7FF' in css and '#123F58' in css


def test_cores_da_paleta_inalteradas():
    def extract_theme(path):
        module=ast.parse(path.read_text(encoding='utf8'))
        for node in module.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id=='TEMAS' for target in node.targets):
                return ast.literal_eval(node.value)
        raise AssertionError('TEMAS missing')
    original = Path('/mnt/data/AQUILA_V9_MOTIVOS/aquila_visual.py')
    if original.exists():
        assert extract_theme(ROOT/'aquila_visual.py') == extract_theme(original)
