import unittest
from pathlib import Path

BASE = Path(__file__).parent
APP = (BASE / 'app.py').read_text(encoding='utf-8')
VISUAL = (BASE / 'aquila_visual.py').read_text(encoding='utf-8')

class LayoutV12(unittest.TestCase):
    def test_nao_existe_coluna_de_lupa(self):
        self.assertNotIn('⌕', APP)
        self.assertNotIn('"acao", "', APP)

    def test_tres_tabelas_selecionaveis(self):
        for category in ('"produto"', '"motivo"', '"origem"'):
            self.assertIn(category, APP)
        self.assertIn('selection_mode="single-row"', VISUAL)
        self.assertIn('on_select="rerun"', VISUAL)

    def test_mesma_altura_tabela_10_linhas(self):
        self.assertIn('height:48px;', VISUAL)
        self.assertIn('height:39px;', VISUAL)
        self.assertIn('min-height:45px;', VISUAL)
        self.assertIn('altura=438', APP)

    def test_filtros_preservados(self):
        self.assertIn('condicoes_cruzadas', APP)
        self.assertIn('definir_filtro_da_tabela', APP)

if __name__ == '__main__':
    unittest.main()
