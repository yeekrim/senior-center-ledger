"""클라이언트 -> 백엔드 구간 봉투(hybrid) 암호화.

이미지는 매번 새로 생성한 AES-256-GCM 키로 암호화하고(대용량 데이터에 적합),
그 대칭키만 백엔드의 RSA 공개키로 암호화해서 함께 전송한다(봉투).
백엔드만 자신의 RSA 개인키로 봉투를 열어 대칭키를 복원하고, 그 키로 이미지를 복호화한다.

이 모듈이 보호하는 구간은 '클라이언트 -> 백엔드' 뿐이다. 백엔드가 복호화한 평문을
클라우드 OCR 벤더로 보내는 순간부터는 이 모듈의 보호 범위 밖이며, 그 구간은
TLS와 벤더의 데이터 정책에 의존한다.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_DIR = Path(__file__).parent / "keys"
PRIVATE_KEY_PATH = KEY_DIR / "backend_private_key.pem"
PUBLIC_KEY_PATH = KEY_DIR / "backend_public_key.pem"

_OAEP_PADDING = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)


@dataclass
class EncryptedEnvelope:
    """전송되는 봉투. encrypted_key 없이는 ciphertext를 열 수 없다."""
    encrypted_key: bytes   # RSA-OAEP로 암호화된 AES 키
    nonce: bytes           # AES-GCM nonce (12바이트)
    ciphertext: bytes      # AES-GCM 암호문 (인증 태그 포함)


def generate_rsa_keypair(key_size: int = 3072):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    return private_key, private_key.public_key()


def load_or_create_backend_keypair():
    """백엔드 RSA 키쌍을 로드하거나, 없으면 새로 만들어 keys/ 아래 저장한다.

    데모/개발용 구현이다. 실제 운영에서는 KMS/시크릿 매니저에서 개인키를
    가져와야 하며, 평문 PEM 파일을 저장소에 두면 안 된다.
    """
    if PRIVATE_KEY_PATH.exists():
        private_key = serialization.load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)
        return private_key, private_key.public_key()

    private_key, public_key = generate_rsa_keypair()
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_KEY_PATH.write_bytes(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    PUBLIC_KEY_PATH.write_bytes(public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return private_key, public_key


def encrypt_envelope(plaintext: bytes, backend_public_key) -> EncryptedEnvelope:
    """클라이언트가 촬영 직후 수행한다고 가정하는 암호화."""
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, associated_data=None)
    encrypted_key = backend_public_key.encrypt(aes_key, _OAEP_PADDING)
    return EncryptedEnvelope(encrypted_key=encrypted_key, nonce=nonce, ciphertext=ciphertext)


def decrypt_envelope(envelope: EncryptedEnvelope, backend_private_key) -> bytes:
    """백엔드만 수행할 수 있는 복호화. 평문은 반환값으로만 잠깐 존재한다."""
    aes_key = backend_private_key.decrypt(envelope.encrypted_key, _OAEP_PADDING)
    return AESGCM(aes_key).decrypt(envelope.nonce, envelope.ciphertext, associated_data=None)
