"""Verificações de regressão estática e helpers HTML sem conexão de banco."""
import ast
import importlib.util
from pathlib import Path
import sys
import types

BASE = Path(__file__).resolve().parents[1]


def test_estrutura_codigo_v3():
    for nome in ("app.py", "aquila_visual.py", "ingestao.py"):
        ast.parse((BASE / nome).read_text(encoding="utf-8"))


def test_navegacao_sao_barras_sem_radio():
    app = (BASE / "app.py").read_text(encoding="utf-8")
    assert "st.radio(" not in app
    assert 'type="primary" if ativo else "secondary"' in app
    assert 'width="stretch"' in app  # Streamlit atual: barras de largura total
    assert 'st.toggle("Modo escuro"' in app


def test_plots_e_cards_possuem_tema_duplo():
    visual = (BASE / "aquila_visual.py").read_text(encoding="utf-8")
    assert '"light"' in visual and '"dark"' in visual
    assert 'data-testid="stSidebar"' in visual
    assert "aq-table" in visual
    assert "--aq-surface" in visual


def test_renderizacao_tabela_escapa_textos():
    # Dublê leve do Streamlit: valida a segurança das tabelas sem instalar o framework.
    out = []
    fake = types.SimpleNamespace(markdown=lambda valor, **kwargs: out.append(valor))
    antigo = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake
    try:
        spec = importlib.util.spec_from_file_location("_aquila_visual_test", BASE / "aquila_visual.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.tabela([("a", "Nome"), ("b", "Valor")], [("<script>alert(1)</script>", "100")])
        assert "<script>" not in out[-1]
        assert "&lt;script&gt;" in out[-1]
        out.clear()
        modulo.aplicar_tema(True)
        assert "#0B1720" in out[-1]
        out.clear()
        modulo.aplicar_tema(False)
        assert "#F2F5F6" in out[-1]
    finally:
        if antigo is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = antigo


def test_regra_de_substituicao_mantida():
    sql = (BASE / "sql/001_schema.sql").read_text(encoding="utf-8")
    assert "DELETE FROM public.pdv_lotes WHERE id <> p_lote" in sql
    assert "pdv_ativar_lote" in (BASE / "ingestao.py").read_text(encoding="utf-8")
