"""Étape « secours » : combler les zones sans données par une génération cohérente avec le quartier.

PAS ENCORE FAIT. L'étape existe pour que le pipeline ait sa forme définitive ; elle ne change rien à la carte.
"""
from __future__ import annotations


def run(ctx) -> dict:
    ctx.journal.record("info", "secours", "étape pas encore faite : aucune zone vide n'est comblée dans cette version")
    return {"etat": "pas encore fait", "elements_generes": 0}
