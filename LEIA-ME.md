# Projeto ÁQUILA — V19 | Correção pontual de alinhamento

Esta versão parte do `app.py` da V17 e do `aquila_visual.py` da V18, que era a combinação mais recente: a V18 alterou somente o arquivo visual.

## Alterações

- **Checkboxes:** deslocamento horizontal de 11 px dentro da primeira coluna de 40 px, mantendo os componentes nativos e callbacks existentes. O passo vertical agora é de 39 px, igual à altura das linhas.
- **Ranking de produtos:** o totalizador foi incorporado ao `tfoot` da mesma tabela HTML. Isso elimina o segundo bloco de rodapé que era renderizado separadamente e causava desalinhamento em relação à tabela de fiscais.
- **Alturas:** cabeçalhos de 48 px, dez linhas de 39 px e totalizadores de 45 px nos dois rankings. Nenhuma alteração nas consultas ou no cálculo dos totais.

## Como atualizar

1. Faça backup dos arquivos `app.py` e `aquila_visual.py` em `C:\Users\anthony.silva\Documents\PROJETO_AQUILA`.
2. Copie os dois arquivos deste pacote para a raiz da mesma pasta.
3. Não substitua `.streamlit/secrets.toml`, `aquila_runtime.py`, módulos ROB, filtros ou outros arquivos.
4. Reinicie o Streamlit:

```powershell
python -m streamlit run app.py
```

Se necessário, use `Ctrl + Shift + R` no navegador para recarregar os estilos.

## Validação

- Sintaxe Python: aprovada.
- Testes de estrutura: 10 produtos, 8 motivos e 2 origens; 20 checkboxes e seus estados/callbacks preservados.
- Prévia isolada no Chromium em Light e Dark: centro do checkbox coincidiu com o centro da coluna (diferença < 2 px), e topo dos dois totalizadores ficou na mesma coordenada (`y=550`).
- **Ainda não validado:** a renderização dentro do Streamlit real e o comportamento em tela estreita com rolagem horizontal. A prévia simula a estrutura DOM, não substitui a validação no localhost.
