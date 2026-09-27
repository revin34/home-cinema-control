from __future__ import annotations

from collections.abc import Mapping, Sequence

from home_cinema_control.playback.startup.models import PlayerMediaFileLocation


class PlayerMediaFileLocationError(ValueError):
    pass


def resolve_player_media_file_location(
    *,
    emby_media_path: str,
    playback_file_format: str,
    path_mappings: Sequence[Mapping[str, str]],
) -> PlayerMediaFileLocation:
    player_path, network_protocol = _apply_path_mappings(emby_media_path, path_mappings)
    player_path = _normalize_path_separators(player_path)

    return _parse_player_media_file_location(
        player_path=player_path,
        playback_file_format=playback_file_format,
        network_protocol=network_protocol,
    )


def matching_path_mappings(
    media_path: str,
    path_mappings: Sequence[Mapping[str, str]],
) -> list[Mapping[str, str]]:
    """The path mappings whose source path applies to media_path.

    Same matching rule as the translation in _apply_path_mappings, so the
    mappings reported here are exactly the ones that produced the player path.
    """
    return [
        mapping
        for mapping in path_mappings
        if mapping.get("source_path") and mapping["source_path"] in media_path
    ]


def _apply_path_mappings(
    media_path: str,
    path_mappings: Sequence[Mapping[str, str]],
) -> tuple[str, str | None]:
    player_path = media_path
    network_protocol = None

    for mapping in path_mappings:
        emby_path = mapping["source_path"]
        if emby_path in player_path:
            player_path = player_path.replace(emby_path, mapping["player_path"])
            network_protocol = mapping.get("protocol") or network_protocol

    return player_path, network_protocol


def _normalize_path_separators(path: str) -> str:
    return path.replace("\\\\", "\\").replace("\\", "/")


def _parse_player_media_file_location(
    *,
    player_path: str,
    playback_file_format: str,
    network_protocol: str | None = None,
) -> PlayerMediaFileLocation:
    path_parts = player_path.strip("/").split("/")

    if len(path_parts) < 3:
        raise PlayerMediaFileLocationError(
            f"Player media path must include server, folder and file: {player_path}"
        )

    content_server = path_parts[0]
    content_directory = "/".join(path_parts[1:-1])
    playback_file_name = path_parts[-1]

    if not content_server or not content_directory or not playback_file_name:
        raise PlayerMediaFileLocationError(
            f"Player media path must include server, folder and file: {player_path}"
        )

    return PlayerMediaFileLocation(
        content_server=content_server,
        content_directory=content_directory,
        playback_file_name=playback_file_name,
        playback_file_format=playback_file_format,
        network_protocol=network_protocol,
    )
