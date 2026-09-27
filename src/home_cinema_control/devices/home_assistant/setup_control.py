from collections.abc import Iterable
from dataclasses import asdict

from .client import HomeAssistantClient


def test_home_assistant_connection(config):
    return HomeAssistantClient(config).test_connection()


def list_home_assistant_entities(config, domains: Iterable[str]) -> list[dict]:
    return [asdict(entity) for entity in HomeAssistantClient(config).list_entities(domains)]
