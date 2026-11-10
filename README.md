# Escalabilidade

Consulte [ESCALA.md](ESCALA.md) para as otimizações, limites do banco, execução
com quatro processos, implantação Docker/Nginx e instruções de teste de carga.
Os testes locais completaram 100 sessões de painel, mas ainda registraram
latência alta e timeouts de saúde; a capacidade em produção precisa de validação.

# ÁQUILA V5 — Ajustes da Visão Geral

## Alterações solicitadas

- **Ranking compacto:** só as colunas **Loja** e **% Desc / Receita** aparecem inicialmente. No botão **Exibir mais colunas**, o usuário pode adicionar individualmente Posição, Valor rebaixado, % do total, Receita bruta e vs. média rede.
- **Histórico mensal à direita do ranking:** gráfico de barras com valores das rebaixas em reais. Um único filtro de loja mostra apenas essa unidade; múltiplas lojas somam os valores delas, e nenhuma loja selecionada mostra a rede inteira.
- **Escopo histórico:** respeita o ano e origem aplicados. Ignora apenas o filtro **Mês**, pois esse filtro reduziria o gráfico a uma barra. Exibe somente meses com registros na base (sem preencher meses ausentes com valores inventados).
- **Light/Dark:** os elementos internos de `selectbox`, `multiselect`, `input`, `number_input` e o controle de ordenação usam contraste consistente, inclusive campos e opções de popover.
- **Preservações:** Supabase, importações de descontos e ROB com substituição integral, histórico de metas, login administrativo provisório, cache e pool de conexões; **nenhuma migração SQL**.

## Instalação

Na pasta `C:\Users\anthony.silva\Documents\PROJETO_AQUILA`, copie **três arquivos da V5**: `app.py`, `aquila_visual.py` e `ranking_compacto.py` (novo). Não substitua o seu `secrets.toml` nem altere os dados no Supabase. Mantenha os módulos `ingestao.py`, `rob_ingestao.py`, `rob_metricas.py` e os demais arquivos existentes.

```powershell
cd "C:\Users\anthony.silva\Documents\PROJETO_AQUILA"
python -m streamlit run app.py
```

Verifique no modo escuro os campos Ano, Mês, Lojas, Origem e a ordenação; há variações de markup entre versões do Streamlit, então um teste visual no navegador é necessário. A aplicação ainda não foi executada com seu Supabase real.

---

# ÁQUILA V5 — Ranking compacto, histórico mensal e contraste Light/Dark

Esta versão **parte do `app.py` e `aquila_visual.py` mais recentes enviados** pelo projeto local, preservando a tela de login em duas colunas, temas claro/escuro, navegação com barras e ícones, cache e pool PostgreSQL, filtros com Aplicar e abas inativas sem consultas.

## Novidades

- Nova aba **Administração → Importação ROB** para carregar o Excel contendo `BASE / Loja / Vlr Venda Atual / Ano/Mês`.
- Cada upload válido substitui **integralmente apenas a ROB** no Supabase. Os dados de desconto, as metas e suas auditorias são independentes.
- Uma carga incompleta ou inválida preserva a ROB anterior. A ativação ocorre em transação no PostgreSQL.
- Conciliação **por código de loja de três dígitos + mês**, sem repetir a receita por transação/cupom; os códigos do nome da loja, por exemplo `001-CARPINA`, identificam a unidade.
- KPIs dinâmicos de **receita bruta conciliada**, **desconto/ROB (%)**, **teto financeiro da meta** e **oportunidade de redução**.
- Top 10 de lojas agora mostra ROB, percentual da ROB e variação contra média dinâmica da seleção.
- Gráfico de oportunidade em percentuais com linha da **meta ponderada pela receita**.
- Evolução mensal mostra valores realizados, limite financeiro pela meta **válida em cada mês**, ROB e oportunidades, somadas somente quando cada loja/mês excede seu próprio limite (uma loja abaixo da meta não compensa outra).
- Lojas/mês sem receita ou com receita `<= 0` são mostradas como pendências; o percentual agregado afetado fica indisponível (`—`), em vez de apresentar um resultado incorreto.

## Instalação no Supabase — passo obrigatório

1. Confirme que o SQL original `sql/001_schema.sql` já foi executado.
2. No projeto Supabase correto, abra **SQL Editor → New query**.
3. Cole todo o conteúdo de **`sql/002_rob.sql`** e execute **uma vez**. É uma migração aditiva que cria as tabelas `rob_lotes`, `rob_receitas`, `rob_config`, a view `rob_receitas_atuais` e a função `rob_ativar_lote`.
4. Verifique `Success. No rows returned`.

**Não execute** `sql/001_schema.sql` novamente para integrar a ROB. O script `002_rob.sql` não exclui nem atualiza dados de descontos. Após a publicação, exclusivamente as versões anteriores da ROB são apagadas.

## Atualização local

No Windows, mantenha **intactos** seus `.streamlit/secrets.toml`, `.venv`, `.git`, `sql/001_schema.sql` personalizado e `ingestao.py` local, caso tenha alterações próprias.

Copie para `C:\Users\anthony.silva\Documents\PROJETO_AQUILA`:

- `app.py` — atualizado a partir da versão mais recente que você enviou
- `rob_ingestao.py` — novo
- `rob_metricas.py` — novo
- `aquila_visual.py` — arquivo mais recente enviado por você, incluído para referência
- `requirements.txt` — versão mais recente enviada por você
- `sql/002_rob.sql` — novo

No PowerShell, com o ambiente ativado:

```powershell
cd "C:\Users\anthony.silva\Documents\PROJETO_AQUILA"
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Para publicar a receita: **Administração → Importação ROB → Escolher arquivo → Confirmar → Validar, importar e publicar ROB**. Carregue o arquivo `ROB Jan-nov.xlsx` fornecido por você. Não adicione esse arquivo de dados ao repositório Git, salvo se houver autorização corporativa.

## Interpretação e atenção aos dados

- A planilha recebida tem **791 registros**, **78 identificações de unidades**, meses **2026/01 a 2026/11**, sem duplicatas por código de loja/mês.
- **Há duas ROBs negativas**. O importador preserva os números, mas esses itens não são usados para dividir descontos por receita; o painel sinaliza a insuficiência de cobertura.
- O cabeçalho é **`Vlr Venda Atual`**, tratado como receita bruta operacional (ROB) conforme orientação de negócio. Confirme se a view futura do ERP representa efetivamente a receita bruta antes do uso oficial dos percentuais.
- A ROB de novembro/2026 pode estar **parcial** porque o período ainda não terminou.
- A consulta considera **somente combinações de loja/mês encontradas na base filtrada de descontos**, e usa o valor total da receita da loja/mês como denominador, inclusive quando o filtro de descontos for CSC ou Loja. Não interpreta a receita como sendo apenas do canal.
- Para escopos com alguma loja/mês sem ROB positiva, o KPI de percentual, comparação e teto global não são exibidos; é intencional.
- `0.04` no banco de metas equivale a **0,04%**, logo o teto em reais é `receita × 0.04 / 100`. A meta de novembro muda só em novembro, sem recálculo retroativo das metas de outubro e meses anteriores.
- Os resultados de oportunidades **não são projeções futuras**. São diferenças entre desconto realizado e teto da meta para meses com dados disponíveis.
- Nenhuma credencial do Supabase ou do administrador está incluída no ZIP.
- A RBAC completa por gerente/distrital/diretor ainda não existe; **não publique acesso para outros perfis** até implementar autorização por loja no backend.

## Testes

```powershell
python -m pytest -q
```

Os testes verificam leitura de linhas, interpretação de percentuais, vigência mensal de metas, tratamento de ROB negativa, ausência de ROB, e contrato SQL do JOIN. O banco real do Supabase e o navegador devem ser validados por você; nenhuma credencial nem conexão real foi disponibilizada a esta revisão.
