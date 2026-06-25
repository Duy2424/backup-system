"""
Ma hoa / giai ma file backup bang AES (Fernet)
Su dung streaming de xu ly file lon ma khong tieu ton RAM
"""
import os
import struct
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import config


# Su dung AES-256 CBC streaming cho file lon
# Header: 16 bytes IV + content


def _derive_aes_key(fernet_key_str):
    """Tu Fernet key suy ra AES-256 key 32 bytes"""
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(fernet_key_str.encode())
    return digest.finalize()


def encrypt_file(in_path, out_path, key_str):
    """Ma hoa file streaming - phu hop file lon"""
    key = _derive_aes_key(key_str)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    enc = cipher.encryptor()

    file_size = os.path.getsize(in_path)

    with open(in_path, "rb") as fin, open(out_path, "wb") as fout:
        # Header: magic + size goc + IV
        fout.write(b"BKUP")
        fout.write(struct.pack("<Q", file_size))
        fout.write(iv)

        while True:
            chunk = fin.read(config.CHUNK_SIZE)
            if not chunk:
                break
            # Padding cho block cuoi
            if len(chunk) % 16 != 0:
                pad_len = 16 - (len(chunk) % 16)
                chunk = chunk + (b"\x00" * pad_len)
            fout.write(enc.update(chunk))
        fout.write(enc.finalize())


def decrypt_file(in_path, out_path, key_str):
    """Giai ma file streaming"""
    key = _derive_aes_key(key_str)

    with open(in_path, "rb") as fin:
        magic = fin.read(4)
        if magic != b"BKUP":
            raise ValueError("File khong hop le hoac da bi loi")
        original_size = struct.unpack("<Q", fin.read(8))[0]
        iv = fin.read(16)

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()

        with open(out_path, "wb") as fout:
            written = 0
            while True:
                chunk = fin.read(config.CHUNK_SIZE)
                if not chunk:
                    break
                plain = dec.update(chunk)
                # Loai bo padding o cuoi
                remaining = original_size - written
                if remaining < len(plain):
                    plain = plain[:remaining]
                fout.write(plain)
                written += len(plain)
            tail = dec.finalize()
            if tail:
                remaining = original_size - written
                if remaining > 0:
                    fout.write(tail[:remaining])


def encrypt_bytes(data, key_str):
    """Ma hoa bytes nho (dung Fernet)"""
    f = Fernet(key_str.encode() if isinstance(key_str, str) else key_str)
    return f.encrypt(data)


def decrypt_bytes(data, key_str):
    """Giai ma bytes nho"""
    f = Fernet(key_str.encode() if isinstance(key_str, str) else key_str)
    return f.decrypt(data)


if __name__ == "__main__":
    # Test
    from cryptography.fernet import Fernet
    k = Fernet.generate_key().decode()
    with open("/tmp/test.txt", "w") as f:
        f.write("Hello World " * 1000)
    encrypt_file("/tmp/test.txt", "/tmp/test.enc", k)
    decrypt_file("/tmp/test.enc", "/tmp/test.dec", k)
    with open("/tmp/test.txt", "rb") as f1, open("/tmp/test.dec", "rb") as f2:
        assert f1.read() == f2.read()
    print("OK")
