from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import requests

REVISION = '48b10fa505aeb51fbd127fc60a5c660040e823b7'
MODELS = (
    ('face_detection_yunet', 'face_detection_yunet_2026may.onnx', 'MIT'),
    ('face_recognition_sface', 'face_recognition_sface_2021dec.onnx', 'Apache-2.0'),
)


def prepare_face_models(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    records = {}
    for folder, filename, licence in MODELS:
        path = f'models/{folder}/{filename}'
        pointer = requests.get(f'https://raw.githubusercontent.com/opencv/opencv_zoo/{REVISION}/{path}', timeout=30)
        pointer.raise_for_status()
        match = re.search(r'oid sha256:([a-f0-9]{64})\nsize (\d+)', pointer.text)
        if not match:
            raise ValueError(f'Pinned upstream LFS hash is missing for {filename}')
        digest, length = match.group(1), int(match.group(2))
        destination = directory / filename
        if not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            temporary = destination.with_suffix('.part')
            try:
                with requests.get(f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/{path}', stream=True, timeout=(30, 180)) as response:
                    response.raise_for_status()
                    with temporary.open('wb') as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                if temporary.stat().st_size != length or hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                    raise ValueError(f'Pinned model integrity check failed: {filename}')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        license_response = requests.get(f'https://raw.githubusercontent.com/opencv/opencv_zoo/{REVISION}/models/{folder}/LICENSE', timeout=30)
        license_response.raise_for_status()
        license_file = folder + '-LICENSE.txt'
        (directory / license_file).write_text(license_response.text, encoding='utf-8')
        records[filename] = {'sha256': digest, 'bytes': length, 'license': licence, 'license_file': license_file, 'source': f'https://github.com/opencv/opencv_zoo/tree/{REVISION}/models/{folder}'}
    (directory / 'face-manifest.json').write_text(json.dumps({'version': 1, 'upstream_revision': REVISION, 'models': records, 'purpose': 'Optional local enrolled-staff matching; not liveness or access control; site accuracy unqualified'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    destination = Path(__file__).resolve().parent / 'build' / 'standalone_models'
    prepare_face_models(destination)
    print(json.dumps({'ok': True, 'pinned_models': list(json.loads((destination / 'face-manifest.json').read_text())['models'])}))
