from .factory import create_lighting_controller


def turn_lighting_on(config):
    return create_lighting_controller(config).turn_on()


def turn_lighting_off(config):
    return create_lighting_controller(config).turn_off()
