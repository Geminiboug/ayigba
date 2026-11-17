"""Configuration d'un projet (une ville ou un quartier), lue depuis config.toml."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


class ConfigError(ValueError):
    """Configuration invalide : le message dit quoi corriger."""


@dataclass(frozen=True)
class Config:
    city: str
    district: str
    country: str
    bbox: tuple[float, float, float, float]  # ouest, sud, est, nord (WGS84)
    seed: int
    style: str
    engine: str
    options: str = "{}"  # sections facultatives ([secours], [optimisation]...) en JSON, pour rester hachable

    def option(self, section: str, key: str, default):
        """Valeur d'une section facultative de config.toml, ou la valeur par défaut."""
        return json.loads(self.options).get(section, {}).get(key, default)

    @property
    def west(self) -> float:
        return self.bbox[0]

    @property
    def south(self) -> float:
        return self.bbox[1]

    @property
    def east(self) -> float:
        return self.bbox[2]

    @property
    def north(self) -> float:
        return self.bbox[3]

    def digest(self) -> str:
        """Empreinte stable de la configuration (sert à la reprise des étapes)."""
        blob = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise ConfigError(f"Fichier de configuration introuvable : {path}")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    try:
        ville = raw["ville"]
        bbox = tuple(float(v) for v in raw["zone"]["bbox"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"Configuration incomplète ({exc}) : il faut [ville] nom et [zone] bbox.") from exc
    if len(bbox) != 4:
        raise ConfigError("zone.bbox doit contenir 4 nombres : ouest, sud, est, nord.")
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ConfigError("zone.bbox invalide : il faut ouest < est et sud < nord, en degrés WGS84.")
    if (east - west) > 0.5 or (north - south) > 0.5:
        raise ConfigError("zone.bbox trop grande (plus de 0,5 degré) : découpe la ville en plusieurs projets.")
    gen = raw.get("generation", {})
    exp = raw.get("export", {})
    return Config(
        city=str(ville.get("nom", "")),
        district=str(ville.get("quartier", "")),
        country=str(ville.get("pays", "")),
        bbox=bbox,
        seed=int(gen.get("graine", 0)),
        style=str(gen.get("style", "defaut")),
        engine=str(exp.get("moteur", "neutre")),
        options=json.dumps({k: v for k, v in raw.items() if k not in ("ville", "zone", "generation", "export") and isinstance(v, dict)},
                           sort_keys=True, ensure_ascii=False),
    )
