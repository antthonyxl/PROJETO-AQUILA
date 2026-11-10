from pathlib import Path
import ast

BASE = Path(__file__).resolve().parents[1]


def test_codigo_sintaticamente_valido():
    for nome in ("app.py", "ingestao.py"):
        ast.parse((BASE / nome).read_text(encoding="utf-8"))


def test_consulta_csc_nao_possui_curto_circuito_ilike_literal():
    codigo = (BASE / "app.py").read_text(encoding="utf-8")
    assert "ILIKE '%CSC%'" not in codigo
    assert "POSITION('CSC' IN UPPER(COALESCE(fiscal_cx" in codigo


def test_arquivos_sensiveis_nao_embalados():
    assert not (BASE / ".streamlit" / "secrets.toml").exists()
    assert ".streamlit/secrets.toml" in (BASE / ".gitignore").read_text(encoding="utf-8")


def test_mantem_ingestao_substitutiva():
    codigo = (BASE / "ingestao.py").read_text(encoding="utf-8")
    assert "pdv_ativar_lote" in codigo
    sql = (BASE / "sql" / "001_schema.sql").read_text(encoding="utf-8")
    assert "DELETE FROM public.pdv_lotes WHERE id <> p_lote" in sql
