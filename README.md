# LACE-TTRI

**LACE-TTRI: A Novel Encrypt-then-Camouflage Framework for Secure Text Transmission via Realistic Image Camouflage**

This repository contains a **research prototype** implementing text-to-image encryption, realistic image camouflage, and the corresponding reverse process. It is designed for **Google Colab** and processes **one text file and one cover image per run**.

> **Research-use notice:** This is an experimental cryptographic construction, not an independently audited or authenticated encryption product. Do not use it to protect production-sensitive information.

## Repository files

| File | Purpose |
|---|---|
| `encryption.py` | Text encryption and camouflage; prompts for a plaintext file, cover image and encryption parameters |
| `decryption.py` | Reverses camouflage and encryption; prompts for three separate recovery files |
| `requirements.txt` | Required Python packages |
| `.gitignore` | Excludes generated data, secret metadata and local files |

## Running in Google Colab

1. Open [Google Colab](https://colab.research.google.com/).
2. Upload `encryption.py` into the Colab session, or clone the repository.
3. Execute `!python encryption.py` **only if running in an interactive Colab environment that supports file-upload prompts**. The most reliable method is to open the file in Colab and execute its code in a notebook cell (`%run encryption.py` may also work in an interactive notebook).
4. Upload **one** `.txt` or `.docx` file when prompted.
5. Upload **one** natural cover image (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.tif`, or `.tiff`).
6. Choose the primary key, independent secondary XOR key, Arnold rounds, camouflage factor `alpha`, and cover channel (`R`, `G`, or `B`).
7. Download the generated ZIP. **Keep the recovery metadata private.**

### Encryption output

- `encrypted_image.png` — grayscale encrypted image.
- `cover.png` — resized RGB cover preview.
- `cover.npy` — **exact RGB cover values** used in camouflage.
- `fake_color.png` — visual camouflage preview **not suitable for exact recovery**.
- `fake_color_float.npy` — **float64 camouflage data** required for exact recovery.
- `confidential_recovery_metadata.json` — **SECRET**: contains keys and recovery parameters.

## Decryption

Run `decryption.py` in Colab. Upload the following **three files separately**, in order:

1. `fake_color_float.npy`
2. `cover.npy`
3. `confidential_recovery_metadata.json`

The script reverses camouflage, Lorenz permutation, XOR diffusion, Arnold Cat Map, checksum replacement and substitution. It checks the recovered plaintext against the SHA-256 digest stored in the metadata. If the check passes, it downloads `LACE_TTRI_Decryption_Output.zip`, containing:

- `recovered_text.txt`
- `recovered_cipher.png`

**DOCX limitation:** Encryption extracts text from DOCX; it does not encrypt the complete Word file, formatting, embedded media or tables. The recovered content is saved as `.txt`.

## Algorithm overview

1. Keyed 16 × 16 substitution matrix with SHA-256-derived byte stream.
2. Dynamic checksum-byte replacement and square packing.
3. Arnold Cat Map permutation.
4. XOR diffusion with an independent secondary key.
5. Lorenz-based index scrambling.
6. RGB-channel camouflage using `float64` blending.

## Dependencies

Google Colab includes many dependencies by default. If necessary:

```python
!pip install -r requirements.txt
```

`google.colab` is supplied by the Colab runtime and is not a standard local Python dependency.

## Security and reproducibility notes

- **Never commit** real recovery metadata, secret keys, private plaintext, or sensitive cover/payload files to a public repository.
- The `.gitignore` protects only *untracked* matching files; it does not remove secrets already committed to Git history.
- A valid SHA-256 recovery match demonstrates an exact round-trip for the tested sample, **not** a general proof of cryptographic security.
- The stored plaintext SHA-256 digest is unkeyed and may disclose information about predictable plaintext. Treat recovery metadata as confidential.
- For exact recovery, use the original `.npy` files, not the preview `.png`.

## License

No open-source license is assigned yet. Add a `LICENSE` file before inviting third-party reuse, according to the authors' publishing and institutional requirements.
