"""Controles de segurança do ÁQUILA: autenticação, rate limit, sessão e Excel seguro."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import tempfile
import threading
import time
import zipfile
from collections import deque
from pathlib import Path
from typing import BinaryIO

LOG = logging.getLogger("aquila.seguranca")

# Hash PBKDF2 dummy válido para equalizar o tempo de resposta quando o usuário não existe.
_SALT_DUMMY = b"\x00" * 16
_HASH_DUMMY = "0" * 64
_PREFIXOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")

# Limites defensivos para planilhas .xlsx (ZIP de XMLs) contra zip bombs e XXE.
MAX_BYTES_UPLOAD_XLSX = 250 * 1024 * 1024
MAX_MEMBROS_ZIP = 2000
MAX_DESCOMPRIMIDO_XLSX = 512 * 1024 * 1024
MAX_RAZOES_COMPRESSAO = 100.0
LIMIAR_VERIFICACAO_RAZAO = 1024 * 1024


def verificar_senha(senha: str, armazenada: str) -> bool:
    """Valida senha em PBKDF2-HMAC-SHA256 (600.000 iterações) em tempo constante."""
    try:
        salt_hex, esperado_hex = armazenada.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        esperado = bytes.fromhex(esperado_hex.strip())
    except (ValueError, TypeError):
        return False
    if not salt or not esperado:
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, 600_000)
    return hmac.compare_digest(calculado, esperado)


def autenticar_admin(usuario: str, senha: str, admin_user: str, admin_hash: str) -> bool:
    """Autentica o administrador sem crash com UTF-8 e sem vazamento de tempo no usuário."""
    usuario_bytes = (usuario or "").strip().encode("utf-8")
    admin_bytes = (admin_user or "").strip().encode("utf-8")
    usuario_ok = bool(admin_bytes) and hmac.compare_digest(usuario_bytes, admin_bytes)
    if usuario_ok:
        senha_ok = verificar_senha(senha or "", admin_hash)
    else:
        # Executa PBKDF2 mesmo com usuário inválido para evitar enumeração por tempo.
        hashlib.pbkdf2_hmac("sha256", (senha or "").encode("utf-8"), _SALT_DUMMY, 600_000)
        hmac.compare_digest(_HASH_DUMMY.encode("ascii"), _HASH_DUMMY.encode("ascii"))
        senha_ok = False
    return usuario_ok and senha_ok


class ControladorTentativasLogin:
    """Limitador de taxa e bloqueio progressivo contra força bruta e DoS de CPU."""

    def __init__(
        self,
        max_tentativas_chave: int = 5,
        max_tentativas_ip: int = 15,
        janela_segundos: int = 300,
        bloqueio_base_segundos: int = 60,
        bloqueio_max_segundos: int = 900,
    ) -> None:
        self._max_chave = max_tentativas_chave
        self._max_ip = max_tentativas_ip
        self._janela = janela_segundos
        self._bloqueio_base = bloqueio_base_segundos
        self._bloqueio_max = bloqueio_max_segundos
        self._lock = threading.Lock()
        self._falhas: dict[str, deque[float]] = {}
        self._bloqueios: dict[str, float] = {}
        self._reincidencias: dict[str, int] = {}

    def _limpar_janela(self, registro: deque[float], agora: float) -> None:
        corte = agora - self._janela
        while registro and registro[0] < corte:
            registro.popleft()

    @staticmethod
    def _chaves(ip: str, usuario: str) -> tuple[str, str]:
        ip_limpo = (ip or "desconhecido").strip()[:64]
        user_limpo = (usuario or "").strip().lower()[:64]
        return f"ip:{ip_limpo}", f"cred:{ip_limpo}:{user_limpo}"

    def segundos_bloqueado(self, ip: str, usuario: str, agora: float | None = None) -> int:
        """Retorna quantos segundos restam de bloqueio (0 se liberado)."""
        t = time.monotonic() if agora is None else agora
        with self._lock:
            restante = 0.0
            for chave in self._chaves(ip, usuario):
                expira = self._bloqueios.get(chave, 0.0)
                if expira > t:
                    restante = max(restante, expira - t)
                elif chave in self._bloqueios:
                    del self._bloqueios[chave]
            return int(restante) + (1 if restante > 0 and restante % 1 > 0 else 0)

    def registrar_falha(self, ip: str, usuario: str, agora: float | None = None) -> int:
        """Registra tentativa inválida e retorna duração do bloqueio aplicado (0 se não bloqueado)."""
        t = time.monotonic() if agora is None else agora
        chave_ip, chave_cred = self._chaves(ip, usuario)
        with self._lock:
            bloqueio_aplicado = 0
            for chave, limite in ((chave_cred, self._max_chave), (chave_ip, self._max_ip)):
                fila = self._falhas.setdefault(chave, deque())
                self._limpar_janela(fila, t)
                fila.append(t)
                if len(fila) >= limite:
                    nivel = self._reincidencias.get(chave, 0)
                    duracao = min(self._bloqueio_max, self._bloqueio_base * (2 ** nivel))
                    self._bloqueios[chave] = t + duracao
                    self._reincidencias[chave] = nivel + 1
                    fila.clear()
                    bloqueio_aplicado = max(bloqueio_aplicado, duracao)
            return bloqueio_aplicado

    def registrar_sucesso(self, ip: str, usuario: str) -> None:
        """Limpa contadores após autenticação bem-sucedida."""
        chave_ip, chave_cred = self._chaves(ip, usuario)
        with self._lock:
            for chave in (chave_cred, chave_ip):
                self._falhas.pop(chave, None)
                self._bloqueios.pop(chave, None)
                self._reincidencias.pop(chave, None)


def obter_ip_cliente(headers: object) -> str:
    """Extrai o IP do cliente a partir dos cabeçalhos encaminhados pelo proxy."""
    if not headers:
        return "local"
    try:
        real_ip = headers.get("X-Real-IP") or headers.get("x-real-ip")
        if real_ip:
            return str(real_ip).strip()[:64]
        forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if forwarded:
            return str(forwarded).split(",")[0].strip()[:64]
    except Exception:
        pass
    return "local"


def ttl_sessao_segundos() -> tuple[int, int]:
    """Retorna (idle_ttl, max_ttl) configuráveis por variável de ambiente."""
    def _ler(nome: str, padrao: int, minimo: int, maximo: int) -> int:
        bruto = os.environ.get(nome)
        if not bruto:
            return padrao
        valor = int(bruto)
        if not minimo <= valor <= maximo:
            raise ValueError(f"{nome} deve estar entre {minimo} e {maximo}")
        return valor

    return (
        _ler("AQUILA_SESSION_IDLE_SECONDS", 1800, 60, 86400),
        _ler("AQUILA_SESSION_MAX_SECONDS", 28800, 300, 604800),
    )


def sessao_valida(session_state: dict, agora: float | None = None) -> bool:
    """Verifica se a sessão autenticada ainda está dentro dos prazos de inatividade e vida útil."""
    if not session_state.get("admin_ok"):
        return False
    t = time.monotonic() if agora is None else agora
    idle_ttl, max_ttl = ttl_sessao_segundos()
    login_at = session_state.get("aq_login_at")
    last_active = session_state.get("aq_last_active")
    if login_at is None or last_active is None:
        session_state["aq_login_at"] = t
        session_state["aq_last_active"] = t
        return True
    if (t - float(last_active)) > idle_ttl or (t - float(login_at)) > max_ttl:
        encerrar_sessao(session_state)
        return False
    session_state["aq_last_active"] = t
    return True


def iniciar_sessao(session_state: dict, agora: float | None = None) -> None:
    """Marca a sessão como autenticada e inicializa os carimbos de tempo."""
    t = time.monotonic() if agora is None else agora
    session_state["admin_ok"] = True
    session_state["aq_login_at"] = t
    session_state["aq_last_active"] = t


def encerrar_sessao(session_state: dict) -> None:
    """Remove os marcadores de autenticação da sessão."""
    session_state["admin_ok"] = False
    session_state.pop("aq_login_at", None)
    session_state.pop("aq_last_active", None)


def sanitizar_celula_excel(valor: object) -> object:
    """Neutraliza Formula Injection (CSV/Excel Injection) em células textuais exportadas."""
    if not isinstance(valor, str):
        return valor
    sem_espaco_esq = valor.lstrip(" ")
    if valor.startswith(_PREFIXOS_FORMULA) or sem_espaco_esq.startswith(_PREFIXOS_FORMULA):
        return "'" + valor
    return valor


def validar_arquivo_xlsx(caminho: str | Path) -> None:
    """Valida integridade ZIP, limites contra zip bomb e ausência de DOCTYPE/ENTITY em XLSX."""
    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise ValueError("Arquivo XLSX não encontrado.")
    tamanho = arquivo.stat().st_size
    if tamanho <= 0 or tamanho > MAX_BYTES_UPLOAD_XLSX:
        raise ValueError("Tamanho do arquivo XLSX fora do limite permitido.")

    try:
        zf = zipfile.ZipFile(arquivo, "r")
    except zipfile.BadZipFile as erro:
        raise ValueError("Arquivo XLSX inválido ou corrompido.") from erro

    with zf:
        infos = zf.infolist()
        if not infos or len(infos) > MAX_MEMBROS_ZIP:
            raise ValueError("Estrutura do arquivo XLSX excede o limite de entradas permitido.")

        nomes = set()
        total_descomprimido = 0
        for info in infos:
            nome = info.filename
            # Bloqueia traversal e caminhos absolutos dentro do pacote ZIP.
            if nome.startswith(("/", "\\")) or ".." in Path(nome).parts:
                raise ValueError("Arquivo XLSX contém caminho interno inválido.")
            nomes.add(nome)

            total_descomprimido += info.file_size
            if total_descomprimido > MAX_DESCOMPRIMIDO_XLSX:
                raise ValueError("Arquivo XLSX excede o tamanho descomprimido máximo permitido.")

            if info.file_size > LIMIAR_VERIFICACAO_RAZAO:
                if info.compress_size <= 0 or (info.file_size / info.compress_size) > MAX_RAZOES_COMPRESSAO:
                    raise ValueError("Taxa de compressão suspeita detectada no arquivo XLSX.")

            if info.flag_bits & 0x1:
                raise ValueError("Planilhas protegidas por senha não são suportadas.")

            if nome.lower().endswith((".xml", ".rels")):
                # Inspeciona o cabeçalho do XML contra declarações DOCTYPE/ENTITY (XXE/Billion Laughs).
                with zf.open(info, "r") as stream:
                    cabecalho = stream.read(4096).upper()
                if b"<!DOCTYPE" in cabecalho or b"<!ENTITY" in cabecalho:
                    raise ValueError("Conteúdo XML não permitido detectado na planilha.")

        if "[Content_Types].xml" not in nomes or not any(n.startswith("xl/") for n in nomes):
            raise ValueError("Arquivo não possui estrutura válida de planilha Excel (.xlsx).")


def salvar_upload_xlsx_temporario(upload: BinaryIO, limite_bytes: int = MAX_BYTES_UPLOAD_XLSX) -> str:
    """Grava upload XLSX em arquivo temporário aplicando limite rígido de tamanho."""
    lido = 0
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        caminho = tmp.name
        try:
            while bloco := upload.read(1024 * 1024):
                lido += len(bloco)
                if lido > limite_bytes:
                    raise ValueError("O arquivo enviado excede o tamanho máximo permitido.")
                tmp.write(bloco)
        except Exception:
            tmp.close()
            try:
                os.unlink(caminho)
            except OSError:
                pass
            raise
    return caminho
