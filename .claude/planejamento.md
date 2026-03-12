Plan to implement                                                                                                    │
│                                                                                                                      │
│ Plano de Deploy na Railway                                                                                           │
│                                                                                                                      │
│ Contexto                                                                                                             │
│                                                                                                                      │
│ O projeto é um dashboard Streamlit que monitora batidas de ponto via API EzPoint. Hoje roda localmente sem nenhuma   │
│ configuração de deploy. O objetivo é publicar na Railway com:                                                        │
│ - Segurança total do .env — credenciais nunca no repositório git                                                     │
│ - Banco bootstrap — SQLite sobe vazio no servidor; tabelas criadas pelo init_db.py na primeira inicialização; admin  │
│ semeado pelo auth.py (ensure_usuarios_table) no primeiro acesso                                                      │
│ - Persistência do SQLite via Railway Volume (evita perda de dados a cada redeploy)                                   │
│                                                                                                                      │
│ ---                                                                                                                  │
│ Arquivos a criar / modificar                                                                                         │
│                                                                                                                      │
│ ┌──────────────┬───────────┬──────────────────────────────────────────────────────────────┐                          │
│ │   Arquivo    │   Ação    │                            Motivo                            │                          │
│ ├──────────────┼───────────┼──────────────────────────────────────────────────────────────┤                          │
│ │ railway.toml │ Criar     │ Config oficial Railway (build + deploy command)              │                          │
│ ├──────────────┼───────────┼──────────────────────────────────────────────────────────────┤                          │
│ │ start.sh     │ Criar     │ Script de boot: inicializa DB → sobe Streamlit               │                          │
│ ├──────────────┼───────────┼──────────────────────────────────────────────────────────────┤                          │
│ │ .env.example │ Criar     │ Template sem segredos para documentar variáveis obrigatórias │                          │
│ ├──────────────┼───────────┼──────────────────────────────────────────────────────────────┤                          │
│ │ db.py        │ Modificar │ Tornar DB_PATH configurável via env var DB_PATH              │                          │
│ ├──────────────┼───────────┼──────────────────────────────────────────────────────────────┤                          │
│ │ .gitignore   │ Verificar │ data/ e .env já estão ignorados — confirmar e manter         │                          │
│ └──────────────┴───────────┴──────────────────────────────────────────────────────────────┘                          │
│                                                                                                                      │
│ ---                                                                                                                  │
│ Implementação detalhada                                                                                              │
│                                                                                                                      │
│ 1. db.py — caminho do banco via variável de ambiente                                                                 │
│                                                                                                                      │
│ import os, sqlite3                                                                                                   │
│ from pathlib import Path                                                                                             │
│                                                                                                                      │
│ DB_PATH = Path(os.getenv("DB_PATH", "data/ezpoint.db"))                                                              │
│                                                                                                                      │
│ def get_con():                                                                                                       │
│     DB_PATH.parent.mkdir(parents=True, exist_ok=True)                                                                │
│     con = sqlite3.connect(DB_PATH)                                                                                   │
│     con.execute("PRAGMA foreign_keys = ON;")                                                                         │
│     return con                                                                                                       │
│                                                                                                                      │
│ Na Railway define-se DB_PATH=/mnt/data/ezpoint.db (Volume montado em /mnt/data).                                     │
│ Localmente continua usando data/ezpoint.db sem alterar nada.                                                         │
│                                                                                                                      │
│ ---                                                                                                                  │
│ 2. start.sh — bootstrap + startup                                                                                    │
│                                                                                                                      │
│ #!/bin/bash                                                                                                          │
│ set -e                                                                                                               │
│                                                                                                                      │
│ echo "==> Inicializando banco de dados..."                                                                           │
│ python init_db.py                                                                                                    │
│                                                                                                                      │
│ echo "==> Iniciando Streamlit..."                                                                                    │
│ exec streamlit run app.py \                                                                                          │
│   --server.port "${PORT:-8501}" \                                                                                    │
│   --server.address "0.0.0.0" \                                                                                       │
│   --server.headless true \                                                                                           │
│   --server.enableCORS false \                                                                                        │
│   --server.enableXsrfProtection true                                                                                 │
│                                                                                                                      │
│ - python init_db.py cria todas as tabelas a partir do schema.sql se ainda não existirem (idempotente — usa CREATE    │
│ TABLE IF NOT EXISTS)                                                                                                 │
│ - auth.py:ensure_usuarios_table() semeia o admin automaticamente no primeiro acesso à página                         │
│ - O --server.headless true é obrigatório para Streamlit em produção sem browser                                      │
│                                                                                                                      │
│ ---                                                                                                                  │
│ 3. railway.toml                                                                                                      │
│                                                                                                                      │
│ [build]                                                                                                              │
│ builder = "nixpacks"                                                                                                 │
│                                                                                                                      │
│ [deploy]                                                                                                             │
│ startCommand = "bash start.sh"                                                                                       │
│ healthcheckPath = "/_stcore/health"                                                                                  │
│ healthcheckTimeout = 60                                                                                              │
│ restartPolicyType = "on_failure"                                                                                     │
│ restartPolicyMaxRetries = 3                                                                                          │
│                                                                                                                      │
│ ---                                                                                                                  │
│ 4. .env.example — template sem segredos                                                                              │
│                                                                                                                      │
│ # EzPoint API                                                                                                        │
│ EZPOINT_EMPRESA=                                                                                                     │
│ EZPOINT_USUARIO=                                                                                                     │
│ EZPOINT_SENHA=                                                                                                       │
│                                                                                                                      │
│ # Tolerâncias (minutos)                                                                                              │
│ TOL_MIN=10                                                                                                           │
│ INTERVAL_TOL_MIN=10                                                                                                  │
│                                                                                                                      │
│ # Dashboard                                                                                                          │
│ AUTO_REFRESH_SEC=30                                                                                                  │
│                                                                                                                      │
│ # SMTP                                                                                                               │
│ SMTP_HOST=                                                                                                           │
│ SMTP_PORT=587                                                                                                        │
│ SMTP_USUARIO=                                                                                                        │
│ SMTP_SENHA=                                                                                                          │
│ EMAIL_REMETENTE_NOME=Dashboard Ponto                                                                                 │
│ EMAIL_ASSUNTO=Relatório Diário de Apontamentos                                                                       │
│                                                                                                                      │
│ # Autenticação                                                                                                       │
│ ADMIN_EMAIL=           # e-mail do usuário admin inicial                                                             │
│ AUTH_COOKIE_SECRET=    # gerar com: python -c "import secrets; print(secrets.token_hex(32))"                         │
│                                                                                                                      │
│ # Banco (Railway Volume)                                                                                             │
│ DB_PATH=/mnt/data/ezpoint.db                                                                                         │
│                                                                                                                      │
│ ---                                                                                                                  │
│ Configuração no painel da Railway (passo a passo)                                                                    │
│                                                                                                                      │
│ A) Criar o projeto                                                                                                   │
│                                                                                                                      │
│ 1. Railway → New Project → Deploy from GitHub repo → selecionar dashrw                                               │
│ 2. Railway detecta Python/Nixpacks automaticamente                                                                   │
│                                                                                                                      │
│ B) Adicionar Volume para persistência do SQLite                                                                      │
│                                                                                                                      │
│ 1. No projeto → Add Volume                                                                                           │
│ 2. Mount path: /mnt/data                                                                                             │
│ 3. Isso persiste o arquivo ezpoint.db entre redeploys e reinicializações                                             │
│                                                                                                                      │
│ C) Definir variáveis de ambiente                                                                                     │
│                                                                                                                      │
│ No painel Railway → Variables → adicionar todas as variáveis do .env.example:                                        │
│ - Copiar valores do .env local                                                                                       │
│ - DB_PATH → /mnt/data/ezpoint.db                                                                                     │
│ - AUTH_COOKIE_SECRET → gerar novo valor com o comando do .env.example                                                │
│ - ADMIN_EMAIL → e-mail real do administrador                                                                         │
│                                                                                                                      │
│ Nunca commitar o .env real — o .gitignore já o exclui.                                                               │
│                                                                                                                      │
│ D) Deploy                                                                                                            │
│                                                                                                                      │
│ - Railway faz build automático a cada push na branch main                                                            │
│ - O start.sh executa init_db.py antes de subir o Streamlit                                                           │
│ - No primeiro acesso, ensure_usuarios_table() cria o usuário admin com senha Tecbio2026 e força troca imediata       │
│                                                                                                                      │
│ ---                                                                                                                  │
│ Fluxo de bootstrap do banco (sequência)                                                                              │
│                                                                                                                      │
│ Railway start                                                                                                        │
│   └─> bash start.sh                                                                                                  │
│         └─> python init_db.py       ← cria todas as tabelas (schema.sql)                                             │
│         └─> streamlit run app.py                                                                                     │
│               └─> require_auth()                                                                                     │
│                     └─> ensure_usuarios_table()  ← semeia admin se tabela vazia                                      │
│                                                                                                                      │
│ O banco sobe completamente vazio — nenhum dado de produção local é enviado ao servidor. Após o primeiro login do     │
│ admin (com troca de senha obrigatória), o admin cadastra colaboradores e horários via painel admin                   │
│ (pages/1_admin_app.py) e sincroniza funcionários pela API EzPoint.                                                   │
│                                                                                                                      │
│ ---                                                                                                                  │
│ Verificação pós-deploy                                                                                               │
│                                                                                                                      │
│ 1. Acessar a URL gerada pela Railway → deve exibir tela de login                                                     │
│ 2. Fazer login com admin / Tecbio2026 → deve redirecionar para troca de senha                                        │
│ 3. Após trocar senha → dashboard principal deve carregar                                                             │
│ 4. Acessar /1_admin_app → sincronizar funcionários via botão "Sincronizar da API"                                    │
│ 5. Verificar logs Railway → sem erros de conexão SMTP ou API EzPoint                                                 │
│ 6. Testar auto-refresh (30s) e painel de correções                                                                   │
│                                                                                                                      │
│ ---                                                                                                                  │
│ Segurança — checklist                                                                                                │
│                                                                                                                      │
│ - .env está no .gitignore — nunca vai para o git                                                                     │
│ - Credenciais definidas apenas nas Variables do painel Railway                                                       │
│ - AUTH_COOKIE_SECRET único e gerado aleatoriamente para produção                                                     │
│ - Banco sobe sem dados — sem colaboradores, senhas ou batidas locais                                                 │
│ - Admin inicial força troca de senha no primeiro acesso (primeiro_acesso=1)                                          │
│ - Cookie assinado com itsdangerous (7 dias), idle timeout 30 min                                                     │
│ - Streamlit com enableXsrfProtection true e CORS desabilitado (Railway já provê HTTPS)                               │
╰─────────────────────