from home_cinema_control.devices.lighting.home_assistant import (
    HomeAssistantLightingController,
)


def create_lighting_controller(config):
    return HomeAssistantLightingController(config)


def create_lighting_controller_or_none(config):
    """Returns None when room lighting control is disabled."""
    if not (config.get("lighting") or {}).get("enabled"):
        return None
    return create_lighting_controller(config)
