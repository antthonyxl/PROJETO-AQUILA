"""Regressões de limites e equivalência dos filtros de calendário."""
import ast
import datetime as dt
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from aquila_runtime import configuracao_pool


class EscalaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8'))
        function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'condicoes')
        namespace = {'dt': dt}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'condicoes', 'exec'), namespace)
        cls.condicoes = staticmethod(namespace['condicoes'])

    def test_pool_bounded_and_read_only(self):
        with patch.dict(os.environ, {}, clear=True):
            config = configuracao_pool()
        self.assertEqual(config['max_size'], 8)
        self.assertEqual(config['max_waiting'], 100)
        self.assertTrue(config['kwargs']['autocommit'])
        self.assertIsNone(config['kwargs']['prepare_threshold'])
        self.assertIn('default_transaction_read_only=on', config['kwargs']['options'])
        self.assertIn('statement_timeout=20000', config['kwargs']['options'])

    def test_pool_rejects_invalid_limits(self):
        for value in ['0', '-1', '1000', 'invalid']:
            with self.subTest(value=value), patch.dict(os.environ, {'AQUILA_DB_POOL_MAX': value}):
                with self.assertRaises(ValueError):
                    configuracao_pool()
        with patch.dict(os.environ, {'AQUILA_DB_POOL_MAX': '1'}):
            self.assertEqual(configuracao_pool()['min_size'], 1)

    def test_range_matches_previous_year_month_semantics(self):
        for year in [2024, 2026]:
            for month in ['Todos', 1, 2, 11, 12]:
                sql, params = self.condicoes(year, month, (), 'Todos')
                self.assertIn('dta_movimento >= %s', sql)
                self.assertNotIn('EXTRACT', sql)
                lower, upper = params
                date = dt.date(year-1, 12, 30)
                while date < dt.date(year+1, 1, 3):
                    expected = date.year == year and (month == 'Todos' or date.month == month)
                    self.assertEqual(lower <= date < upper, expected, (year, month, date))
                    date += dt.timedelta(days=1)

    def test_all_years_and_other_filters_preserved(self):
        sql, params = self.condicoes('Todos', 11, ('001-LOJA',), 'CSC')
        self.assertIn('EXTRACT(MONTH', sql)
        self.assertIn('empresa = ANY(%s)', sql)
        self.assertIn("POSITION('CSC'", sql)
        self.assertEqual(params, (11, ['001-LOJA']))
        self.assertEqual(self.condicoes('Todos', 'Todos', (), 'Todos'), ('', ()))


if __name__ == '__main__':
    unittest.main()
