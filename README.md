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

Every car gets a switch and an end time. Turning the switch on starts a session until the end time (default 23:59, set it with the `time.set_value` action or on the dashboard), turning it off stops it. While a session is running the end time shows when it ends. All cars share one login and one request every 2 minutes. If your password changes, Home Assistant asks for the new one.

## Development

```sh
uv sync
uv run pre-commit install
uv run pytest        # tests with coverage (min. 95%)
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Releases are automated with [release-please](https://github.com/googleapis/release-please): use [conventional commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, ...) on `main`. A release PR with the changelog and version bump is kept up to date; merging it tags the release and attaches the zip for HACS.
