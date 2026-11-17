"""Étape « optimisation » : niveaux de détail, découpage en zones chargeables, budgets.

PAS ENCORE FAIT. L'étape existe pour que le pipeline ait sa forme définitive ; elle ne change rien à la carte.
"""
from __future__ import annotations


def run(ctx) -> dict:
    ctx.journal.record("info", "optimisation", "étape pas encore faite : la carte sort en un seul bloc, sans niveaux de détail")
    return {"etat": "pas encore fait"}
