from pathlib import Path

import yaml

from moveflow.config.schema import CommunityConfig


class CommunityNotFoundError(KeyError):
    pass


class CommunityCatalog:
    """Loads every community config from a folder of YAML files.

    Adding a community means dropping a new YAML file in that folder.
    """

    def __init__(self, configs: list[CommunityConfig]):
        self._configs = {config.id: config for config in configs}

    @classmethod
    def from_directory(cls, directory: Path) -> "CommunityCatalog":
        configs = [load_community(path) for path in sorted(directory.glob("*.yaml"))]
        return cls(configs)

    def get(self, community_id: str) -> CommunityConfig:
        try:
            return self._configs[community_id]
        except KeyError:
            raise CommunityNotFoundError(community_id) from None

    def all(self) -> list[CommunityConfig]:
        return list(self._configs.values())


def load_community(path: Path) -> CommunityConfig:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return CommunityConfig.model_validate(raw)
