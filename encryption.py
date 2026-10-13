"""LACE-TTRI encryption and camouflage — Google Colab research prototype.
Upload one TXT/DOCX and one cover image. Run in Colab.
"""
import io
import math
import json
import hashlib
import secrets
import zipfile
import html
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from google.colab import files


def upload_one(label, extensions):
    print('\n' + label)
    uploaded = files.upload()
    if len(uploaded) != 1:
        raise ValueError('Select exactly one file.')
    name, content = next(iter(uploaded.items()))
    if not name.lower().endswith(extensions):
        raise ValueError('Unsupported file type: ' + name)
    return name, content


def read_text_bytes(name, content):
    if name.lower().endswith('.txt'):
        return bytes(content)
    if name.lower().endswith('.docx'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            xml = z.read('word/document.xml')
        root = ET.fromstring(xml)
        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        paragraphs = []
        for p in root.iter(ns + 'p'):
            paragraphs.append(''.join(t.text or '' for t in p.iter(ns + 't')))
        return '\n'.join(paragraphs).encode('utf-8')
    raise ValueError('TXT and DOCX only.')


def sha256_stream(seed_bytes, key_bytes, length):
    combined = hashlib.sha256(key_bytes + seed_bytes).digest()
    result = bytearray()
    for counter in range((length + 31) // 32):
        result.extend(hashlib.sha256(combined + counter.to_bytes(8, 'big')).digest())
    return np.frombuffer(bytes(result[:length]), dtype=np.uint8)


def build_key_matrix(key):
    values = list(dict.fromkeys(key))
    values.extend(b for b in range(256) if b not in values)
    return np.array(values, dtype=np.uint8).reshape(16, 16)


def arnold_cat(image, rounds):
    result = image.copy()
    N = result.shape[0]
    yy, xx = np.indices((N, N))
    new_x = (xx + yy) % N
    new_y = (xx + 2 * yy) % N
    for _ in range(rounds):
        nxt = np.empty_like(result)
        nxt[new_y, new_x] = result[yy, xx]
        result = nxt
    return result


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


def main():
    print('=' * 60)
    print('LACE-TTRI — ENCRYPTION AND CAMOUFLAGE')
    print('=' * 60)
    text_name, text_file = upload_one('[1] Select original TXT or DOCX', ('.txt', '.docx'))
    cover_name, cover_file = upload_one('[2] Select natural cover image', ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'))

    print('\nPrimary key: 1 = random; 2 = enter text')
    choice = input('Choose (1/2) [1]: ').strip() or '1'
    if choice == '1':
        key_length = int(input('Primary key length (1-256) [256]: ').strip() or '256')
        if not 1 <= key_length <= 256:
            raise ValueError('Primary key length must be 1-256')
        key1 = bytes(secrets.SystemRandom().sample(range(256), key_length))
    elif choice == '2':
        key1 = input('Primary key text: ').encode('utf-8')
        if not key1:
            raise ValueError('Primary key cannot be empty')
    else:
        raise ValueError('Invalid choice')

    print('\nSecondary XOR key: 1 = random 256-bit; 2 = 64-digit hexadecimal')
    choice = input('Choose (1/2) [1]: ').strip() or '1'
    if choice == '1':
        key2 = secrets.token_bytes(32)
    elif choice == '2':
        key2 = bytes.fromhex(input('Secondary key hex: ').strip())
        if len(key2) != 32:
            raise ValueError('Secondary key must be 256 bits')
    else:
        raise ValueError('Invalid choice')

    rounds = int(input('Arnold rounds (0-30) [10]: ').strip() or '10')
    alpha = float(input('Camouflage alpha (0-1) [0.999]: ').strip() or '0.999')
    channel = input('Cover channel (R/G/B) [R]: ').strip().upper() or 'R'
    if not 0 <= rounds <= 30 or not 0 < alpha < 1 or channel not in ('R', 'G', 'B'):
        raise ValueError('Invalid parameters')

    plaintext = read_text_bytes(text_name, text_file)
    n = len(plaintext)
    if n == 0:
        raise ValueError('Text is empty')
    seed = hashlib.sha256(plaintext).digest()

    # Layer 1: keyed substitution
    matrix = build_key_matrix(key1)
    V = sha256_stream(seed, key1, n)
    data = np.frombuffer(plaintext, dtype=np.uint8)
    dr, dc = V & 15, V >> 4
    substituted = matrix[((data // 16) + dr) % 16, ((data % 16) + dc) % 16].copy()

    # Layer 2: checksum replacement and square packing
    checksum_position = int(sha256_stream(seed, key1 + seed, 1)[0]) % n
    checksum = int(substituted.sum(dtype=np.uint64) % 256)
    substituted[checksum_position] = checksum
    N = math.isqrt(n - 1) + 1
    packed = np.zeros(N * N, dtype=np.uint8)
    packed[:n] = substituted

    # Layer 3: Arnold cat map
    cipher = arnold_cat(packed.reshape(N, N), rounds)

    # Layer 4: independent XOR key
    xor_seed = hashlib.sha256(b'LACE-TTRI|XOR|' + key2 + seed).digest()
    cipher = np.bitwise_xor(cipher, sha256_stream(xor_seed, key2, N * N).reshape(N, N))

    # Layer 5: Lorenz permutation
    idx = lorenz_indices(N * N, key1, seed)
    cipher = cipher.reshape(-1)[idx].reshape(N, N)

    # Layer 6: float64 camouflage
    with Image.open(io.BytesIO(cover_file)) as im:
        cover_image = im.convert('RGB').resize((N, N), Image.Resampling.BICUBIC)
    cover = np.asarray(cover_image, dtype=np.float64)
    fake_float = cover.copy()
    ci = {'R': 0, 'G': 1, 'B': 2}[channel]
    fake_float[:, :, ci] = (1 - alpha) * cipher.astype(np.float64) + alpha * cover[:, :, ci]
    fake_preview = np.clip(np.rint(fake_float), 0, 255).astype(np.uint8)

    Image.fromarray(cipher).save('encrypted_image.png')
    Image.fromarray(cover.astype(np.uint8)).save('cover.png')
    Image.fromarray(fake_preview).save('fake_color.png')
    np.save('cover.npy', cover)
    np.save('fake_color_float.npy', fake_float)

    # SECRET: contains both keys and plaintext digest; never commit this file.
    metadata = {
        'algorithm': 'LACE-TTRI',
        'original_filename': text_name,
        'original_length_bytes': n,
        'plaintext_sha256': seed.hex(),
        'primary_key_hex': key1.hex(),
        'secondary_xor_key_hex': key2.hex(),
        'arnold_rounds': rounds,
        'alpha': alpha,
        'channel': channel,
        'image_size': N,
        'checksum_position': checksum_position,
        'cover_filename': cover_name,
        'public_camouflage_file': 'fake_color_float.npy',
        'cover_file': 'cover.npy',
    }
    with open('confidential_recovery_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    axes[0].imshow(cipher, cmap='gray', vmin=0, vmax=255)
    axes[0].set_title('Encrypted Image')
    axes[1].imshow(cover.astype(np.uint8))
    axes[1].set_title('Natural Cover Image')
    axes[2].imshow(fake_preview)
    axes[2].set_title('Realistic Fake Image')
    for ax in axes:
        ax.axis('off')
    plt.tight_layout()
    plt.show()

    output_files = ['encrypted_image.png', 'cover.png', 'cover.npy',
                    'fake_color.png', 'fake_color_float.npy',
                    'confidential_recovery_metadata.json']
    zip_name = 'LACE_TTRI_Encryption_Output.zip'
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in output_files:
            z.write(path)
    print('Encryption and camouflage completed. Bytes:', n, 'Dimensions:', N, 'x', N)
    print('Keep the recovery metadata SECRET. PNG is only a visual preview.')
    files.download(zip_name)


if __name__ == '__main__':
    main()
