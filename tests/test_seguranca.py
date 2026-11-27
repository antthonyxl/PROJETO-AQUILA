"""Testes de regressão de segurança para autenticação, sessão e Excel."""
import hashlib
import os
import sys
import tomllib
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aquila_seguranca import (
    ControladorTentativasLogin,
    MAX_BYTES_UPLOAD_XLSX,
    autenticar_admin,
    encerrar_sessao,
    iniciar_sessao,
    obter_ip_cliente,
    sanitizar_celula_excel,
    salvar_upload_xlsx_temporario,
    sessao_valida,
    validar_arquivo_xlsx,
    verificar_senha,
)


def _gerar_hash(senha: str) -> str:
    salt = b"\x01" * 16
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, 600_000)
    return f"{salt.hex()}:{digest.hex()}"


def _criar_xlsx_minimo(caminho: Path, extras: dict[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(caminho, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types></Types>")
        zf.writestr("xl/workbook.xml", b"<workbook></workbook>")
        for nome, conteudo in (extras or {}).items():
            zf.writestr(nome, conteudo)


class SegurancaTests(unittest.TestCase):
    def test_autenticar_admin_aceita_nao_ascii_sem_crash(self):
        armazenado = _gerar_hash("SenhaForte123!")
        self.assertFalse(autenticar_admin("usuário_ç_á", "SenhaForte123!", "novo_admin", armazenado))
        self.assertTrue(autenticar_admin(" novo_admin ", "SenhaForte123!", "novo_admin", armazenado))
        self.assertFalse(autenticar_admin("novo_admin", "errada", "novo_admin", armazenado))

    def test_verificar_senha_rejeita_formato_invalido(self):
        self.assertFalse(verificar_senha("abc", "formato_invalido"))
        self.assertFalse(verificar_senha("abc", ":"))

    def test_rate_limit_bloqueia_forca_bruta_e_reseta_no_sucesso(self):
        ctrl = ControladorTentativasLogin(max_tentativas_chave=3, max_tentativas_ip=6, janela_segundos=300, bloqueio_base_segundos=60)
        self.assertEqual(ctrl.segundos_bloqueado("10.0.0.1", "admin", agora=100.0), 0)
        self.assertEqual(ctrl.registrar_falha("10.0.0.1", "admin", agora=101.0), 0)
        self.assertEqual(ctrl.registrar_falha("10.0.0.1", "admin", agora=102.0), 0)
        self.assertEqual(ctrl.registrar_falha("10.0.0.1", "admin", agora=103.0), 60)
        self.assertGreater(ctrl.segundos_bloqueado("10.0.0.1", "admin", agora=110.0), 0)
        ctrl.registrar_sucesso("10.0.0.1", "admin")
        self.assertEqual(ctrl.segundos_bloqueado("10.0.0.1", "admin", agora=111.0), 0)

    def test_sessao_expira_por_inatividade_e_tempo_maximo(self):
        estado = {}
        with patch.dict(os.environ, {"AQUILA_SESSION_IDLE_SECONDS": "60", "AQUILA_SESSION_MAX_SECONDS": "300"}):
            iniciar_sessao(estado, agora=1000.0)
            self.assertTrue(sessao_valida(estado, agora=1030.0))
            self.assertFalse(sessao_valida(estado, agora=1100.0))
            self.assertFalse(estado["admin_ok"])

            iniciar_sessao(estado, agora=2000.0)
            self.assertTrue(sessao_valida(estado, agora=2050.0))
            self.assertTrue(sessao_valida(estado, agora=2100.0))
            self.assertFalse(sessao_valida(estado, agora=2301.0))
            encerrar_sessao(estado)
            self.assertFalse(estado["admin_ok"])

    def test_obter_ip_cliente(self):
        self.assertEqual(obter_ip_cliente({"X-Real-IP": "192.0.2.10"}), "192.0.2.10")
        self.assertEqual(obter_ip_cliente({"X-Forwarded-For": "198.51.100.5, 127.0.0.1"}), "198.51.100.5")
        self.assertEqual(obter_ip_cliente({}), "local")

    def test_sanitizar_celula_excel_neutraliza_formulas(self):
        for perigoso in ("=CMD()", "+SUM(A1)", "-1+1", "@SUM(1,2)", "\t=1", " =HYPERLINK()"):
            resultado = sanitizar_celula_excel(perigoso)
            self.assertTrue(str(resultado).startswith("'"), perigoso)
        self.assertEqual(sanitizar_celula_excel("001-CARPINA"), "001-CARPINA")
        self.assertEqual(sanitizar_celula_excel(123.45), 123.45)

    def test_validar_arquivo_xlsx_bloqueia_xxe_traversal_e_corrompido(self):
        tmp_dir = ROOT / "tests" / "_tmp_sec"
        tmp_dir.mkdir(exist_ok=True)
        try:
            invalido = tmp_dir / "nao_zip.xlsx"
            invalido.write_bytes(b"nao e um zip")
            with self.assertRaises(ValueError):
                validar_arquivo_xlsx(invalido)

            xxe = tmp_dir / "xxe.xlsx"
            _criar_xlsx_minimo(xxe, {"xl/sharedStrings.xml": b'<!DOCTYPE foo [<!ENTITY xxe "1">]><sst/>'})
            with self.assertRaises(ValueError):
                validar_arquivo_xlsx(xxe)

            traversal = tmp_dir / "traversal.xlsx"
            _criar_xlsx_minimo(traversal, {"../evil.txt": b"x"})
            with self.assertRaises(ValueError):
                validar_arquivo_xlsx(traversal)

            bomba = tmp_dir / "bomba.xlsx"
            # Cria entrada altamente compressível (>1 MB com razão > 100:1) para validar detecção de zip bomb.
            _criar_xlsx_minimo(bomba, {"xl/worksheets/sheet1.xml": b"A" * (2 * 1024 * 1024)})
            with self.assertRaises(ValueError):
                validar_arquivo_xlsx(bomba)

            valido = tmp_dir / "ok.xlsx"
            _criar_xlsx_minimo(valido, {"xl/worksheets/sheet1.xml": b"<worksheet/>"})
            validar_arquivo_xlsx(valido)
        finally:
            for item in tmp_dir.glob("*"):
                item.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def test_salvar_upload_rejeita_excesso_de_bytes(self):
        stream = BytesIO(b"x" * 2048)
        with self.assertRaises(ValueError):
            salvar_upload_xlsx_temporario(stream, limite_bytes=1024)
        self.assertGreater(MAX_BYTES_UPLOAD_XLSX, 1024)

    def test_config_toml_desabilita_tracebacks_e_habilita_protecoes(self):
        cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["client"]["showErrorDetails"], "none")
        self.assertTrue(cfg["server"]["enableCORS"])
        self.assertTrue(cfg["server"]["enableXsrfProtection"])
        self.assertTrue(cfg["server"]["headless"])
        self.assertFalse(cfg["browser"]["gatherUsageStats"])

    def test_app_usa_controles_seguranca_sem_vazamento(self):
        codigo = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("autenticar_admin(", codigo)
        self.assertIn("sessao_valida(", codigo)
        self.assertIn("sanitizar_celula_excel(", codigo)
        self.assertIn("ControladorTentativasLogin", codigo)
        self.assertNotIn("hmac.compare_digest(usuario", codigo)
        self.assertNotIn("{type(erro).__name__}: {erro}", codigo)


if __name__ == "__main__":
    unittest.main()
