# ÁQUILA V12 — caixas de seleção e alinhamento dos rankings

Esta atualização parte da **V11 de filtros interativos**.

## Instalação

Substitua `app.py` e `aquila_visual.py` no projeto `C:\Users\anthony.silva\Documents\PROJETO_AQUILA`.
Mantenha `filtros_interativos.py`, `aquila_runtime.py`, os módulos de ROB, importadores e `.streamlit/secrets.toml` da V11.

Reinicie pelo PowerShell:

```powershell
cd 'C:\Users\anthony.silva\Documents\PROJETO_AQUILA'
.venv\Scripts\python.exe -m streamlit run app.py
```

Não é necessária migração SQL nem alteração de credenciais.

## Alterações

- Retirada a coluna de lupa (`⌕`) das três tabelas interativas: motivos, CSC × Loja e produtos.
- A caixa de seleção que o Streamlit mostra nativamente continua disponível.
- Ranking de fiscais e produtos com título, grade e rodapé alinhados: grade de dez linhas com altura coerente e rodapés com 45px.
- Texto instrutivo abaixo da tabela de produtos removido, preservando o alinhamento vertical dos painéis.
- Não foram alteradas as consultas SQL, o cálculo da ROB, a meta, as conexões ou os filtros cruzados.

## Validação

Sintaxe Python e testes de filtros podem ser executados localmente. Ainda é necessária validação visual no navegador, pois o componente de tabela do Streamlit possui renderização própria.
