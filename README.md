# Monitor PNCP x DSPACE: 15ª Cia Inf Mtz

De **segunda a sexta, às 11h00 e 16h00 (Brasília)**, o GitHub Actions
(não roda aos sábados e domingos):

1. abre o painel [PNCP x DSPACE 2026](https://datastudio.google.com/u/0/reporting/71a1b697-4dd9-428d-ba8c-c2f02491324a/page/p_n01n3pu72d);
2. filtra a UGA **15ª Cia Inf Mtz** e lê todos os processos da OM;
3. separa os que estão **NÃO ENCONTRADO** no DSPACE (na falta);
4. salva a consulta em `docs/historico.json` (histórico completo);
5. envia um e-mail para **conf15companhia@gmail.com** **somente quando houver divergência**
   (processo na falta). Sem divergência, nenhum e-mail é enviado.

O histórico fica visível em `docs/index.html` (página do GitHub Pages).

## Arquivos

| Arquivo | Função |
|---|---|
| `monitor.py` | Raspagem do painel, histórico e e-mail |
| `.github/workflows/monitor.yml` | Agendamento 11h/16h na nuvem |
| `docs/index.html` | Página com última consulta e histórico |
| `docs/historico.json` / `historico.js` | Dados de todas as consultas (atualizados pelo robô) |

## Instalação (uma vez só)

### 1. Senha de app do Gmail (conf15companhia@gmail.com)
1. Entre em <https://myaccount.google.com/security> com conf15companhia@gmail.com
   e ative a **Verificação em duas etapas** (se ainda não estiver ativa).
2. Abra <https://myaccount.google.com/apppasswords>, crie uma senha de app
   (nome: "Monitor PNCP") e copie os 16 caracteres.

### 2. Repositório no GitHub
1. Crie uma conta em <https://github.com> (se não tiver) e um repositório novo,
   por exemplo `monitor-pncp-dspace`, **vazio** (sem README).
   - **Público**: GitHub Pages grátis para ver o histórico. Os dados são públicos de qualquer forma (PNCP).
   - **Privado**: funciona igual, mas a página do histórico exige plano pago.
     Nesse caso, veja o histórico abrindo `docs/historico.json` no próprio GitHub.
2. Envie esta pasta (no terminal, dentro da pasta do projeto):
   ```bash
   git add .
   git commit -m "Monitor PNCP x DSPACE"
   git remote add origin https://github.com/SEU_USUARIO/monitor-pncp-dspace.git
   git push -u origin main
   ```

### 3. Segredos (Settings → Secrets and variables → Actions → New repository secret)
| Nome | Valor |
|---|---|
| `GMAIL_USER` | `conf15companhia@gmail.com` |
| `GMAIL_APP_PASSWORD` | a senha de app de 16 caracteres |

Opcional, na aba **Variables**: `EMAIL_TO` (outros destinatários, separados por vírgula)
e `OM_NOME` (para monitorar outra UGA, com o nome exatamente como aparece no painel).

### 4. Permissão de escrita e página do histórico
- **Settings → Actions → General → Workflow permissions** → marque *Read and write permissions*.
- **Settings → Pages** → *Deploy from a branch* → branch `main`, pasta `/docs`.
  A página fica em `https://SEU_USUARIO.github.io/monitor-pncp-dspace/`.

### 5. Teste
Aba **Actions** → *Monitor PNCP x DSPACE* → **Run workflow**. Em 2 a 3 minutos o e-mail
chega (se houver falta) e o histórico ganha uma linha.

## Observações
- O GitHub pode atrasar disparos agendados em alguns minutos (às vezes até ~30 min).
- O robô tenta 3 vezes antes de registrar erro. Se o painel mudar de layout, a consulta
  falha e a linha aparece como **Erro** no histórico. Não há e-mail do robô nesse caso,
  mas o GitHub avisa o dono do repositório por e-mail quando uma execução falha.
- O botão **Run workflow** roda a qualquer dia, inclusive no fim de semana (é manual).
- Rodar no próprio PC: `pip install -r requirements.txt`, `python -m playwright install chromium`,
  defina `GMAIL_USER` e `GMAIL_APP_PASSWORD` no ambiente e rode `python monitor.py`.
