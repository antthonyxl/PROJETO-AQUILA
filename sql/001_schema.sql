-- Execute uma vez no SQL Editor do Supabase.
CREATE TABLE IF NOT EXISTS public.pdv_lotes (
    id uuid PRIMARY KEY,
    nome_arquivo text NOT NULL,
    status text NOT NULL DEFAULT 'carregando' CHECK (status IN ('carregando','ativo','substituido','falhou')),
    linhas integer NOT NULL DEFAULT 0,
    criado_em timestamptz NOT NULL DEFAULT now(),
    ativado_em timestamptz
);

CREATE TABLE IF NOT EXISTS public.pdv_descontos (
    lote_id uuid NOT NULL REFERENCES public.pdv_lotes(id) ON DELETE CASCADE,
    linha_excel integer NOT NULL,
    empresa text,
    dta_movimento date,
    hora_emissao time,
    segmento text,
    seqpessoa text,
    cliente text,
    cnpjcpf text,
    caixa text,
    turno text,
    cupom_coo text,
    cod_produto text,
    cod_ean text,
    produto text,
    quantidade numeric,
    qtd_emb numeric,
    vlrunitario numeric,
    vlrtotal numeric,
    vlr_desconto numeric,
    cod_operador text,
    op_caixa text,
    cod_fiscal text,
    fiscal_cx text,
    nro_doc text,
    status text,
    tipo text,
    motivo text,
    tipo_desconto text,
    PRIMARY KEY (lote_id, linha_excel)
);
CREATE INDEX IF NOT EXISTS pdv_descontos_lote_empresa_idx ON public.pdv_descontos(lote_id, empresa);
CREATE INDEX IF NOT EXISTS pdv_descontos_lote_data_idx ON public.pdv_descontos(lote_id, dta_movimento);
CREATE INDEX IF NOT EXISTS pdv_descontos_lote_fiscal_idx ON public.pdv_descontos(lote_id, fiscal_cx);

CREATE TABLE IF NOT EXISTS public.pdv_config (
    chave text PRIMARY KEY,
    lote_ativo uuid REFERENCES public.pdv_lotes(id) DEFERRABLE INITIALLY DEFERRED
);
INSERT INTO public.pdv_config(chave, lote_ativo) VALUES ('descontos', NULL)
ON CONFLICT (chave) DO NOTHING;

-- Cada meta vale desde o primeiro dia do seu mês de vigência até uma nova alteração.
CREATE TABLE IF NOT EXISTS public.pdv_metas (
    mes_vigencia date PRIMARY KEY,
    percentual numeric(10,5) NOT NULL CHECK (percentual >= 0 AND percentual <= 100),
    alterado_por text NOT NULL,
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CHECK (mes_vigencia = date_trunc('month', mes_vigencia)::date)
);
CREATE TABLE IF NOT EXISTS public.pdv_auditoria_metas (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mes_vigencia date NOT NULL,
    percentual_anterior numeric(10,5),
    percentual_novo numeric(10,5) NOT NULL,
    alterado_por text NOT NULL,
    criado_em timestamptz NOT NULL DEFAULT now()
);
-- Valor inicial será aplicado enquanto não houver alteração posterior.
INSERT INTO public.pdv_metas(mes_vigencia, percentual, alterado_por)
VALUES ('2026-01-01', 0.04, 'sistema') ON CONFLICT (mes_vigencia) DO NOTHING;

-- A troca para um novo lote é atômica: se ocorrer erro, o lote anterior permanece ativo.
-- A exclusão dos dados antigos ocorre na mesma transação.
CREATE OR REPLACE FUNCTION public.pdv_ativar_lote(p_lote uuid)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE v_qtd integer; v_antigo uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(20261109, 1);
    SELECT COUNT(*) INTO v_qtd FROM public.pdv_descontos WHERE lote_id = p_lote;
    IF v_qtd = 0 THEN RAISE EXCEPTION 'Lote vazio; base atual preservada'; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.pdv_lotes WHERE id = p_lote AND status = 'carregando') THEN
      RAISE EXCEPTION 'Lote inexistente ou já finalizado';
    END IF;
    SELECT lote_ativo INTO v_antigo FROM public.pdv_config WHERE chave='descontos' FOR UPDATE;
    UPDATE public.pdv_config SET lote_ativo = p_lote WHERE chave='descontos';
    UPDATE public.pdv_lotes SET status='ativo', linhas=v_qtd, ativado_em=now() WHERE id=p_lote;
    -- Remove TODOS os lotes antigos e seus dados por CASCADE; só ficam os registros novos.
    DELETE FROM public.pdv_lotes WHERE id <> p_lote;
END $$;

CREATE OR REPLACE VIEW public.pdv_descontos_atuais WITH (security_invoker=true) AS
SELECT d.* FROM public.pdv_descontos d
JOIN public.pdv_config c ON c.chave='descontos' AND c.lote_ativo=d.lote_id;

-- Finaliza verificações de FK adiadas antes de ALTER TABLE/RLS na mesma transação.
SET CONSTRAINTS ALL IMMEDIATE;

-- Segurança: não expor as tabelas diretamente pela API pública do Supabase.
ALTER TABLE public.pdv_lotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pdv_descontos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pdv_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pdv_metas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pdv_auditoria_metas ENABLE ROW LEVEL SECURITY;
-- O app acessa pelo PostgreSQL com credencial de backend guardada em secrets.

-- Não permitir uso da função de publicação ou leitura do esquema pela API anon/autenticada.
REVOKE ALL ON FUNCTION public.pdv_ativar_lote(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.pdv_lotes, public.pdv_descontos, public.pdv_config,
    public.pdv_metas, public.pdv_auditoria_metas, public.pdv_descontos_atuais
    FROM PUBLIC, anon, authenticated;
