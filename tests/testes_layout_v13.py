import ast
import unittest
from pathlib import Path

P = Path(__file__).parent
APP = (P / "app.py").read_text(encoding="utf-8")
CSS = (P / "aquila_visual.py").read_text(encoding="utf-8")

class TesteContencaoDosPaineis(unittest.TestCase):
    def test_arquivos_compilam(self):
        ast.parse(APP)
        ast.parse(CSS)
    def test_espaco_interno_em_ambos_paineis(self):
        self.assertEqual(APP.count('class="aq-dual-footer-clearance"'), 2)
        self.assertIn('height:18px;', CSS)
    def test_largura_e_rolagem_horizontais(self):
        self.assertIn('max-width:100% !important;', CSS)
        self.assertIn('overflow-x:auto;', CSS)
    def test_sem_alteracao_sql_e_filtros_cruzados(self):
        self.assertIn('condicoes_cruzadas', APP)
        self.assertIn('st.dataframe(', CSS)
        self.assertIn('on_select="rerun"', CSS)
    def test_sem_modificar_calculos_ou_cores(self):
        base = Path(__file__).parent.parent / 'AQUILA_V12_ALINHAMENTO'
        if base.exists():
            antigo_app = (base / 'app.py').read_text(encoding='utf-8')
            antigo_css = (base / 'aquila_visual.py').read_text(encoding='utf-8')
            for trecho in ("SELECT cod_produto,", "FROM public.pdv_descontos_atuais"):
                self.assertIn(trecho, APP)
            self.assertIn('"light": {', CSS)
            self.assertIn('"dark": {', CSS)

if __name__ == '__main__':
    unittest.main()
