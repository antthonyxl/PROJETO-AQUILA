-- Execute no SQL Editor do Supabase para separar privilégios (menor privilégio).
-- Substitua as senhas fortes antes de executar em produção e atualize secrets.toml.

-- 1. Role de leitura para consultas do dashboard (SUPABASE_DB_READONLY_URL).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aquila_leitura') THEN
        CREATE ROLE aquila_leitura LOGIN PASSWORD 'SUBSTITUA_POR_SENHA_FORTE_LEITURA'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END $$;

REVOKE ALL ON SCHEMA public FROM aquila_leitura;
GRANT USAGE ON SCHEMA public TO aquila_leitura;
GRANT SELECT ON public.pdv_lotes, public.pdv_descontos, public.pdv_config,
    public.pdv_metas, public.pdv_auditoria_metas, public.pdv_descontos_atuais,
    public.rob_lotes, public.rob_receitas, public.rob_config,
    public.rob_receitas_atuais TO aquila_leitura;

-- 2. Role operacional para ingestão e alteração de metas (SUPABASE_DB_URL), sem DDL.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aquila_escrita') THEN
        CREATE ROLE aquila_escrita LOGIN PASSWORD 'SUBSTITUA_POR_SENHA_FORTE_ESCRITA'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END $$;

REVOKE ALL ON SCHEMA public FROM aquila_escrita;
GRANT USAGE ON SCHEMA public TO aquila_escrita;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pdv_lotes, public.pdv_descontos,
    public.pdv_config, public.pdv_metas, public.pdv_auditoria_metas,
    public.rob_lotes, public.rob_receitas, public.rob_config TO aquila_escrita;
GRANT SELECT ON public.pdv_descontos_atuais, public.rob_receitas_atuais TO aquila_escrita;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aquila_escrita;
GRANT EXECUTE ON FUNCTION public.pdv_ativar_lote(uuid), public.rob_ativar_lote(uuid) TO aquila_escrita;
