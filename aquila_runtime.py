"""Limites de conexões por processo, configuráveis sem editar o dashboard."""
import os


def inteiro_ambiente(nome: str, padrao: int, minimo: int, maximo: int) -> int:
    valor = int(os.environ.get(nome, str(padrao)))
    if not minimo <= valor <= maximo:
        raise ValueError(f'{nome} deve estar entre {minimo} e {maximo}')
    return valor


def configuracao_pool() -> dict:
    # Sessões web compartilham conexões; não abrir uma conexão por usuário.
    maximo = inteiro_ambiente('AQUILA_DB_POOL_MAX', 8, 1, 64)
    return {
        'min_size': min(2, maximo),
        'max_size': maximo,
        'max_waiting': inteiro_ambiente('AQUILA_DB_MAX_WAITING', 100, 1, 1000),
        'timeout': inteiro_ambiente('AQUILA_DB_POOL_TIMEOUT', 30, 1, 120),
        'max_idle': 300,
        'kwargs': {
            'connect_timeout': 10,
            # Autocommit evita transações ociosas; somente este pool é de leitura.
            'autocommit': True,
            'prepare_threshold': None,
            'options': '-c default_transaction_read_only=on -c statement_timeout=20000',
        },
    }
