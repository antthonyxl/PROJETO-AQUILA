"""ÁQUILA | Dashboard Descontos PDV — versão 10 (ranking completo e menu).

Dashboard executivo com temas claro/escuro. Acesso administrativo provisório.
Não liberar a gerentes, diretores ou distritais antes de implementar RBAC real.
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import hmac
import html
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import streamlit as st
from psycopg_pool import ConnectionPool

from aquila_visual import aplicar_tema, cabecalho, kpi, nota, paleta, secao, tabela, tabela_selecionavel, vazio
from aquila_runtime import configuracao_pool
from filtros_interativos import filtros_vazios, alternar_filtro, condicoes_cruzadas
from rob_metricas import calc_linhas, pct, d
from ranking_compacto import preparar_ranking_compacto
from decimal import Decimal
import re

st.set_page_config(page_title="Controle Descontos PDV", page_icon=":material/analytics:", layout="wide", initial_sidebar_state="expanded")

if "aq_dark" not in st.session_state:
    st.session_state.aq_dark = False
if "aq_pagina" not in st.session_state:
    st.session_state.aq_pagina = "geral"

TEMA = paleta(st.session_state.aq_dark)
AZUL = TEMA["blue"]
LARANJA = TEMA["orange"]
TEAL = TEMA["teal"]
TEXTO = TEMA["text"]
MUDO = TEMA["muted"]
GRID = TEMA["grid"]
FUNDO_GRAFICO = TEMA["surface"]
PALETA = ["#1C839A", "#EB963E", "#608AD2", "#8E7BD8", "#43AD8A", "#E1BE54", "#BD73A6", "#5A9CA8"]

aplicar_tema(st.session_state.aq_dark)


def segredo(chave: str) -> str:
    try:
        return str(st.secrets.get(chave, ""))
    except Exception:
        return ""


DB_URL = segredo("SUPABASE_DB_URL")
ADMIN_USER = segredo("ADMIN_USER")
ADMIN_PASSWORD_HASH = segredo("ADMIN_PASSWORD_HASH")


@st.cache_resource
def pool_banco() -> ConnectionPool:
    """Reutiliza conexões entre consultas, com limite por processo."""
    return ConnectionPool(DB_URL, **configuracao_pool(),
                          check=ConnectionPool.check_connection)


@st.cache_data(ttl=300, max_entries=2048, show_spinner=False)
def query(sql: str, params: tuple = ()) -> list[tuple]:
    """Consultas ao PostgreSQL realizadas exclusivamente no servidor."""
    with pool_banco().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []


def verificar_senha(senha: str, armazenada: str) -> bool:
    try:
        salt, esperado = armazenada.split(":", 1)
        calculado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 600_000)
        return hmac.compare_digest(calculado.hex(), esperado)
    except (ValueError, TypeError):
        return False


def escape(valor: object) -> str:
    return html.escape(str(valor) if valor is not None else "", quote=True)


def numero_br(valor: object, casas: int = 0) -> str:
    texto = f"{float(valor or 0):,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def brl(valor: object, compacto: bool = False) -> str:
    val = float(valor or 0)
    if compacto and abs(val) >= 1_000_000:
        return f"R$ {numero_br(val / 1_000_000, 2)} mi"
    if compacto and abs(val) >= 1_000:
        return f"R$ {numero_br(val / 1_000, 1)} mil"
    return f"R$ {numero_br(val, 2)}"


def percentual(numerador: object, denominador: object) -> str:
    base = float(denominador or 0)
    return f"{numero_br(float(numerador or 0) / base * 100, 2)}%" if base else "—"


def titulo(texto: str, descricao: str, eyebrow: str = "PAINEL DE GESTÃO") -> None:
    cabecalho(texto, descricao, eyebrow)


def configurar_figura(fig: go.Figure, altura: int = 320) -> go.Figure:
    fig.update_layout(
        height=altura, margin=dict(l=10, r=15, t=36, b=35),
        paper_bgcolor=FUNDO_GRAFICO, plot_bgcolor=FUNDO_GRAFICO,
        font=dict(family="Segoe UI, Arial", size=12, color=TEXTO),
        hoverlabel=dict(bgcolor=TEMA["surface_alt"], font=dict(color=TEXTO), font_size=12),
        showlegend=False,
    )
    fig.update_xaxes(showline=False, gridcolor=GRID, zeroline=False, tickfont=dict(color=MUDO))
    fig.update_yaxes(showline=False, gridcolor=GRID, zeroline=False, tickfont=dict(color=MUDO))
    return fig


def fig_treemap(linhas: list[tuple]) -> go.Figure:
    nomes = [str(x[0] or "Não informado") for x in linhas]
    valores = [float(x[1] or 0) for x in linhas]
    if not nomes or any(v <= 0 for v in valores):
        fig = go.Figure(go.Bar(
            y=nomes[::-1], x=valores[::-1], orientation="h", marker_color=TEAL,
            text=[brl(v, True) for v in valores[::-1]], textposition="outside",
        ))
        fig.update_layout(margin=dict(l=10, r=100, t=20, b=25))
        return configurar_figura(fig, 350)
    fig = go.Figure(go.Treemap(
        labels=nomes, parents=[""] * len(nomes), values=valores,
        marker=dict(colors=[PALETA[i % len(PALETA)] for i in range(len(nomes))],
                    line=dict(width=3, color=FUNDO_GRAFICO)),
        textinfo="label+percent root", textfont=dict(color="white", size=14),
        hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>",
        tiling=dict(pad=4),
    ))
    return configurar_figura(fig, 350)


def fig_donut(linhas: list[tuple]) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=[str(x[0]) for x in linhas],
        values=[abs(float(x[1] or 0)) for x in linhas],
        hole=.67, sort=False,
        marker=dict(colors=[TEAL, LARANJA], line=dict(color=FUNDO_GRAFICO, width=3)),
        textinfo="label+percent", textposition="outside",
        textfont=dict(color=TEXTO, size=12),
        hovertemplate="%{label}<br>R$ %{value:,.2f}<extra></extra>",
    ))
    fig = configurar_figura(fig, 260)
    fig.update_layout(margin=dict(l=14, r=14, t=20, b=10))
    return fig


def fig_ranking(linhas: list[tuple]) -> go.Figure:
    itens = list(linhas[:10])[::-1]
    fig = go.Figure(go.Bar(
        y=[str(x[0]) for x in itens],
        x=[float(x[1] or 0) for x in itens], orientation="h",
        marker=dict(color=TEAL, cornerradius=4),
        text=[brl(x[1], True) for x in itens], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(margin=dict(l=18, r=110, t=25, b=25))
    return configurar_figura(fig, 360)


def fig_meses(linhas: list[tuple]) -> go.Figure:
    rotulos = [x[0].strftime("%m/%Y") for x in linhas]
    valores = [float(x[1] or 0) for x in linhas]
    fig = go.Figure(go.Bar(
        x=rotulos, y=valores,
        marker=dict(color=LARANJA, cornerradius=4),
        text=[brl(v, True) for v in valores], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Desconto: R$ %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(margin=dict(l=15, r=12, t=50, b=35))
    fig.update_yaxes(tickprefix="R$ ")
    return configurar_figura(fig, 390)


def fig_historico_rebaixas(meses: list[tuple]) -> go.Figure:
    """Valor de desconto por mês; recebe somente períodos realmente carregados."""
    rotulos = [mes.strftime("%m/%Y") for mes, _ in meses]
    valores = [float(valor or 0) for _, valor in meses]
    fig = go.Figure(go.Bar(
        x=rotulos, y=valores, name="Rebaixas",
        marker=dict(color=TEAL, line=dict(color=FUNDO_GRAFICO, width=1)),
        text=[brl(valor, True) for valor in valores], textposition="outside",
        customdata=[brl(valor) for valor in valores],
        hovertemplate="<b>%{x}</b><br>Rebaixas: %{customdata}<extra></extra>",
        cliponaxis=False,
    ))
    fig = configurar_figura(fig, 560)
    fig.update_layout(margin=dict(l=74, r=18, t=48, b=70), bargap=0.32)
    fig.update_yaxes(tickprefix="R$ ", tickformat="~s", rangemode="tozero", automargin=True)
    fig.update_xaxes(type="category", tickangle=-35)
    return fig


def carregar_hierarquia_lojas() -> dict[str, dict[str, str]]:
    """Lê o vínculo código da loja → estado, distrito e região do JSON externo."""
    caminho = Path(__file__).resolve().parent / "lojas_hierarquia.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st.warning("Arquivo lojas_hierarquia.json não encontrado. Os filtros geográficos ficarão indisponíveis.")
        return {}
    except (OSError, json.JSONDecodeError) as erro:
        st.warning(f"Não foi possível ler lojas_hierarquia.json: {erro}")
        return {}

    registros = dados.get("lojas", []) if isinstance(dados, dict) else []
    if not isinstance(registros, list):
        st.warning("O campo 'lojas' do arquivo lojas_hierarquia.json precisa ser uma lista.")
        return {}

    hierarquia: dict[str, dict[str, str]] = {}
    for registro in registros:
        if not isinstance(registro, dict):
            continue
        codigo = str(registro.get("codigo", "")).strip()
        if not re.fullmatch(r"\d{1,3}", codigo):
            continue
        codigo = codigo.zfill(3)
        hierarquia[codigo] = {
            campo: str(registro.get(campo, "") or "").strip()
            for campo in ("estado", "distrito", "regiao")
        }
    return hierarquia


def condicoes(ano, meses, lojas, origem, filtro_hierarquia_ativo=False) -> tuple[str, tuple]:
    partes: list[str] = []
    params: list = []

    # Lista vazia representa Todos os meses. Uma ou mais seleções geram IN.
    meses_selecionados = (
        [] if meses in (None, "Todos", ()) else
        [int(meses)] if isinstance(meses, (int, str)) else
        [int(mes) for mes in meses]
    )

    if ano != "Todos":
        ano_num = int(ano)
        partes.extend(["dta_movimento >= %s", "dta_movimento < %s"])
        params.extend([dt.date(ano_num, 1, 1), dt.date(ano_num + 1, 1, 1)])

    if meses_selecionados:
        partes.append("EXTRACT(MONTH FROM dta_movimento)::int = ANY(%s)")
        params.append(meses_selecionados)
    if lojas:
        partes.append("empresa = ANY(%s)")
        params.append(list(lojas))
    elif filtro_hierarquia_ativo:
        # Um filtro geográfico sem lojas correspondentes deve retornar zero linhas,
        # nunca remover o filtro e exibir a rede inteira.
        partes.append("FALSE")
    verificacao = "POSITION('CSC' IN UPPER(COALESCE(fiscal_cx, ''))) > 0"
    if origem == "CSC":
        partes.append(verificacao)
    elif origem == "Loja":
        partes.append(f"NOT ({verificacao})")
    return ("WHERE " + " AND ".join(partes) if partes else "", tuple(params))


def adicionar_condicao(where: str, filtro: str) -> str:
    return f"{where} AND {filtro}" if where else f"WHERE {filtro}"


def filtros_dashboard(chave: str) -> tuple[str, tuple, dict]:
    anos = [int(x[0]) for x in query("""
        SELECT DISTINCT EXTRACT(YEAR FROM dta_movimento)::int
        FROM public.pdv_descontos_atuais WHERE dta_movimento IS NOT NULL ORDER BY 1 DESC
    """)]
    lojas = [str(x[0]) for x in query("""
        SELECT DISTINCT empresa FROM public.pdv_descontos_atuais
        WHERE empresa IS NOT NULL ORDER BY 1
    """)]
    hierarquia = carregar_hierarquia_lojas()
    metadados_disponiveis = [
        hierarquia[codigo_loja(loja)]
        for loja in lojas
        if codigo_loja(loja) in hierarquia
    ]

    meses = {"Todos": None, "Janeiro": 1, "Fevereiro": 2, "Março": 3,
             "Abril": 4, "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8,
             "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12}

    # Os filtros geográficos ficam fora de st.form para que o Streamlit
    # atualize as opções dos outros campos imediatamente após cada seleção.
    chave_estado = f"{chave}_filtros_confirmados"
    chaves_geo = {
        "estados": f"{chave}_estados",
        "distritos": f"{chave}_distritos",
        "regioes": f"{chave}_regioes",
    }
    for nome, widget_key in chaves_geo.items():
        st.session_state.setdefault(widget_key, [])

    def registros_compativeis(ignorar: str) -> list[dict[str, str]]:
        selecionados = {
            nome: set(st.session_state.get(widget_key, []))
            for nome, widget_key in chaves_geo.items()
        }
        resultado = []
        for item in metadados_disponiveis:
            if any(
                selecionados[nome] and item[campo] not in selecionados[nome]
                for nome, campo in (
                    ("estados", "estado"),
                    ("distritos", "distrito"),
                    ("regioes", "regiao"),
                )
                if nome != ignorar
            ):
                continue
            resultado.append(item)
        return resultado

    # Cada lista apresenta apenas valores compatíveis com as seleções
    # feitas nos outros dois filtros geográficos.
    opcoes_geo = {
        "estados": sorted({
            item["estado"] for item in registros_compativeis("estados")
            if item["estado"]
        }),
        "distritos": sorted({
            item["distrito"] for item in registros_compativeis("distritos")
            if item["distrito"]
        }),
        "regioes": sorted({
            item["regiao"] for item in registros_compativeis("regioes")
            if item["regiao"]
        }),
    }

    # Remove automaticamente seleções que deixaram de ser compatíveis.
    # Isso evita combinações impossíveis e listas sem correspondência.
    for nome, widget_key in chaves_geo.items():
        valores_validos = set(opcoes_geo[nome])
        st.session_state[widget_key] = [
            valor for valor in st.session_state[widget_key]
            if valor in valores_validos
        ]

    with st.container(border=True):
        st.markdown('<div class="aq-panel-title">Filtros de consulta</div>', unsafe_allow_html=True)
        a, b, c, d = st.columns([1, 1.2, 2, 1.2])
        with a:
            ano = st.selectbox("Ano", ["Todos", *anos], index=1 if anos else 0, key=f"{chave}_ano")
        with b:
            meses_sel = st.multiselect(
                "Mês", list(meses.keys())[1:], placeholder="Todos os meses",
                key=f"{chave}_meses",
            )
        with c:
            lojas_sel = st.multiselect("Lojas", lojas, placeholder="Todas as lojas", key=f"{chave}_lojas")
        with d:
            origem = st.selectbox("Origem", ["Todos", "CSC", "Loja"], key=f"{chave}_origem")

        e, f, g = st.columns([1, 1.2, 1.2])
        with e:
            estados_sel = st.multiselect(
                "Estado", opcoes_geo["estados"], placeholder="Todos os estados",
                key=chaves_geo["estados"], disabled=not opcoes_geo["estados"],
                help="Selecione um ou mais estados. Distrito e Região serão ajustados automaticamente."
            )
        with f:
            distritos_sel = st.multiselect(
                "Distrito", opcoes_geo["distritos"], placeholder="Todos os distritos",
                key=chaves_geo["distritos"], disabled=not opcoes_geo["distritos"],
                help="Exibe somente distritos compatíveis com Estado e Região selecionados."
            )
        with g:
            regioes_sel = st.multiselect(
                "Região", opcoes_geo["regioes"], placeholder="Todas as regiões",
                key=chaves_geo["regioes"], disabled=not opcoes_geo["regioes"],
                help="Exibe somente regiões compatíveis com Estado e Distrito selecionados."
            )

        if not metadados_disponiveis:
            st.caption("Para habilitar Estado, Distrito e Região, cadastre em lojas_hierarquia.json os códigos que aparecem no início do campo empresa da base.")
        enviado = st.button(
            "Aplicar filtros", type="primary", icon=":material/filter_alt:",
            key=f"{chave}_aplicar_filtros"
        )

    # As alterações nos campos atualizam as listas, mas só afetam os dados
    # do dashboard quando o usuário clica em Aplicar filtros.
    if enviado or chave_estado not in st.session_state:
        st.session_state[chave_estado] = {
            "ano": ano,
            "mes": tuple(meses[nome] for nome in meses_sel),
            "lojas": tuple(lojas_sel),
            "origem": origem,
            "estados": tuple(estados_sel),
            "distritos": tuple(distritos_sel),
            "regioes": tuple(regioes_sel),
        }

    escopo = dict(st.session_state[chave_estado])
    mes_salvo = escopo.get("mes", ())
    if mes_salvo in (None, "Todos"):
        escopo["mes"] = ()
    elif isinstance(mes_salvo, int):
        escopo["mes"] = (mes_salvo,)
    elif isinstance(mes_salvo, str):
        escopo["mes"] = (int(mes_salvo),) if mes_salvo.isdigit() else ()
    else:
        escopo["mes"] = tuple(mes_salvo)
    escopo.setdefault("estados", ())
    escopo.setdefault("distritos", ())
    escopo.setdefault("regioes", ())

    filtro_hierarquia_ativo = bool(
        escopo["estados"] or escopo["distritos"] or escopo["regioes"]
    )
    if filtro_hierarquia_ativo:
        lojas_aplicadas = []
        lojas_escolhidas = set(escopo["lojas"])
        for loja in lojas:
            metadados = hierarquia.get(codigo_loja(loja))
            if not metadados:
                continue
            if escopo["estados"] and metadados["estado"] not in escopo["estados"]:
                continue
            if escopo["distritos"] and metadados["distrito"] not in escopo["distritos"]:
                continue
            if escopo["regioes"] and metadados["regiao"] not in escopo["regioes"]:
                continue
            if lojas_escolhidas and loja not in lojas_escolhidas:
                continue
            lojas_aplicadas.append(loja)
        lojas_aplicadas = tuple(lojas_aplicadas)
    else:
        lojas_aplicadas = tuple(escopo["lojas"])

    escopo["lojas_aplicadas"] = lojas_aplicadas
    escopo["filtro_hierarquia_ativo"] = filtro_hierarquia_ativo
    if filtro_hierarquia_ativo and not lojas_aplicadas:
        st.warning("Nenhuma loja corresponde à combinação de Estado, Distrito, Região e Lojas. Confira o cadastro no JSON.")
    where, params = condicoes(
        escopo["ano"], escopo["mes"], escopo["lojas_aplicadas"],
        escopo["origem"], escopo["filtro_hierarquia_ativo"]
    )
    return where, params, escopo


def filtros_cruzados_ativos() -> dict:
    """Seleções isoladas por sessão: não são guardadas no cache global."""
    if "aq_filtros_cruzados" not in st.session_state:
        st.session_state.aq_filtros_cruzados = filtros_vazios()
    return st.session_state.aq_filtros_cruzados


def definir_filtro_da_tabela(categoria: str, valor, nome: str | None = None) -> None:
    st.session_state.aq_filtros_cruzados = alternar_filtro(
        filtros_cruzados_ativos(), categoria, valor, nome
    )
    # Remonta o seletor e evita que a última linha clicada seja reaplicada
    # em cada nova execução do Streamlit.
    st.session_state[f"aq_tabela_versao_{categoria}"] = (
        st.session_state.get(f"aq_tabela_versao_{categoria}", 0) + 1
    )


def limpar_filtros_dashboard() -> None:
    """Limpa filtros do formulário das duas páginas e seleções cruzadas."""
    st.session_state.aq_filtros_cruzados = filtros_vazios()
    st.session_state.ranking_criterio = 'Valor rebaixado (R$)'
    for pagina in ("geral", "mensal"):
        st.session_state[f"{pagina}_ano"] = "Todos"
        st.session_state[f"{pagina}_meses"] = []
        st.session_state[f"{pagina}_lojas"] = []
        st.session_state[f"{pagina}_origem"] = "Todos"
        st.session_state[f"{pagina}_estados"] = []
        st.session_state[f"{pagina}_distritos"] = []
        st.session_state[f"{pagina}_regioes"] = []
        st.session_state[f"{pagina}_filtros_confirmados"] = {
            "ano": "Todos", "mes": (), "lojas": (), "origem": "Todos",
            "estados": (), "distritos": (), "regioes": ()
        }
    for categoria in ("motivo", "origem", "produto"):
        st.session_state[f"aq_tabela_versao_{categoria}"] = (
            st.session_state.get(f"aq_tabela_versao_{categoria}", 0) + 1
        )


def ferramentas_de_filtro() -> None:
    """Botão global no início de ambas as páginas, com seleções visíveis."""
    botoes, aviso = st.columns([1.35, 4], gap="small", vertical_alignment="center")
    with botoes:
        st.button("Redefinir todos os filtros", icon=":material/filter_alt_off:",
                  key=f"reset_{st.session_state.aq_pagina}",
                  width="stretch", on_click=limpar_filtros_dashboard)
    cruzados = filtros_cruzados_ativos()
    selecionados = []
    if cruzados["motivo"] is not None:
        selecionados.append(("motivo", f"Motivo: {cruzados['motivo']}"))
    if cruzados["origem"] is not None:
        selecionados.append(("origem", f"Origem: {cruzados['origem']}"))
    if cruzados["produto_ativo"]:
        selecionados.append(("produto", f"Produto: {cruzados['produto_nome']}"))
    with aviso:
        if not selecionados:
            st.caption("Selecione uma linha nos rankings de motivos, origem ou produtos para filtrar o painel.")
        else:
            st.caption("Filtros interativos ativos (clique para remover):")
    if selecionados:
        colunas = st.columns(len(selecionados), gap="small")
        for col, (categoria, texto) in zip(colunas, selecionados):
            with col:
                st.button(texto[:70] + ("…" if len(texto) > 70 else ""),
                          icon=":material/close:", key=f"remover_filtro_{categoria}",
                          on_click=remover_filtro, args=(categoria,), width="stretch")


def remover_filtro(categoria: str) -> None:
    atuais = filtros_cruzados_ativos()
    if categoria == "produto":
        definir_filtro_da_tabela("produto", atuais["produto_codigo"], atuais["produto_nome"])
    else:
        definir_filtro_da_tabela(categoria, atuais[categoria])


def tabela_com_acao(colunas: list[tuple[str, str]], linhas: list[tuple],
                    categoria: str, opcoes: list, altura: int = 480,
                    totalizador=None) -> None:
    """Tabela com visual executivo e checkbox funcional por categoria."""
    filtros = filtros_cruzados_ativos()

    def marcado(opcao) -> bool:
        if categoria == "produto":
            return bool(filtros["produto_ativo"] and
                        filtros["produto_codigo"] == opcao[0] and
                        filtros["produto_nome"] == opcao[1])
        return filtros[categoria] == opcao

    def ao_alternar(opcao, chave_checkbox: str) -> None:
        # Callback do checkbox executado ANTES da nova renderização. Não
        # mexe nas conexões, no cache nem nas regras de cálculo.
        selecionado = bool(st.session_state[chave_checkbox])
        if selecionado == marcado(opcao):
            return
        if categoria == "produto":
            definir_filtro_da_tabela(categoria, opcao[0], opcao[1])
        else:
            definir_filtro_da_tabela(categoria, opcao)

    versao = st.session_state.get(f"aq_tabela_versao_{categoria}", 0)
    tabela_selecionavel(
        colunas, linhas, key=f"aq_seletor_{categoria}_{versao}",
        opcoes=opcoes, ativo=marcado, ao_mudar=ao_alternar,
        totalizador=totalizador,
    )


def metas_historicas() -> list[tuple]:
    return query("SELECT mes_vigencia, percentual FROM public.pdv_metas ORDER BY mes_vigencia")


def meta_do_mes(mes: dt.date, historico: list[tuple]) -> float | None:
    disponiveis = [float(valor) for vigencia, valor in historico if vigencia <= mes]
    return disponiveis[-1] if disponiveis else None


def meta_atual() -> float:
    mes = dt.datetime.now(ZoneInfo("America/Recife")).date().replace(day=1)
    rows = query("""
        SELECT percentual FROM public.pdv_metas
        WHERE mes_vigencia <= %s ORDER BY mes_vigencia DESC LIMIT 1
    """, (mes,))
    return float(rows[0][0]) if rows else .04


def base_ativa() -> tuple | None:
    rows = query("""
        SELECT l.nome_arquivo, l.linhas, l.ativado_em
        FROM public.pdv_config c JOIN public.pdv_lotes l ON l.id=c.lote_ativo
        WHERE c.chave='descontos'
    """)
    return rows[0] if rows else None


def cabecalho_base(lote: tuple) -> None:
    nome, linhas, publicado = lote
    quando = publicado.strftime("%d/%m/%Y %H:%M") if publicado else "Data não informada"
    st.markdown(
        f'<div class="aq-footnote"><span class="aq-pill">Base publicada</span> &nbsp;'
        f'{escape(nome)} &nbsp;·&nbsp; {numero_br(linhas)} registros &nbsp;·&nbsp; {escape(quando)}</div>',
        unsafe_allow_html=True,
    )




def base_rob_ativa() -> tuple | None:
    linhas = query("""
        SELECT l.nome_arquivo, l.linhas, l.ativado_em
        FROM public.rob_config c
        JOIN public.rob_lotes l ON l.id = c.lote_ativo
        WHERE c.chave = 'rob'
    """)
    return linhas[0] if linhas else None


@st.cache_data(max_entries=512, show_spinner=False)
def calcular_conciliacao(resultado: list[tuple], metas: list[tuple]) -> dict:
    return calc_linhas(resultado, metas)


def dados_conciliados(where: str, params: tuple) -> dict:
    # Primeiro agregar descontos por CODIGO + MÊS; só então juntar com a ROB.
    # Evita multiplicar a receita pelo número de cupons de desconto.
    where_data = adicionar_condicao(where, 'dta_movimento IS NOT NULL')
    resultado = query(f"""
        WITH por_unidade_mes AS (
          SELECT SUBSTRING(BTRIM(empresa) FROM '^([0-9]{{3}})') AS codigo_loja,
                 DATE_TRUNC('month', dta_movimento)::date AS mes,
                 MIN(COALESCE(empresa,'Não informado')) AS loja,
                 COALESCE(SUM(vlr_desconto),0) AS desconto
          FROM public.pdv_descontos_atuais {where_data}
          GROUP BY 1,2
        )
        SELECT d.codigo_loja, d.mes, d.loja, d.desconto, r.receita_bruta
        FROM por_unidade_mes d
        LEFT JOIN public.rob_receitas_atuais r
          ON r.codigo_loja=d.codigo_loja AND r.mes_vigencia=d.mes
        ORDER BY d.mes, d.codigo_loja
    """, params)
    return calcular_conciliacao(resultado, metas_historicas())


def porcentagem_rob(valor: object, casas: int = 3) -> str:
    return f'{numero_br(valor, casas)}%' if valor is not None else '—'


def variacao_media(valor: object, media: object) -> str:
    if valor is None or media is None or d(media) <= 0:
        return '—'
    taxa = (d(valor) / d(media) - 1) * 100
    return f'{"+" if taxa > 0 else ""}{numero_br(taxa, 0)}%'


def fig_oportunidades_rob(ranking: list[tuple], detalhes: dict) -> go.Figure:
    # São percentuais reais, como 0.04 para meta de 0,04%.
    selecionadas = []
    for loja, desconto, _ in ranking[:10]:
        codigo = codigo_loja(loja)
        dado = detalhes['lojas'].get(codigo)
        if dado and dado['percentual'] is not None:
            selecionadas.append((loja, float(dado['percentual']), float(dado['meta_pct_ponderada'])))
    figura = go.Figure()
    figura.add_trace(go.Bar(
        x=[x[0] for x in selecionadas], y=[x[1] for x in selecionadas],
        name='Desconto / ROB', marker_color='#B5C8E8',
        text=[porcentagem_rob(x[1], casas=2) for x in selecionadas], textposition='outside'
    ))
    figura.add_trace(go.Scatter(
        x=[x[0] for x in selecionadas], y=[x[2] for x in selecionadas],
        name='Meta vigente ponderada', mode='lines+markers',
        line=dict(color=TEAL, dash='dash', width=3), marker=dict(size=7)
    ))
    figura = configurar_figura(figura, 390)
    figura.update_layout(showlegend=True, legend=dict(orientation='h', y=-.27),
                         margin=dict(l=54,r=10,t=45,b=110))
    figura.update_xaxes(tickangle=-35)
    figura.update_yaxes(ticksuffix='%', tickformat='.2f', rangemode='tozero', automargin=True)
    return figura


def fig_realizado_teto(mensal: dict) -> go.Figure:
    periodos = sorted(mensal)
    rotulos = [x.strftime('%m/%Y') for x in periodos]
    realizado = [float(mensal[x]['desconto']) for x in periodos]
    teto = [float(mensal[x]['teto']) if mensal[x]['cobertura_completa'] else None for x in periodos]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=rotulos, y=realizado, name='Realizado', marker_color=LARANJA,
                         text=[brl(x, True) for x in realizado], textposition='outside'))
    fig.add_trace(go.Bar(x=rotulos, y=teto, name='Teto pela meta', marker_color=TEAL,
                         text=[brl(x,True) if x is not None else 'Sem ROB' for x in teto],
                         textposition='outside'))
    fig = configurar_figura(fig, 400)
    fig.update_layout(showlegend=True, barmode='group', legend=dict(orientation='h',y=-.23),
                      margin=dict(l=15,r=10,t=50,b=80))
    fig.update_yaxes(tickprefix='R$ ')
    return fig


@st.cache_data(max_entries=512, show_spinner=False)
def exibir_grafico(tipo: str, escuro: bool, dados, detalhes=None) -> None:
    """Reproduz o gráfico serializado; tema e dados separam as entradas do cache."""
    funcoes = {
        'historico': fig_historico_rebaixas,
        'oportunidades': fig_oportunidades_rob,
        'canais': fig_donut,
        'realizado': fig_realizado_teto,
    }
    figura = funcoes[tipo](dados, detalhes) if detalhes is not None else funcoes[tipo](dados)
    st.plotly_chart(figura, theme=None, width='stretch', config={'displayModeBar': False})


def codigo_loja(valor: str) -> str:
    encontrado = re.match(r'^\s*(\d{3})', str(valor or ''))
    return encontrado.group(1) if encontrado else str(valor or '').strip()

def selecionar_ranking(criterio: str) -> None:
    """Atualiza a ordenação com botões compatíveis com os dois temas."""
    st.session_state.ranking_criterio = criterio


def visao_geral(lote: tuple) -> None:
    titulo("Visão Geral", "Descontos manuais no PDV - análise executiva e operacional por loja, fiscal e produto.", "GESTÃO EXECUTIVA / ÁQUILA")
    cabecalho_base(lote)
    ferramentas_de_filtro()
    onde_base, params_base, escopo = filtros_dashboard("geral")
    onde, params = condicoes_cruzadas(onde_base, params_base, filtros_cruzados_ativos())
    resumo = query(f"""
        SELECT COALESCE(SUM(vlr_desconto),0), COUNT(DISTINCT empresa), COUNT(*),
               COUNT(DISTINCT cod_produto),
               COALESCE(SUM(CASE WHEN POSITION('CSC' IN UPPER(COALESCE(fiscal_cx,''))) > 0
                   THEN vlr_desconto ELSE 0 END),0)
        FROM public.pdv_descontos_atuais {onde}
    """, params)[0]
    total, n_lojas, qtd_registros, n_produtos, valor_csc = resumo
    ranking = query(f"""
        SELECT MIN(COALESCE(empresa,'Não informado')), COALESCE(SUM(vlr_desconto),0), COUNT(*)
        FROM public.pdv_descontos_atuais {onde}
        GROUP BY COALESCE(SUBSTRING(BTRIM(empresa) FROM '^([0-9]{{3}})'), COALESCE(empresa,'Não informado'))
        ORDER BY 2 DESC
    """, params)
    # Cada linha da base representa uma ocorrência do motivo; não somamos QUANTIDADE.
    # Sem LIMIT: o total da tabela deve abranger todos os motivos do filtro.
    motivos = query(f"""
        SELECT COALESCE(NULLIF(TRIM(motivo),''),'Não informado') AS motivo,
               COALESCE(SUM(vlr_desconto),0) AS valor_desconto,
               COUNT(*) AS ocorrencias
        FROM public.pdv_descontos_atuais {onde}
        GROUP BY 1
        ORDER BY 2 DESC, 3 DESC, 1
    """, params)
    canais = query(f"""
        SELECT CASE WHEN POSITION('CSC' IN UPPER(COALESCE(fiscal_cx,''))) > 0 THEN 'CSC' ELSE 'Loja' END,
               COALESCE(SUM(vlr_desconto),0), COUNT(*)
        FROM public.pdv_descontos_atuais {onde} GROUP BY 1 ORDER BY 2 DESC
    """, params)

    conciliado = dados_conciliados(onde, params)
    consolidado = conciliado['total']
    tem_rob = base_rob_ativa() is not None
    if conciliado['faltantes'] and tem_rob:
        st.warning(f"Conciliação parcial: {len(conciliado['faltantes'])} combinações loja/mês sem ROB positiva. "
                   "Percentuais de períodos incompletos ficam indisponíveis.")
    elif not tem_rob:
        st.info("A base ROB ainda não foi publicada. Vá em Administração → Importação ROB.")

    st.write("")
    col1, col2, col3, col4 = st.columns(4, gap="medium")
    with col1: kpi("Desconto concedido", brl(total, True), "Valor acumulado nos filtros", "orange")
    with col2: kpi("Lojas analisadas", numero_br(n_lojas), "Unidades com registros")
    with col3: kpi("Produtos envolvidos", numero_br(n_produtos), "Códigos de produto distintos", "blue")
    with col4: kpi("Participação CSC", percentual(valor_csc, total), "No total de descontos", "orange")

    st.write("")
    c_fin1, c_fin2, c_fin3, c_fin4 = st.columns(4, gap='medium')
    with c_fin1: kpi('Receita Operacional Bruta (ROB)', brl(consolidado['receita'], True), 'Somada uma vez por loja/mês', 'blue')
    with c_fin2: kpi('% desconto / ROB', porcentagem_rob(consolidado['percentual']),
                     'Disponível apenas com cobertura completa', 'orange')
    with c_fin3: kpi('Teto pela meta', brl(consolidado['teto'], True) if consolidado['cobertura_completa'] else '—',
                     'Metas vigentes em cada mês')
    with c_fin4: kpi('Oportunidade de redução', brl(consolidado['excesso'], True) if consolidado['excesso'] is not None else '—',
                     'Excesso de descontos acima do teto', 'orange')

    secao('Ranking de lojas - Desconto Manual em PDV',
          'Todas as lojas com descontos no período')
    # Botões convencionais evitam o contraste imprevisível de st.segmented_control
    # quando a aparência é alternada via CSS sem trocar o tema global do Streamlit.
    if 'ranking_criterio' not in st.session_state:
        st.session_state.ranking_criterio = 'Valor Desconto Manual (R$)'
    st.markdown('<div class="aq-filter-label">Ordenar ranking por</div>', unsafe_allow_html=True)
    escolha_valor, escolha_percentual, _ = st.columns([1.45, 1.40, 3.0], gap='small')
    with escolha_valor:
        st.button('Valor Desconto Manual (R$)', key='ranking_btn_valor',
                  type='primary' if st.session_state.ranking_criterio == 'Valor Desconto Manual (R$)' else 'secondary',
                  width='stretch', on_click=selecionar_ranking, args=('Valor rebaixado (R$)',))
    with escolha_percentual:
        st.button('% desconto / ROB', key='ranking_btn_percentual',
                  type='primary' if st.session_state.ranking_criterio == '% desconto / ROB' else 'secondary',
                  width='stretch', on_click=selecionar_ranking, args=('% desconto / ROB',))
    criterio_ranking = st.session_state.ranking_criterio
    if criterio_ranking == '% desconto / ROB':
        ranking_ordenado = sorted(ranking,
            key=lambda linha: float(conciliado['lojas'].get(codigo_loja(linha[0]), {}).get('percentual') or -1),
            reverse=True)
    else:
        ranking_ordenado = ranking
    # Sem corte Top 10: ranking completo em um quadro com rolagem interna.
    lojas_ranking = ranking_ordenado
    linhas_ranking = []
    soma_ranking_desconto = Decimal(0)
    soma_ranking_rob = Decimal(0)
    n_incompletos = 0
    for i, (loja, valor, contagem) in enumerate(lojas_ranking, start=1):
        dados_loja = conciliado['lojas'].get(codigo_loja(loja), {})
        taxa = dados_loja.get('percentual')
        soma_ranking_desconto += d(valor)
        soma_ranking_rob += dados_loja.get('receita', Decimal(0))
        n_incompletos += int(not dados_loja.get('cobertura_completa', False))
        linhas_ranking.append({
            'rank': i, 'loja': loja, 'valor': brl(valor),
            'participacao': percentual(valor, total),
            'rob': brl(dados_loja.get('receita')) if dados_loja.get('cobertura_completa') else '—',
            'percent_rob': porcentagem_rob(taxa, casas=2),
            'media': variacao_media(taxa, consolidado['percentual']),
        })
    percentual_total_ranking = pct(soma_ranking_desconto, soma_ranking_rob) if n_incompletos == 0 else None
    total_ranking = {
        'rank': '', 'loja': 'TOTAL LOJAS', 'valor': brl(soma_ranking_desconto),
        'participacao': percentual(soma_ranking_desconto, total),
        'rob': brl(soma_ranking_rob) if n_incompletos == 0 else '—',
        'percent_rob': porcentagem_rob(percentual_total_ranking, casas=2),
        'media': variacao_media(percentual_total_ranking, consolidado['percentual']),
    }

    # O gráfico mantém o histórico do ano, mesmo quando um mês está selecionado.
    # Não ignora o escopo de loja ou de origem.
    onde_historico, params_historico = condicoes(
        escopo['ano'], 'Todos', escopo['lojas_aplicadas'],
        escopo['origem'], escopo['filtro_hierarquia_ativo']
    )
    onde_historico, params_historico = condicoes_cruzadas(
        onde_historico, params_historico, filtros_cruzados_ativos()
    )
    onde_historico = adicionar_condicao(onde_historico, 'dta_movimento IS NOT NULL')
    historico_rebaixas = query(f"""
        SELECT DATE_TRUNC('month', dta_movimento)::date AS mes,
               COALESCE(SUM(vlr_desconto), 0) AS total_rebaixas
        FROM public.pdv_descontos_atuais {onde_historico}
        GROUP BY 1 ORDER BY 1
    """, params_historico)

    # Dois painéis irmãos: mesmo início vertical, proporção e altura mínima.
    # Os painéis são containers Streamlit reais, não divs HTML que englobam widgets.
    coluna_tabela, coluna_historico = st.columns([1, 1], gap='medium', vertical_alignment='top')
    with coluna_tabela:
        with st.container(border=True, key='aq_ranking_panel'):
            st.markdown('<div class="aq-panel-title aq-comparison-title">Ranking de lojas</div>',
                        unsafe_allow_html=True)
            with st.container(key='aq_comparison_controls'):
                with st.popover('Exibir mais colunas', icon=':material/view_column:'):
                    # A coluna de valor foi fixada; limpa selecao legada do widget.
                    if 'ranking_colunas_extras' in st.session_state:
                        st.session_state.ranking_colunas_extras = [
                            item for item in st.session_state.ranking_colunas_extras
                            if item not in {'Valor rebaixado', 'Posição (#)'}
                        ]
                    colunas_extra = st.multiselect(
                        'Colunas adicionais',
                        ['% do total', 'Receita bruta', 'vs. média rede'],
                        key='ranking_colunas_extras',
                        placeholder='Selecione as colunas que deseja visualizar'
                    )
            colunas, registros, rodape, indices_numericos, indices_fortes = preparar_ranking_compacto(
                linhas_ranking, total_ranking, colunas_extra
            )
            tabela(colunas, registros, rodape, numeros=indices_numericos, fortes=indices_fortes)
            st.caption(f'{len(lojas_ranking)} lojas')
    with coluna_historico:
        if escopo['filtro_hierarquia_ativo'] and not escopo['lojas_aplicadas']:
            titulo_historico = 'Rebaixas mensais · nenhuma loja correspondente'
        elif len(escopo['lojas_aplicadas']) == 1:
            titulo_historico = f"Rebaixas mensais · {escopo['lojas_aplicadas'][0]}"
        elif len(escopo['lojas_aplicadas']) > 1:
            titulo_historico = f"Rebaixas mensais · {len(escopo['lojas_aplicadas'])} lojas"
        else:
            titulo_historico = 'Histórico mensal de rebaixas · rede'
        with st.container(border=True, key='aq_historico_panel'):
            st.markdown(f'<div class="aq-panel-title aq-comparison-title">{escape(titulo_historico)}</div>',
                        unsafe_allow_html=True)
            with st.container(key='aq_comparison_history_info'):
                st.markdown('<div class="aq-chart-helper">Valores mensais em R$ · período selecionado</div>',
                            unsafe_allow_html=True)
            if historico_rebaixas:
                exibir_grafico('historico', st.session_state.aq_dark, historico_rebaixas)
            else:
                vazio('Sem histórico de descontos', 'Não há movimentos para as lojas e o ano selecionados.')
            st.caption('Histórico anual; respeita loja e origem, mas não restringe o mês.')

    st.write('')
    secao('Análise de oportunidade de desconto sobre a ROB')
    # Painéis com o mesmo topo e altura mínima: o bloco de indicadores
    # contém apenas média dinâmica e meta vigente, sem benchmark histórico.
    c_graf, c_ref = st.columns([2.15, 1], gap='medium', vertical_alignment='top')
    with c_graf:
        with st.container(border=True, key='aq_rob_chart_panel'):
            st.markdown('<div class="aq-panel-title">% de desconto / receita por loja × meta</div>',
                        unsafe_allow_html=True)
            if any(x['percentual'] is not None for x in conciliado['lojas'].values()):
                exibir_grafico('oportunidades', st.session_state.aq_dark, ranking_ordenado, conciliado)
            else:
                vazio('ROB não conciliada', 'Importe a ROB ou confira meses/lojas sem correspondência.')
    with c_ref:
        with st.container(border=True, key='aq_rob_reference_panel'):
            st.markdown('<div class="aq-panel-title">Referências de desempenho</div>',
                        unsafe_allow_html=True)
            kpi('Média do período selecionado', porcentagem_rob(consolidado['percentual']),
                'Rede no escopo selecionado, somente com ROB completa')
            st.write('')
            kpi('Meta vigente neste mês', f'{numero_br(meta_atual(), 2)}%',
                'Alterável exclusivamente em Administração', 'blue')

    # Consultas preservadas: mesma origem de descontos, filtros e totais da V7.
    # Fiscais e produtos são carregados antes de criar os dois painéis, para
    # evitar diferenças de posicionamento devido à execução das consultas.
    condicao_fiscais = adicionar_condicao(
        onde, "TRIM(COALESCE(fiscal_cx,'')) <> '' AND POSITION('CSC' IN UPPER(COALESCE(fiscal_cx,''))) = 0"
    )
    fiscais = query(f"""
        SELECT TRIM(fiscal_cx), COALESCE(empresa,'Não informado'),
               COALESCE(SUM(quantidade),0), COALESCE(SUM(vlr_desconto),0)
        FROM public.pdv_descontos_atuais {condicao_fiscais}
        GROUP BY 1,2 ORDER BY 4 DESC LIMIT 10
    """, params)
    total_fiscais = sum(float(x[3] or 0) for x in fiscais)
    qtd_fiscais = sum(float(x[2] or 0) for x in fiscais)

    produtos = query(f"""
        SELECT cod_produto,
               COALESCE(NULLIF(TRIM(produto),''),'Não informado'),
               COALESCE(SUM(quantidade),0), COALESCE(SUM(vlr_desconto),0)
        FROM public.pdv_descontos_atuais {onde}
        GROUP BY 1, 2 ORDER BY 4 DESC LIMIT 10
    """, params)
    total_produtos = sum(float(x[3] or 0) for x in produtos)

    st.write("")
    # Dois painéis irmãos, com a mesma linha de início, cabeçalhos de altura
    # fixa e tabelas roláveis horizontalmente em telas com largura limitada.
    col_fiscais, col_produtos = st.columns([1, 1], gap="medium", vertical_alignment="top")
    with col_fiscais:
        with st.container(border=True, key="aq_fiscais_panel"):
            st.markdown(
                '<div class="aq-dual-title">Top 10 fiscais autorizadores</div>',
                unsafe_allow_html=True,
            )
            tabela(
                [("rank", "#"), ("fiscal", "Fiscal autorizador"), ("loja", "Loja"),
                 ("qtd", "Qtd. rebaixada"), ("valor", "Valor liberado"), ("pct", "% do total")],
                [(i, nome, loja, numero_br(qtd, 2), brl(valor), percentual(valor, total))
                 for i, (nome, loja, qtd, valor) in enumerate(fiscais, 1)],
                ("", "TOTAL TOP 10 FISCAIS", f"{len(fiscais)} fiscais", numero_br(qtd_fiscais, 2),
                 brl(total_fiscais), percentual(total_fiscais, total)) if fiscais else None,
                numeros=(3, 4, 5), fortes=(1, 4),
            )
            # Reserva espaço real dentro do contêiner, evitando que a tabela
            # encoste na borda inferior em diferentes resoluções/temas.
            st.markdown('<div class="aq-dual-footer-clearance" aria-hidden="true"></div>',
                        unsafe_allow_html=True)
    with col_produtos:
        with st.container(border=True, key="aq_produtos_panel"):
            st.markdown(
                '<div class="aq-dual-title">Top 10 produtos em rebaixa de preço</div>',
                unsafe_allow_html=True,
            )
            tabela_com_acao(
                [("rank", "#"), ("produto", "Produto"),
                 ("qtd", "Qtd. rebaixada"), ("valor", "Valor rebaixado"),
                 ("pct", "% do total")],
                [(i, nome, numero_br(qtd, 2), brl(valor), percentual(valor, total))
                 for i, (_, nome, qtd, valor) in enumerate(produtos, 1)],
                "produto", [(codigo, nome) for codigo, nome, _, _ in produtos],
                altura=438,
                totalizador=("TOTAL TOP 10 PRODUTOS", brl(total_produtos),
                             percentual(total_produtos, total)) if produtos else None,
            )
            # A caixa de seleção nativa do Streamlit já indica a ação;
            # sem a coluna decorativa e sem texto adicional que desalinhava o painel.
            st.markdown('<div class="aq-dual-footer-clearance" aria-hidden="true"></div>',
                        unsafe_allow_html=True)

    st.write("")
    secao("Motivos e origem dos descontos",
          "Ranking dos motivos e identificação automática CSC × Loja")

    # Ambos são painéis irmãos com mesmo alinhamento superior e altura mínima.
    col_motivos, col_origem = st.columns([1.70, 1], gap="medium", vertical_alignment="top")
    with col_motivos:
        with st.container(border=True, key="aq_motivos_panel"):
            st.markdown('<div class="aq-panel-title aq-motivos-title">Ranking de motivos</div>',
                        unsafe_allow_html=True)
            if motivos:
                # Ranking ordenado por valor concedido; cada COUNT(*) representa
                # uma ocorrência, não a soma da quantidade de mercadorias.
                soma_motivos = sum((d(valor) for _, valor, _ in motivos), Decimal(0))
                qtd_ocorrencias = sum(int(qtd) for _, _, qtd in motivos)
                st.caption("Marque a caixa da linha para filtrar o dashboard por motivo.")
                tabela_com_acao(
                    [("rank", "#"), ("motivo", "Motivo"),
                     ("qtd", "Ocorrências"), ("valor", "Desconto (R$)"),
                     ("pct", "% do total")],
                    [(pos, motivo, numero_br(qtd), brl(valor), percentual(valor, total))
                     for pos, (motivo, valor, qtd) in enumerate(motivos, 1)],
                    "motivo", [motivo for motivo, _, _ in motivos],
                    altura=465,
                )
                st.markdown(
                    f'<div class="aq-total-interativo"><strong>TOTAL MOTIVOS · {numero_br(qtd_ocorrencias)} ocorrências</strong>'
                    f'<span>{brl(soma_motivos)} &nbsp; {percentual(soma_motivos, total)}</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                vazio("Nenhum motivo encontrado", "Altere os filtros para ampliar o período.")

    with col_origem:
        with st.container(border=True, key="aq_origem_panel"):
            st.markdown('<div class="aq-panel-title aq-motivos-title">CSC × Loja</div>',
                        unsafe_allow_html=True)
            if canais:
                exibir_grafico('canais', st.session_state.aq_dark, canais)
                st.caption("Marque a caixa de CSC ou Loja para filtrar os indicadores.")
                tabela_com_acao(
                    [("tipo", "Origem"), ("valor", "Desconto"), ("reg", "Registros")],
                    [(canal, brl(valor), numero_br(qtd)) for canal, valor, qtd in canais],
                    "origem", [canal for canal, _, _ in canais], altura=154,
                )
            else:
                vazio("Nenhum registro", "Não há descontos para a origem selecionada.")

    detalhes = st.expander("Detalhamento operacional e clientes", key="detalhes", on_change="rerun")
    if not detalhes.open:
        return
    with detalhes:
        aba_lojas, aba_produtos, aba_fiscais, aba_clientes = st.tabs(["Lojas", "Produtos", "Fiscais", "Clientes"], key="abas_detalhes", on_change="rerun")
        with aba_lojas:
            if aba_lojas.open:
                tabela(
                    [("loja", "Loja"), ("valor", "Desconto (R$)"), ("registros", "Registros")],
                    [(loja, brl(valor), numero_br(n)) for loja, valor, n in ranking[:30]],
                    numeros=(1, 2), fortes=(0, 1),
                )
        with aba_produtos:
            if aba_produtos.open:
                tabela(
                    [("produto", "Produto"), ("qtd", "Quantidade"), ("valor", "Desconto (R$)")],
                    [(nome, numero_br(qtd, 2), brl(valor)) for _, nome, qtd, valor in produtos],
                    numeros=(1, 2), fortes=(0, 2),
                )
        with aba_fiscais:
            if aba_fiscais.open:
                tabela(
                    [("fiscal", "Fiscal"), ("loja", "Loja"), ("qtd", "Quantidade"), ("valor", "Desconto (R$)")],
                    [(nome, loja, numero_br(qtd, 2), brl(valor)) for nome, loja, qtd, valor in fiscais],
                    numeros=(2, 3), fortes=(0, 3),
                )
        with aba_clientes:
            if aba_clientes.open:
                clientes = query(f"""
                    SELECT COALESCE(NULLIF(TRIM(cliente),''),'Não informado'),
                           COALESCE(SUM(vlr_desconto),0), COUNT(*)
                    FROM public.pdv_descontos_atuais {onde}
                    GROUP BY 1 ORDER BY 2 DESC LIMIT 30
                """, params)
                tabela(
                    [("cliente", "Cliente"), ("valor", "Desconto (R$)"), ("registros", "Registros")],
                    [(nome, brl(valor), numero_br(qtd)) for nome, valor, qtd in clientes],
                    numeros=(1, 2), fortes=(0, 1),
                )


def gerar_excel_evolucao_loja_mes(linhas: list[dict], totalizador: dict) -> bytes:
    """Gera a planilha detalhada com valores numéricos e totalizador."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    arquivo = Workbook()
    planilha = arquivo.active
    planilha.title = "Evolução por loja"
    planilha.sheet_view.showGridLines = False

    cabecalhos = [
        "Mês", "Loja", "Desconto (R$)", "ROB (R$)", "Meta (%)",
        "% Desconto/ROB", "Teto (R$)", "Excesso (R$)", "Registros",
    ]
    planilha.append(cabecalhos)

    def numero_excel(valor):
        return float(valor) if valor is not None else None

    for item in linhas:
        planilha.append([
            item["mes"], item["loja"], numero_excel(item["desconto"]),
            numero_excel(item["rob"]), numero_excel(item["meta"]),
            numero_excel(item["percentual"]), numero_excel(item["teto"]),
            numero_excel(item["excesso"]), int(item["registros"]),
        ])

    planilha.append([
        "TOTAL", "TODAS AS LOJAS",
        numero_excel(totalizador["desconto"]),
        numero_excel(totalizador["rob"]),
        None,
        numero_excel(totalizador["percentual"]),
        numero_excel(totalizador["teto"]),
        numero_excel(totalizador["excesso"]),
        int(totalizador["registros"]),
    ])

    preenchimento_cabecalho = PatternFill("solid", fgColor="103B49")
    preenchimento_total = PatternFill("solid", fgColor="103B49")
    preenchimento_par = PatternFill("solid", fgColor="F0F5F7")
    preenchimento_impar = PatternFill("solid", fgColor="FFFFFF")
    fonte_branca = Font(name="Aptos", bold=True, color="FFFFFF", size=10)
    fonte_normal = Font(name="Aptos", color="17313B", size=10)
    fonte_total = Font(name="Aptos", bold=True, color="FFFFFF", size=10)
    borda = Border(bottom=Side(style="hair", color="D7E1E5"))

    for celula in planilha[1]:
        celula.fill = preenchimento_cabecalho
        celula.font = fonte_branca
        celula.alignment = Alignment(horizontal="center", vertical="center")
    planilha.row_dimensions[1].height = 25

    linha_total = planilha.max_row
    for linha in planilha.iter_rows(min_row=2, max_row=linha_total):
        indice = linha[0].row
        for celula in linha:
            celula.font = fonte_normal
            celula.border = borda
            celula.alignment = Alignment(vertical="center")
            celula.fill = preenchimento_par if indice % 2 == 0 else preenchimento_impar
        linha[0].number_format = "mm/yyyy"
        for indice_coluna in (3, 4, 7, 8):
            linha[indice_coluna - 1].number_format = '"R$" #,##0.00'
        linha[4].number_format = r"0.00\%"
        linha[5].number_format = r"0.000\%"
        linha[8].number_format = "#,##0"

    for celula in planilha[linha_total]:
        celula.fill = preenchimento_total
        celula.font = fonte_total
        celula.border = Border(top=Side(style="thin", color="103B49"))
        celula.alignment = Alignment(vertical="center")
    planilha.row_dimensions[linha_total].height = 23

    larguras = {
        "A": 13, "B": 34, "C": 19, "D": 20, "E": 13,
        "F": 19, "G": 19, "H": 19, "I": 14,
    }
    for coluna, largura in larguras.items():
        planilha.column_dimensions[coluna].width = largura

    if linhas:
        planilha.auto_filter.ref = f"A1:I{len(linhas) + 1}"
    planilha.freeze_panes = "A2"
    arquivo.properties.creator = "ÁQUILA"

    buffer = BytesIO()
    arquivo.save(buffer)
    return buffer.getvalue()


def evolucao_mensal(lote: tuple) -> None:
    titulo('Evolução Mensal','Descontos reais, receitas e metas históricas da rede.','ANÁLISE TEMPORAL / ÁQUILA')
    cabecalho_base(lote)
    ferramentas_de_filtro()
    onde_base, params_base, _ = filtros_dashboard('mensal')
    onde, params = condicoes_cruzadas(onde_base, params_base, filtros_cruzados_ativos())
    onde_data = adicionar_condicao(onde,'dta_movimento IS NOT NULL')
    meses_desconto = query(f"""
        SELECT DATE_TRUNC('month',dta_movimento)::date, COALESCE(SUM(vlr_desconto),0), COUNT(*)
        FROM public.pdv_descontos_atuais {onde_data}
        GROUP BY 1 ORDER BY 1
    """,params)
    if not meses_desconto:
        vazio('Nenhum dado mensal','Não existem descontos para os filtros selecionados.')
        return
    conciliado = dados_conciliados(onde,params)
    hist_metas = metas_historicas()
    soma = conciliado['total']
    meses = conciliado['meses']

    # Detalhamento na mesma granularidade da conciliação: uma linha por loja/mês.
    # O agrupamento ocorre antes do JOIN com a ROB para não multiplicar receita.
    detalhes_brutos = query(f"""
        WITH por_unidade_mes AS (
          SELECT SUBSTRING(BTRIM(empresa) FROM '^([0-9]{{3}})') AS codigo_loja,
                 DATE_TRUNC('month', dta_movimento)::date AS mes,
                 MIN(COALESCE(empresa,'Não informado')) AS loja,
                 COALESCE(SUM(vlr_desconto),0) AS desconto,
                 COUNT(*) AS registros
          FROM public.pdv_descontos_atuais {onde_data}
          GROUP BY 1,2
        )
        SELECT d.codigo_loja, d.mes, d.loja, d.desconto,
               r.receita_bruta, d.registros
        FROM por_unidade_mes d
        LEFT JOIN public.rob_receitas_atuais r
          ON r.codigo_loja=d.codigo_loja AND r.mes_vigencia=d.mes
        ORDER BY d.mes, d.loja
    """, params)

    linhas_loja_mes = []
    for codigo, mes, loja, desconto, receita, registros in detalhes_brutos:
        # Reaproveita o motor oficial de conciliação para manter exatamente
        # as mesmas regras de ROB, percentual, teto, excesso e cobertura.
        calculo = calc_linhas(
            [(codigo, mes, loja, desconto, receita)], hist_metas
        )['total']
        meta = meta_do_mes(mes, hist_metas)
        cobertura = bool(calculo['cobertura_completa'])
        linhas_loja_mes.append({
            'mes': mes,
            'loja': loja,
            'desconto': calculo['desconto'],
            'rob': calculo['receita'] if cobertura else None,
            'meta': meta,
            'percentual': calculo['percentual'],
            'teto': calculo['teto'] if cobertura else None,
            'excesso': calculo['excesso'],
            'registros': int(registros or 0),
        })
    if conciliado['faltantes']:
        st.warning(f"Há {len(conciliado['faltantes'])} combinações loja/mês sem ROB positiva. "
                   'Metas em reais e percentuais incompletos serão exibidos como indisponíveis.')
    total = sum((d(x[1]) for x in meses_desconto), Decimal(0))
    maior = max(meses_desconto,key=lambda x:float(x[1]))
    a,b,c,e = st.columns(4,gap='medium')
    with a: kpi('Desconto acumulado',brl(total,True),'Período selecionado','orange')
    with b: kpi('ROB conciliada',brl(soma['receita'],True),'Receita por loja/mês','blue')
    with c: kpi('Desconto / ROB',porcentagem_rob(soma['percentual']),
                'Exige cobertura integral das lojas')
    with e: kpi('Maior mês de desconto',maior[0].strftime('%m/%Y'),brl(maior[1]),'orange')

    secao('Realizado × teto permitido','Teto financeiro = ROB mensal × meta percentual vigente naquele mês')
    c_g,c_k = st.columns([2.1,.9],gap='medium')
    with c_g:
        with st.container(border=True):
            st.markdown('<div class="aq-panel-title">Descontos realizados × metas mensais (R$)</div>',unsafe_allow_html=True)
            exibir_grafico('realizado', st.session_state.aq_dark, meses)
    with c_k:
        with st.container(border=True):
            kpi('Meta vigente',f'{numero_br(meta_atual(),2)}%','A alteração vale a partir do mês corrente')
            st.write('')
            kpi('Teto acumulado',brl(soma['teto'],True) if soma['cobertura_completa'] else '—',
                'Respeita a meta de cada mês','blue')
            st.write('')
            kpi('Oportunidade',brl(soma['excesso'],True) if soma['excesso'] is not None else '—',
                'Descontos acima do limite','orange')

    secao('Histórico consolidado','Receita, desconto, teto e meta por mês, com conferência de conciliação')
    resultados=[]
    for mes in sorted(meses):
        resumo=meses[mes]
        registro=next((x[2] for x in meses_desconto if x[0]==mes),0)
        meta = meta_do_mes(mes,hist_metas)
        resultados.append((mes.strftime('%m/%Y'),brl(resumo['desconto']),
                          brl(resumo['receita']) if resumo['cobertura_completa'] else '—',
                          f'{numero_br(meta,2)}%' if meta is not None else '—',
                          porcentagem_rob(resumo['percentual']),
                          brl(resumo['teto']) if resumo['cobertura_completa'] else '—',
                          brl(resumo['excesso']) if resumo['excesso'] is not None else '—',
                          numero_br(registro)))
    tabela([('mes','Mês'),('desconto','Desconto (R$)'),('rob','ROB (R$)'),
            ('meta','Meta (%)'),('pct','% Desconto/ROB'),('teto','Teto (R$)'),
            ('excesso','Excesso (R$)'),('registros','Registros')],resultados,
           ('TOTAL',brl(soma['desconto']),brl(soma['receita']) if soma['cobertura_completa'] else '—',
            '—',porcentagem_rob(soma['percentual']),
            brl(soma['teto']) if soma['cobertura_completa'] else '—',
            brl(soma['excesso']) if soma['excesso'] is not None else '—',
            numero_br(sum(int(x[2]) for x in meses_desconto))),
           numeros=(1,2,3,4,5,6,7),fortes=(0,1))

    secao('Detalhamento por loja e mês',
          'Uma linha por unidade em cada mês.')
    if linhas_loja_mes:
        total_registros_detalhe = sum(item['registros'] for item in linhas_loja_mes)
        total_detalhe = {
            'desconto': soma['desconto'],
            'rob': soma['receita'] if soma['cobertura_completa'] else None,
            'percentual': soma['percentual'],
            'teto': soma['teto'] if soma['cobertura_completa'] else None,
            'excesso': soma['excesso'],
            'registros': total_registros_detalhe,
        }
        linhas_visuais = [(
            item['mes'].strftime('%m/%Y'), item['loja'], brl(item['desconto']),
            brl(item['rob']) if item['rob'] is not None else '—',
            f"{numero_br(item['meta'], 2)}%" if item['meta'] is not None else '—',
            porcentagem_rob(item['percentual']),
            brl(item['teto']) if item['teto'] is not None else '—',
            brl(item['excesso']) if item['excesso'] is not None else '—',
            numero_br(item['registros']),
        ) for item in linhas_loja_mes]
        total_visual = (
            'TOTAL', 'TODAS AS LOJAS', brl(total_detalhe['desconto']),
            brl(total_detalhe['rob']) if total_detalhe['rob'] is not None else '—',
            '—', porcentagem_rob(total_detalhe['percentual']),
            brl(total_detalhe['teto']) if total_detalhe['teto'] is not None else '—',
            brl(total_detalhe['excesso']) if total_detalhe['excesso'] is not None else '—',
            numero_br(total_detalhe['registros']),
        )
        col_info, col_download = st.columns([3.4, 1], vertical_alignment='center')
        with col_info:
            st.caption(f"{numero_br(len(linhas_loja_mes))} combinações loja/mês · "
                       f"{numero_br(total_registros_detalhe)} registros")
        with col_download:
            planilha_excel = gerar_excel_evolucao_loja_mes(linhas_loja_mes, total_detalhe)
            st.download_button(
                'Baixar Excel', data=planilha_excel,
                file_name=f"evolucao_mensal_loja_a_loja_{dt.datetime.now(ZoneInfo('America/Recife')).strftime('%Y%m%d_%H%M')}.xlsx",
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                icon=':material/download:', width='stretch',
                key='download_evolucao_loja_mes',
            )
        tabela(
            [('mes','Mês'),('loja','Loja'),('desconto','Desconto (R$)'),
             ('rob','ROB (R$)'),('meta','Meta (%)'),('pct','% Desconto/ROB'),
             ('teto','Teto (R$)'),('excesso','Excesso (R$)'),('registros','Registros')],
            linhas_visuais, total_visual,
            numeros=(2,3,4,5,6,7,8), fortes=(1,2),
        )
    else:
        vazio('Nenhum detalhamento disponível',
              'Não foram encontradas combinações de loja e mês para os filtros selecionados.')

    nota('Ambiente de Desenvolvimento, Não disponibilizar ou compartilhar os dados fora da rede corporativa.')
    if conciliado['faltantes']:
        with st.expander('Ver lojas e meses sem ROB válida',expanded=False):
            tabela([('codigo','Código'),('mes','Mês'),('motivo','Pendência')],
                   [(cod or '—',mes.strftime('%m/%Y'),motivo)
                    for cod,mes,motivo in conciliado['faltantes'][:100]])


def administracao() -> None:
    titulo("Administração", "Gerencie separadamente as bases de descontos, ROB e as metas da rede.", "AMBIENTE RESTRITO")
    aba_base, aba_rob, aba_meta, aba_sistema = st.tabs(["Importação de descontos", "Importação ROB", "Meta da rede", "Segurança"], key="abas_admin", on_change="rerun")
    with aba_base:
        if aba_base.open:
            with st.container(border=True):
                st.markdown('<div class="aq-section-title">Publicar uma nova base Excel</div>', unsafe_allow_html=True)
                st.info("A nova planilha substitui completamente a base antiga. A publicação ocorre apenas após validar e carregar todos os registros.")
                upload = st.file_uploader("Selecione a planilha de descontos", type=["xlsx"], key="upload_base")
                if upload is not None:
                    st.caption(f"{escape(upload.name)} · {numero_br(upload.size / 1024**2, 1)} MB")
                    confirmar = st.checkbox("Confirmo que desejo substituir integralmente a base atual", key="confirma_substituicao")
                    if st.button("Validar, importar e publicar", type="primary", disabled=not confirmar, width="stretch"):
                        barra = st.progress(0.0, text="Iniciando validação da planilha...")
                        aviso = st.empty()
                        try:
                            def progresso(qtd: int):
                                barra.progress(min(.99, qtd / 110_000), text="Transferindo registros para a base temporária...")
                                aviso.caption(f"{numero_br(qtd)} registros carregados. A base anterior segue ativa até a conclusão.")
                            from ingestao import importar_upload
                            resultado = importar_upload(upload, DB_URL, progresso)
                            st.cache_data.clear()
                            barra.progress(1.0, text="Nova base publicada")
                            aviso.success(f"Publicação concluída: {numero_br(resultado['linhas'])} registros substituíram a base anterior.")
                        except Exception as erro:
                            st.error(f"A importação não foi concluída. Verifique o arquivo: {type(erro).__name__}: {erro}")
                atual = base_ativa()
                if atual:
                    st.caption(f"Base em produção: **{atual[0]}** · {numero_br(atual[1])} registros")
    with aba_rob:
        if aba_rob.open:
            with st.container(border=True):
                st.markdown('<div class="aq-section-title">Publicar receita bruta operacional (ROB)</div>',unsafe_allow_html=True)
                st.info('Cada nova ROB Excel substitui totalmente a ROB anterior. '
                        'Descontos e metas não são alterados; falhas mantêm a ROB ativa.')
                st.caption('Formato aceito: aba BASE · Loja | Vlr Venda Atual | Ano/Mês (AAAA/MM). '
                           'A chave única é código de loja + mês.')
                upload_rob = st.file_uploader('Selecione a base de receita ROB',type=['xlsx'],key='upload_rob')
                if upload_rob is not None:
                    confirmar_rob = st.checkbox('Confirmo a substituição integral da ROB atual',key='confirmar_rob')
                    if st.button('Validar, importar e publicar ROB',type='primary',disabled=not confirmar_rob,width='stretch'):
                        progresso_ui = st.progress(0,text='Validando receita bruta...')
                        try:
                            def progresso_rob(qtd: int) -> None:
                                progresso_ui.progress(min(.99,qtd/1000),text=f'Importados {numero_br(qtd)} registros ROB')
                            from rob_ingestao import importar_upload_rob
                            resultado = importar_upload_rob(upload_rob,DB_URL,progresso_rob)
                            st.cache_data.clear()
                            progresso_ui.progress(1.0,text='ROB publicada')
                            st.success(f"ROB publicada: {numero_br(resultado['linhas'])} registros. "
                                       'Versão anterior substituída integralmente.')
                            if resultado['negativas'] or resultado['zeradas']:
                                st.warning(f"A base contém {resultado['negativas']} receitas negativas e "
                                           f"{resultado['zeradas']} zeradas. Serão sinalizadas na análise, "
                                           'não usadas como denominador.')
                            st.rerun()
                        except Exception as erro:
                            st.error(f'Falha na importação ROB (base anterior preservada): {type(erro).__name__}: {erro}')
                ativa = base_rob_ativa()
                if ativa:
                    st.caption(f'ROB em produção: **{escape(ativa[0])}** · {numero_br(ativa[1])} registros')
                else:
                    st.caption('Nenhuma ROB publicada ainda. Execute sql/002_rob.sql antes da primeira importação.')
    with aba_meta:
        if aba_meta.open:
            with st.container(border=True):
                st.markdown('<div class="aq-section-title">Meta global de descontos sobre ROB</div>', unsafe_allow_html=True)
                st.caption("Aplica-se a todas as lojas. A meta entra em vigor no dia 1º do mês corrente e não altera os meses encerrados.")
                atual = meta_atual()
                st.markdown(
                    f'<div style="font-size:2.45rem;font-weight:850;color:var(--aq-teal);">{numero_br(atual, 2)}%</div>'
                    f'<div style="color:var(--aq-muted);margin-bottom:18px;">Meta vigente neste mês</div>',
                    unsafe_allow_html=True,
                )
                nova_meta = st.number_input("Nova meta (%)", min_value=0.0, max_value=100.0,
                                            value=float(atual), step=0.01, format="%.2f")
                if st.button("Salvar meta para este mês", type="primary"):
                    mes = dt.datetime.now(ZoneInfo("America/Recife")).date().replace(day=1)
                    with psycopg.connect(DB_URL) as con:
                        with con.cursor() as cur:
                            cur.execute("SELECT percentual FROM public.pdv_metas WHERE mes_vigencia=%s FOR UPDATE", (mes,))
                            anterior = cur.fetchone()
                            cur.execute("""
                                INSERT INTO public.pdv_metas(mes_vigencia, percentual, alterado_por)
                                VALUES(%s,%s,%s)
                                ON CONFLICT(mes_vigencia) DO UPDATE SET
                                    percentual=EXCLUDED.percentual,
                                    alterado_por=EXCLUDED.alterado_por,
                                    atualizado_em=now()
                            """, (mes, decimal.Decimal(str(nova_meta)), ADMIN_USER))
                            cur.execute("""
                                INSERT INTO public.pdv_auditoria_metas
                                    (mes_vigencia, percentual_anterior, percentual_novo, alterado_por)
                                VALUES(%s,%s,%s,%s)
                            """, (mes, anterior[0] if anterior else None,
                                  decimal.Decimal(str(nova_meta)), ADMIN_USER))
                    st.cache_data.clear()
                    st.success("Meta salva. O histórico dos meses anteriores foi preservado.")
                    st.rerun()
                historico = query("""
                    SELECT mes_vigencia, percentual, alterado_por, atualizado_em
                    FROM public.pdv_metas ORDER BY mes_vigencia DESC LIMIT 36
                """)
                st.markdown('<div class="aq-section-title">Histórico das metas</div>', unsafe_allow_html=True)
                tabela(
                    [("vigencia", "Vigência"), ("percentual", "Meta (%)"),
                     ("autor", "Responsável"), ("data", "Alterado em")],
                    [(x[0].strftime("%m/%Y"), f"{numero_br(x[1], 2)}%", x[2],
                      x[3].strftime("%d/%m/%Y %H:%M") if x[3] else "—") for x in historico],
                    numeros=(1,), fortes=(0, 1),
                )
    with aba_sistema:
        if aba_sistema.open:
            with st.container(border=True):
                st.markdown('<div class="aq-section-title">Status de segurança</div>', unsafe_allow_html=True)
                st.info("Esta etapa do projeto usa login administrativo provisório. Os acessos Gerente, Distrital e Diretor e o cadastro de usuários ainda não estão implementados.")
                st.markdown("**Credenciais:** armazenadas apenas em `.streamlit/secrets.toml` ou nos Secrets da hospedagem.")
                st.markdown("**Supabase:** as consultas são executadas no servidor; nunca exponha a URL de banco nas telas ou no repositório.")
                st.markdown("**Próxima etapa:** autorização por loja/distrito na consulta SQL, controle de sessão e gerenciamento de usuários.")


if not DB_URL or not ADMIN_USER or not ADMIN_PASSWORD_HASH:
    st.error("Configure SUPABASE_DB_URL, ADMIN_USER e ADMIN_PASSWORD_HASH no Secrets do Streamlit.")
    st.stop()

if not st.session_state.get("admin_ok"):
    st.set_page_config(initial_sidebar_state="collapsed")
    with st.container(key="login_layout"):
        marca, acesso = st.columns([1.15, 1], gap="large", vertical_alignment="center")
        with marca:
            st.markdown('<div class="aq-login-brand">Novo Atacarejo x ÁQUILA<span>.</span></div>'
                        '<div class="aq-overline">ANALYTICS / DESCONTOS PDV</div>'
                        '<h1 class="aq-login-title">Clareza nos dados.<br>Precisão nas decisões.</h1>'
                        '<p class="aq-subtitle">Uma visão integrada dos descontos da rede, '
                        'com indicadores por loja, produto e período.</p>'
                        '<div class="aq-login-features">Visão executiva / Evolução mensal / Gestão da base</div>',
                        unsafe_allow_html=True)
        with acesso:
            with st.container(border=True, key="login_card"):
                st.caption("ÁREA ADMINISTRATIVA")
                st.subheader("Bem-vindo ao PDV Analytics")
                st.write("Entre com suas credenciais para acessar o painel.")
                with st.form("login_admin", border=False):
                    usuario = st.text_input("Usuário", placeholder="Seu usuário", key="login_usuario")
                    senha = st.text_input("Senha", type="password", placeholder="Sua senha", key="login_senha")
                    entrar = st.form_submit_button("Acessar painel", type="primary", width="stretch")
                if entrar:
                    if hmac.compare_digest(usuario.strip(), ADMIN_USER) and verificar_senha(senha, ADMIN_PASSWORD_HASH):
                        st.session_state.admin_ok = True
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
                st.caption("Acesso restrito à administração da rede.")
    st.stop()

def mudar_pagina(pagina: str) -> None:
    st.session_state.aq_pagina = pagina


# A tela de login não precisa carregar a biblioteca de gráficos ou o Excel.
import plotly.graph_objects as go


with st.sidebar:
    st.markdown('<div class="aq-brand">Novo Atacarejo<small>ANALYTICS · PDV</small></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="aq-user"><div class="aq-user-name">{escape(ADMIN_USER)}</div>'
                '<div class="aq-user-sub">Administrador do sistema</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="aq-sidebar-label">MENU PRINCIPAL</div>', unsafe_allow_html=True)

    paginas = [
        ("geral", "Visão geral", ":material/dashboard:"),
        ("mensal", "Evolução mensal", ":material/monitoring:"),
        ("administracao", "Administração", ":material/settings:"),
    ]
    # Barras clicáveis em largura total: sem pontos/círculos de seleção de radio.
    for chave, rotulo, icone in paginas:
        ativo = st.session_state.aq_pagina == chave
        st.button(rotulo, icon=icone, key=f"nav_{chave}",
                  type="primary" if ativo else "secondary", width="stretch",
                  on_click=mudar_pagina, args=(chave,))

    st.divider()
    st.markdown('<div class="aq-sidebar-label">APARÊNCIA</div>', unsafe_allow_html=True)
    st.toggle("Modo escuro", key="aq_dark", help="Alternar entre tema claro e escuro")
    st.divider()
    st.markdown('<div class="aq-sidebar-footer">GESTÃO DE DESCONTOS PDV<br>'
                'Painel executivo e operacional de descontos.</div>', unsafe_allow_html=True)
    if st.button("Sair do sistema", key="sair_app", width="stretch"):
        st.session_state.admin_ok = False
        st.session_state.aq_pagina = "geral"
        st.rerun()

try:
    if st.session_state.aq_pagina == "administracao":
        administracao()
    else:
        lote = base_ativa()
        if lote is None:
            titulo("Descontos PDV", "Nenhuma base operacional publicada no Supabase.")
            st.info("Acesse Administração para importar a primeira planilha Excel.")
        elif st.session_state.aq_pagina == "mensal":
            evolucao_mensal(lote)
        else:
            visao_geral(lote)
except psycopg.Error as erro:
    st.error(f"Falha na consulta ao Supabase ({type(erro).__name__}). Verifique a conexão e o SQL de instalação.")
    st.stop()
