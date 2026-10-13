"""LACE-TTRI decryption — Google Colab research prototype.
Select three files individually: fake_color_float.npy, cover.npy, confidential_recovery_metadata.json.
"""
import io
import json
import hashlib
import zipfile

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from google.colab import files


def upload_one_file(message, extension):
    print('\n' + message)
    uploaded = files.upload()
    if len(uploaded) != 1:
        raise ValueError('Select exactly ONE file.')
    filename, content = next(iter(uploaded.items()))
    if not filename.lower().endswith(extension):
        raise ValueError('Expected a file ending with ' + extension)
    print('Selected:', filename)
    return filename, content


def sha256_stream(seed_bytes, key_bytes, length):
    combined = hashlib.sha256(key_bytes + seed_bytes).digest()
    output = bytearray()
    for counter in range((length + 31) // 32):
        output.extend(hashlib.sha256(combined + counter.to_bytes(8, 'big')).digest())
    return np.frombuffer(bytes(output[:length]), dtype=np.uint8)


def lorenz_indices(length, key, seed):
    digest = hashlib.sha256(key + seed).digest()
    x, y, z = [b / 255.0 for b in digest[:3]]
    sigma = 10 + digest[3] / 255.0 * 10
    rho = 28 + digest[4] / 255.0 * 30
    beta = 8 / 3 + digest[5] / 255.0 * 2
    sequence = np.empty(length, dtype=np.float64)
    for i in range(length):
        dx = sigma * (y - x)
        dy = x * (rho - z) - y
        dz = x * y - beta * z
        x += dx * 0.01
        y += dy * 0.01
        z += dz * 0.01
        sequence[i] = y
    return np.argsort(sequence, kind='stable')


def inverse_arnold(image, rounds):
    result = image.copy()
    N = result.shape[0]
    yy, xx = np.indices((N, N))
    new_x = (xx + yy) % N
    new_y = (xx + 2 * yy) % N
    for _ in range(rounds):
        restored = np.empty_like(result)
        restored[yy, xx] = result[new_y, new_x]
        result = restored
    return result


def build_matrix(key):
    values = list(dict.fromkeys(key))
    values.extend(b for b in range(256) if b not in values)
    return np.array(values, dtype=np.uint8).reshape(16, 16)


def main():
    print('=' * 60)
    print('LACE-TTRI — DECRYPTION AND TEXT RECOVERY')
    print('=' * 60)
    _, fake_bytes = upload_one_file('[1] Select FAKE IMAGE (fake_color_float.npy)', '.npy')
    _, cover_bytes = upload_one_file('[2] Select COVER IMAGE (cover.npy)', '.npy')
    _, metadata_bytes = upload_one_file('[3] Select RECOVERY METADATA (.json)', '.json')

    fake = np.load(io.BytesIO(fake_bytes), allow_pickle=False)
    cover = np.load(io.BytesIO(cover_bytes), allow_pickle=False)
    metadata = json.loads(metadata_bytes.decode('utf-8'))
    key1 = bytes.fromhex(metadata['primary_key_hex'])
    key2 = bytes.fromhex(metadata['secondary_xor_key_hex'])
    seed = bytes.fromhex(metadata['plaintext_sha256'])
    n = int(metadata['original_length_bytes'])
    N = int(metadata['image_size'])
    rounds = int(metadata['arnold_rounds'])
    alpha = float(metadata['alpha'])
    channel = metadata['channel'].upper()
    checksum_pos = int(metadata['checksum_position'])
    ci = {'R': 0, 'G': 1, 'B': 2}[channel]

    if n <= 0 or N * N < n or not (0 <= checksum_pos < n):
        raise ValueError('Invalid text length, image size or checksum position')
    if fake.shape != (N, N, 3) or cover.shape != (N, N, 3):
        raise ValueError('Invalid image dimensions')
    if not 0 < alpha < 1:
        raise ValueError('Invalid alpha')
    if fake.dtype != np.float64:
        raise ValueError('Fake image must be float64')

    print('\n[1/6] Removing camouflage...')
    recovered_float = (fake[:, :, ci] - alpha * cover[:, :, ci]) / (1 - alpha)
    rounded = np.rint(recovered_float)
    if not np.all(np.isfinite(recovered_float)) or np.any((rounded < 0) | (rounded > 255)):
        raise ValueError('Invalid recovered pixels')
    max_error = float(np.max(np.abs(recovered_float - rounded)))
    if max_error > 1e-5:
        raise ValueError('Camouflage recovery failed: use the exact float64 NPY files')
    recovered_cipher = rounded.astype(np.uint8)

    print('[2/6] Inverse Lorenz scrambling...')
    idx = lorenz_indices(N * N, key1, seed)
    inverse_idx = np.argsort(idx)
    data = recovered_cipher.reshape(-1)[inverse_idx].reshape(N, N)

    print('[3/6] Inverse XOR diffusion...')
    xor_seed = hashlib.sha256(b'LACE-TTRI|XOR|' + key2 + seed).digest()
    data = np.bitwise_xor(data, sha256_stream(xor_seed, key2, N * N).reshape(N, N))

    print('[4/6] Inverse Arnold Cat Map...')
    data = inverse_arnold(data, rounds)

    print('[5/6] Recovering checksum-replaced byte...')
    substituted = data.reshape(-1)[:n].copy()
    stored_checksum = int(substituted[checksum_pos])
    sum_other = (int(substituted.sum(dtype=np.uint64)) - stored_checksum) % 256
    substituted[checksum_pos] = (stored_checksum - sum_other) % 256
    if int(substituted.sum(dtype=np.uint64) % 256) != stored_checksum:
        raise ValueError('Checksum verification failed')

    print('[6/6] Reversing keyed substitution...')
    matrix = build_matrix(key1)
    positions = np.empty((256, 2), dtype=np.int16)
    for r in range(16):
        for c in range(16):
            positions[int(matrix[r, c])] = (r, c)
    V = sha256_stream(seed, key1, n)
    dr = (V & 15).astype(np.int16)
    dc = (V >> 4).astype(np.int16)
    mapped = positions[substituted]
    original_r = (mapped[:, 0] - dr) % 16
    original_c = (mapped[:, 1] - dc) % 16
    plaintext = (original_r * 16 + original_c).astype(np.uint8).tobytes()

    actual_hash = hashlib.sha256(plaintext).hexdigest()
    if actual_hash != metadata['plaintext_sha256']:
        raise ValueError('SHA-256 verification FAILED: recovered text differs from original')

    print('\n' + '=' * 60)
    print('DECRYPTION COMPLETED SUCCESSFULLY')
    print('SHA-256 MATCH: TRUE')
    print('Original text recovered exactly.')
    print('=' * 60)

    # For DOCX inputs, encryption extracts text rather than original DOCX bytes.
    with open('recovered_text.txt', 'wb') as f:
        f.write(plaintext)
    Image.fromarray(recovered_cipher).save('recovered_cipher.png')

    fake_preview = np.clip(np.rint(fake), 0, 255).astype(np.uint8)
    cover_preview = np.clip(np.rint(cover), 0, 255).astype(np.uint8)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    axes[0].imshow(fake_preview)
    axes[0].set_title('Fake Image')
    axes[1].imshow(cover_preview)
    axes[1].set_title('Cover Image')
    axes[2].imshow(recovered_cipher, cmap='gray', vmin=0, vmax=255)
    axes[2].set_title('Recovered Cipher Image')
    for ax in axes:
        ax.axis('off')
    plt.tight_layout()
    plt.show()

    output_zip = 'LACE_TTRI_Decryption_Output.zip'
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write('recovered_text.txt')
        z.write('recovered_cipher.png')
    print('\nOutput:', output_zip)
    files.download(output_zip)


if __name__ == '__main__':
    main()
