"""Dossier d'un projet et contexte passé à chaque étape du pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config, load_config
from .journal import Journal

SUBDIRS = ("data", "cache", "work", "out", "reports", "logs")


@dataclass(frozen=True)
class Project:
    root: Path

    @property
    def slug(self) -> str:
        return self.root.name

    @property
    def config_path(self) -> Path:
        return self.root / "config.toml"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def out(self) -> Path:
        return self.root / "out"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure_dirs(self) -> None:
        for name in SUBDIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def stage_dir(self, stage: str) -> Path:
        d = self.work / stage
        d.mkdir(parents=True, exist_ok=True)
        return d


@dataclass
class Context:
    """Tout ce dont une étape a besoin. Une étape ne lit et n'écrit que dans le projet."""

    project: Project
    config: Config
    journal: Journal
    offline: bool = False


def open_context(root: Path, offline: bool = False) -> Context:
    project = Project(Path(root).resolve())
    config = load_config(project.config_path)
    project.ensure_dirs()
    return Context(project=project, config=config, journal=Journal(project.logs / "decisions.jsonl"), offline=offline)
