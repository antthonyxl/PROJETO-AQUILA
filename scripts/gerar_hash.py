import getpass
import hashlib
import secrets
senha = getpass.getpass('Digite a senha administrativa (não será exibida): ')
if len(senha) < 12:
    raise SystemExit('Use pelo menos 12 caracteres na senha administrativa.')
salt = secrets.token_bytes(16)
h = hashlib.pbkdf2_hmac('sha256', senha.encode(), salt, 600_000)
print(f'ADMIN_PASSWORD_HASH = "{salt.hex()}:{h.hex()}"')
