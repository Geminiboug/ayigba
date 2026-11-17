"""Journal des décisions : pourquoi un élément a été corrigé, supprimé ou généré.

Une ligne JSON par décision dans logs/decisions.jsonl. Pas d'horodatage par ligne : le journal
doit être identique d'une exécution à l'autre pour la même entrée et la même graine.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ACTIONS = ("corrige", "supprime", "genere", "signale", "info")


class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._buffer: list[dict] = []
        self._stage = ""

    def start_stage(self, stage: str) -> None:
        """Efface les décisions d'une exécution précédente de cette étape, puis ouvre l'étape."""
        self.flush()
        self._stage = stage
        if self.path.is_file():
            kept = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line and json.loads(line).get("etape") != stage]
            self.path.write_text("".join(line + "\n" for line in kept), encoding="utf-8")

    def record(self, action: str, obj: str, reason: str, **details) -> None:
        """action : une valeur de ACTIONS ; obj : identifiant de l'élément (ex. « way/123 ») ; reason : phrase courte en français."""
        if action not in ACTIONS:
            raise ValueError(f"action inconnue : {action}")
        entry = {"etape": self._stage, "action": action, "objet": obj, "raison": reason}
        if details:
            entry["details"] = details
        self._buffer.append(entry)

    def flush(self) -> None:
        if not self._buffer:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for entry in self._buffer:
                f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        self._buffer.clear()

    def counts(self, stage: str | None = None) -> dict[str, int]:
        """Nombre de décisions par action (pour les rapports)."""
        self.flush()
        c: Counter[str] = Counter()
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                e = json.loads(line)
                if stage is None or e.get("etape") == stage:
                    c[e["action"]] += 1
        return dict(c)
