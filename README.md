# parkeerservice

Home Assistant integration (HACS) to start, stop and read parking sessions in parkeerservice.

It is a service used in various cities in the Netherlands, to start parking sessions for visitors for example.

I made this so I could automate the registration with Home Assistant based on car GPS data, as it is often forgotten to register.

> [!WARNING]
> It is made purely for personal usage. As it's made by reverse engineering their web requests, it can stop working at any time.


## Home Assistant

1. Add this repository to HACS as a custom repository (type: Integration) and install it.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Parkeerservice**, then enter your city's portal URL (e.g. `https://parkstart-LOCATION.parkpermit.eu`), email and password.
4. Click **Configure** on the integration to add your cars: name, license plate and permit (picked from a list of your permits).

Every car becomes a switch. Turning it on starts a session until the end of the day, turning it off stops it. All cars share one login and one request every 2 minutes. If your password changes, Home Assistant asks for the new one.

## Development

```sh
uv sync
uv run pre-commit install
uv run pytest        # tests with coverage (min. 95%)
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Releases: bump `version` in `custom_components/parkeerservice/manifest.json` and `pyproject.toml`, then push a tag `vX.Y.Z`. The release workflow checks the tag, runs the checks and publishes a GitHub release with the zip for HACS.
