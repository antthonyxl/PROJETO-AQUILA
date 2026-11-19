# Execução com múltiplos processos

O alvo é 80–100 sessões conectadas. O número de sessões sozinho não define a
capacidade: abertura simultânea, aplicação de filtros, dados em cache, volume do
banco e CPU do servidor mudam os tempos de resposta. Os testes locais não
certificam a infraestrutura de produção.

## Alterações

- O login não importa Plotly nem os importadores Excel. As importações são feitas
  somente depois da autenticação ou ao confirmar uma importação.
- Consultas compartilham cache por processo por até 300 segundos, com limite de
  2.048 entradas. Cálculos e gráficos usam caches de até 512 entradas cada.
  O cache do gráfico inclui os dados e o tema, e reproduz a saída serializada.
- Ano e mês usam um intervalo de datas semiaberto quando há ano selecionado.
  Isso preserva o filtro e permite usar o índice de data já existente. Quando o
  ano é “Todos”, o filtro isolado de mês continua usando EXTRACT.
- O pool de leitura tem até oito conexões por processo, fila limitada e espera
  de até 30 segundos. Consultas têm timeout de 20 segundos. O pool usa autocommit,
  leitura obrigatória e preparação automática desativada. As gravações da
  administração seguem em suas conexões próprias.
- Quatro processos independentes e Nginx distribuem os navegadores por cookie.
  HTTP, WebSocket e uploads do mesmo navegador seguem para o mesmo processo.
  Reiniciar um processo encerra as sessões que estavam nele.

## Inicialização local de um processo

```powershell
.venv\Scripts\python.exe scripts\servir.py --port 8501
```

Esse comando grava a saída em `logs/`, usa logs de aplicação rotativos e desativa
o observador de arquivos. Alterações no código exigem reinício. A saída de console
é um arquivo separado; sua retenção deve ser administrada pelo serviço hospedeiro.
O comando serve apenas um processo, não ativa o balanceador.

## Implantação com Docker Compose

É necessário Docker com Compose no servidor. O Dockerfile usa Python 3.14 e as
dependências fixadas em `requirements.lock`, extraídas do ambiente local testado.
O build Linux, o Nginx e o balanceamento por cookie precisam ser validados no
servidor; não há Docker/Nginx disponível nesta estação de trabalho.

1. Preserve `.streamlit/secrets.toml`. Ele é montado em modo de leitura e não
   entra na imagem. Garanta que o usuário de UID 10001 no contêiner consiga ler
   esse arquivo e o `config.toml`.
2. Preserve o `.env` existente. Em uma instalação nova, crie esse arquivo na
   raiz do projeto com `AQUILA_COOKIE_SECRET=<chave aleatória>` e
   `AQUILA_DB_POOL_MAX=8`, cada variável em sua própria linha. Gere a chave
   com o comando abaixo e conserve a mesma chave nos reinícios. `.env` está
   ignorado pelo Git; não coloque a chave em arquivos versionados.

   ```powershell
   .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Confira no Supabase a disponibilidade de **até 32 conexões de leitura**,
   além das conexões administrativas e de outros sistemas. O limite pode ser
   reduzido por `AQUILA_DB_POOL_MAX`. Aumentar conexões sem medir o banco pode
   piorar o desempenho. Os testes locais usaram oito conexões máximas por processo.
4. Inicie e confira o estado:

   ```powershell
   docker compose up -d --build
   docker compose ps
   docker compose logs --tail 100
   ```

5. Abra `http://localhost:8080`. A porta fica restrita ao host por padrão.
   Integre esse endereço ao proxy HTTPS da infraestrutura para acesso externo.
   Não são publicados os quatro servidores Streamlit diretamente.

   Para acesso externo, configure domínio e certificado no proxy HTTPS do
   mesmo servidor e encaminhe o tráfego para `http://127.0.0.1:8080`.
   Esse proxy deve preservar `Host`, encaminhar os cabeçalhos WebSocket
   `Upgrade` e `Connection`, aceitar uploads de pelo menos 260 MB e usar
   timeout de leitura de pelo menos 300 segundos. Deve também sobrescrever
   `X-Forwarded-Proto` com o protocolo recebido (`https` na conexão TLS),
   sem confiar no cabeçalho enviado pelo cliente. O Nginx interno usa esse
   valor para encaminhar o protocolo e marcar o cookie de afinidade como
   `Secure` em HTTPS. Mantenha a porta 8080 restrita ao loopback; essa
   configuração confia no proxy local. Domínio, certificado e configuração
   do proxy externo ainda precisam ser definidos antes da publicação.

Não é necessário executar migração SQL. Publicar base, ROB ou meta limpa o cache
do processo que recebeu a operação; nos demais, as consultas expiram em até cinco
minutos. Se for necessário publicar alterações instantaneamente em todas as
réplicas, será preciso adicionar invalidação distribuída. As importações e o
login administrativo simultâneo não fazem parte do teste de carga de leitura.

## Repetir os testes

### Resultado da validação local de 09/11/2026

Quatro processos, oito CPUs lógicas disponíveis, banco real em leitura,
100 sessões (25 por processo), duas rodadas, chegada durante 20 segundos:

| Cenário | Sessões concluídas | p95 abertura | p95 após filtrar | Timeouts de saúde |
| --- | --- | --- | --- | --- |
| Cache de gráficos serializados, primeira medição | 100/100 | 13,061 s | 13,781 s | 2 de 124 verificações |
| Repetição com cache aquecido, permanência de 30 s | 100/100 | 13,615 s | 13,415 s | 2 verificações |

Os quatro processos receberam 25 sessões cada. Houve 100 aplicações de filtro
por execução, sem falhas de sessão. Os logs não registraram exceções não tratadas
da aplicação. O teste funcional adicional confirmou navegação para Evolução Mensal
e troca para modo escuro. Os quatro testes de limites e equivalência dos filtros
passaram, assim como as verificações ativas da V10 executadas diretamente.

**A meta de estabilidade ainda não está homologada:** as duas execuções com 100
sessões retornam erro no script por causa dos timeouts de saúde, mesmo completando
todas as páginas. A estação ainda apresenta latência alta. O teste exclui custo
de autenticação, navegador, TLS e Nginx. Esses resultados não autorizam declarar
que o servidor definitivo suporta 100 usuários com resposta rápida.

Os relatórios detalhados estão em `reports/final_100_dashboard_4workers.json`,
`reports/final_100_dashboard_warm.json` e `reports/final_monthly_dark_smoke.json`.
As instâncias temporárias de teste são encerradas ao concluir a validação.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_escala.py -v
.venv\Scripts\python.exe scripts\carga_sessoes.py --url ws://127.0.0.1:8501/_stcore/stream --users 100 --rounds 2 --hold 15 --output reports/login_100.json
```

O segundo comando testa apenas o login. Ele não envia credenciais. Para um painel
já autenticado em ambiente de teste, use `--dashboard --vary-filters`; essa opção
**não autentica** nem modifica o controle de acesso. `--urls` permite distribuir
clientes diretamente entre servidores de teste, mas não testa o Nginx.

Os testes de painel desta revisão usaram uma entrada temporária restrita a
localhost, com sessões previamente autenticadas. Essa entrada é removida depois
do teste e não faz parte da implantação. O pool de leitura foi usado com o banco
real, sem importações nem atualização de metas. O teste verifica o recebimento
dos gráficos no protocolo Streamlit, não a renderização visual em 100 navegadores.

`--ramp-seconds 20` distribui a chegada durante 20 segundos. Sem essa opção,
as conexões são abertas em rajada. O relatório informa o pico efetivamente
conectado, sucesso por sessão, percentis por rodada e falhas da verificação de
saúde. Qualquer sessão malsucedida ou timeout de saúde faz o novo script retornar
código de erro. `scripts/teste_carga.py` é o teste inicial mais simples; use
`carga_sessoes.py` para novas medições.

Antes de liberar o tráfego, repita no servidor definitivo pelo endereço do proxy:
verifique login, manutenção do cookie, reconexão WebSocket, filtros e erros no
banco. Aumente CPU ou distribua os processos por máquinas se os tempos continuarem
altos. O login administrativo existente permanece; este trabalho não cria
perfis individuais nem autorização por loja.
