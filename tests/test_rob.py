import datetime as dt
from decimal import Decimal
import pytest

from rob_ingestao import converter_linha
from rob_metricas import calc_linhas


def test_rob_leitura_linha_origem():
    codigo, loja, mes, valor = converter_linha(('063-TRAPICHE', 40900000.120, '2026/08'), 2)
    assert (codigo, loja, mes) == ('063','063-TRAPICHE',dt.date(2026,8,1))
    assert valor == Decimal('40900000.12')


def test_valor_negativo_preservado_mas_nao_calculado():
    codigo, loja, mes, valor = converter_linha(('062-ANTARES', -77.22, '2026/01'), 2)
    assert valor == Decimal('-77.22')
    soma = calc_linhas([('062',mes,loja,Decimal('30'),valor)],[(dt.date(2026,1,1),.04)])
    assert soma['total']['percentual'] is None
    assert soma['total']['faltantes'] == 1


def test_rejeita_mes_invalido_e_codigo_nao_padronizado():
    with pytest.raises(ValueError):
        converter_linha(('063-TRAPICHE',120,'2026/13'),2)
    with pytest.raises(ValueError):
        converter_linha(('TRAPICHE',120,'2026/08'),2)


def test_meta_muda_somente_no_mes_de_alteracao_e_rob_nao_duplica():
    meses = [
        ('001',dt.date(2026,10,1),'001-CARPINA', Decimal('100'),Decimal('100000')),
        ('001',dt.date(2026,11,1),'001-CARPINA', Decimal('100'),Decimal('100000')),
    ]
    metas=[(dt.date(2026,1,1),Decimal('.04')),(dt.date(2026,11,1),Decimal('.05'))]
    total=calc_linhas(meses,metas)['total']
    assert total['receita']==Decimal('200000')
    assert total['desconto']==Decimal('200')
    assert total['teto']==Decimal('90') # 40 outubro + 50 novembro
    assert total['percentual']==Decimal('0.1')
    assert total['excesso']==Decimal('110')


def test_sem_rob_invalida_percentual_geral_ao_inves_de_subestimar():
    linhas=[
        ('001',dt.date(2026,10,1),'001-CARPINA',Decimal(100),Decimal(100000)),
        ('002',dt.date(2026,10,1),'002-VIT.SA',Decimal(150),None),
    ]
    resultado=calc_linhas(linhas,[(dt.date(2026,1,1),Decimal('.04'))])
    assert resultado['total']['desconto']==250
    assert resultado['total']['receita']==100000
    assert resultado['total']['percentual'] is None
    assert resultado['lojas']['001']['percentual']==Decimal('0.1')
    assert resultado['lojas']['002']['percentual'] is None


def test_integracao_exige_chave_codigo_mes_e_nao_cupom():
    from pathlib import Path
    codigo = (Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8')
    assert "GROUP BY 1,2" in codigo
    assert 'r.codigo_loja=d.codigo_loja AND r.mes_vigencia=d.mes' in codigo


def test_oportunidade_soma_apenas_excessos_por_loja_mes():
    mes=dt.date(2026,10,1)
    linhas=[
        ('001',mes,'001-CARPINA',Decimal('100'),Decimal('100000')), # teto 40 -> excesso 60
        ('002',mes,'002-VIT.SA',Decimal('10'),Decimal('100000')),  # teto 40 -> abaixo da meta
    ]
    resultado=calc_linhas(linhas,[(dt.date(2026,1,1),Decimal('.04'))])
    assert resultado['total']['desconto']==110
    assert resultado['total']['teto']==80
    assert resultado['total']['excesso']==60  # não 30: loja abaixo da meta não abate excesso de outra
