from home_cinema_control.devices.tv.adapters.home_assistant import HomeAssistantTvController
from home_cinema_control.devices.tv.adapters.lg import LgTvController
from home_cinema_control.devices.tv.adapters.scripts import ScriptsTvController
from home_cinema_control.devices.tv.adapters.sony import SonyTvController

TV_CONTROLLERS = {
    "HOME_ASSISTANT": HomeAssistantTvController,
    "LG": LgTvController,
    "SONY": SonyTvController,
    "SCRIPTS": ScriptsTvController,
}


def normalize_tv_model(model):
    return str(model or "").upper()


def get_supported_tv_models():
    return sorted(TV_CONTROLLERS.keys())


def create_tv_controller(config):
    model = normalize_tv_model((config.get("tv") or {}).get("model"))
    controller_class = TV_CONTROLLERS.get(model)

    if controller_class is None:
        raise ValueError(f"Unsupported TV model: {model}")

    return controller_class(config)


def create_tv_controller_or_none(config):
    """Returns None when TV control is disabled; raises ValueError for unknown model when enabled."""
    if not (config.get("tv") or {}).get("enabled"):
        return None
    return create_tv_controller(config)
