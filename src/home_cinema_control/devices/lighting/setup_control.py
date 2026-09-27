from dataclasses import asdict

from .factory import create_lighting_controller


def test_lighting_connection(config):
    return create_lighting_controller(config).test_connection()


def turn_lighting_on(config):
    return create_lighting_controller(config).turn_on()


def turn_lighting_off(config):
    return create_lighting_controller(config).turn_off()


def list_lighting_entities(config) -> list[dict]:
    return [asdict(entity) for entity in create_lighting_controller(config).list_entities()]
