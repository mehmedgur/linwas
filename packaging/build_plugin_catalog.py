"""Linwas eklenti kataloğunu üretir (imzalamayı build-plugin-catalog.sh yapar).

Kullanım: python3 packaging/build_plugin_catalog.py <kaynak-klasör> <çıktı-klasörü>
  kaynak: plugins/*.json (eklenti tanımları) + revoked.json (geri çekilenler)
  çıktı:  index.json + files/<kimlik>-<sürüm>.json
Her tanım Linwas'ın kendi doğrulayıcısından geçer; geçmeyen tanımla katalog üretilmez.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from linwas.core.plugins import declarative  # noqa: E402


def main(source: Path, out: Path) -> int:
    files = out / "files"
    files.mkdir(parents=True, exist_ok=True)
    plugins = []
    seen: set[str] = set()
    for path in sorted((source / "plugins").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        try:
            manifest = declarative.parse(text)
        except declarative.ManifestError as exc:
            print(f"HATA: {path.name}: {exc}", file=sys.stderr)
            return 1
        if manifest["id"] in seen:
            print(f"HATA: {manifest['id']} iki kez var", file=sys.stderr)
            return 1
        seen.add(manifest["id"])
        name = f"{manifest['id']}-{manifest['version']}.json"
        data = text.encode("utf-8")
        (files / name).write_bytes(data)
        plugins.append(
            {
                "id": manifest["id"],
                "version": manifest["version"],
                "name": manifest["name"],
                "description": manifest["description"],
                "publisher": manifest["publisher"],
                "url": f"files/{name}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    revoked_path = source / "revoked.json"
    revoked = json.loads(revoked_path.read_text(encoding="utf-8")) if revoked_path.exists() else []
    index = {"schema": 1, "plugins": plugins, "revoked": revoked}
    (out / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{len(plugins)} eklenti, {len(revoked)} geri çekilen → {out / 'index.json'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
