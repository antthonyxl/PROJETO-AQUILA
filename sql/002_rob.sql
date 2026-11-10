-- ÁQUILA V4: ROB (receita bruta por loja/mês).
-- Execute no SQL Editor DO MESMO projeto Supabase após 001_schema.sql.
-- Não altera nem exclui dados de pdv_descontos, pdv_metas ou usuários.

CREATE TABLE IF NOT EXISTS public.rob_lotes (
    id uuid PRIMARY KEY,
    nome_arquivo text NOT NULL,
    status text NOT NULL DEFAULT 'carregando'
        CHECK (status IN ('carregando', 'ativo', 'substituido', 'falhou')),
    linhas integer NOT NULL DEFAULT 0,
    criado_em timestamptz NOT NULL DEFAULT now(),
    ativado_em timestamptz
);

CREATE TABLE IF NOT EXISTS public.rob_receitas (
    lote_id uuid NOT NULL REFERENCES public.rob_lotes(id) ON DELETE CASCADE,
    codigo_loja varchar(3) NOT NULL CHECK (codigo_loja ~ '^[0-9]{3}$'),
    loja text NOT NULL,
    mes_vigencia date NOT NULL,
    receita_bruta numeric(20,2) NOT NULL,
    linha_excel integer NOT NULL,
    PRIMARY KEY (lote_id, codigo_loja, mes_vigencia),
    CONSTRAINT rob_mes_primeiro_dia CHECK (mes_vigencia = date_trunc('month',mes_vigencia)::date)
);
CREATE INDEX IF NOT EXISTS rob_receitas_mes_idx
    ON public.rob_receitas(lote_id, mes_vigencia);

CREATE TABLE IF NOT EXISTS public.rob_config (
    chave text PRIMARY KEY,
    lote_ativo uuid REFERENCES public.rob_lotes(id)
);
INSERT INTO public.rob_config(chave,lote_ativo) VALUES ('rob',NULL)
ON CONFLICT (chave) DO NOTHING;

CREATE OR REPLACE FUNCTION public.rob_ativar_lote(p_lote uuid)
RETURNS void LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_qtd integer;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(20261109, 2);
    SELECT COUNT(*) INTO v_qtd FROM public.rob_receitas WHERE lote_id=p_lote;
    IF v_qtd=0 THEN RAISE EXCEPTION 'ROB vazia; base anterior preservada'; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.rob_lotes WHERE id=p_lote AND status='carregando') THEN
        RAISE EXCEPTION 'Lote ROB inexistente ou finalizado';
    END IF;
    PERFORM 1 FROM public.rob_config WHERE chave='rob' FOR UPDATE;
    UPDATE public.rob_config SET lote_ativo=p_lote WHERE chave='rob';
    UPDATE public.rob_lotes SET status='ativo', linhas=v_qtd, ativado_em=now() WHERE id=p_lote;
    -- Exclusão atômica exclusivamente de lotes ROB anteriores; nunca dos descontos.
    DELETE FROM public.rob_lotes WHERE id<>p_lote AND status='ativo';
END $$;

CREATE OR REPLACE VIEW public.rob_receitas_atuais
WITH (security_invoker=true) AS
SELECT r.codigo_loja, r.loja, r.mes_vigencia, r.receita_bruta
FROM public.rob_receitas r
JOIN public.rob_config c ON c.chave='rob' AND c.lote_ativo=r.lote_id;

-- Segurança: API pública do Supabase não deve ler dados corporativos.
SET CONSTRAINTS ALL IMMEDIATE;
ALTER TABLE public.rob_lotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rob_receitas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rob_config ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON FUNCTION public.rob_ativar_lote(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.rob_lotes, public.rob_receitas, public.rob_config,
    public.rob_receitas_atuais FROM PUBLIC, anon, authenticated;
