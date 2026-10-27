"""Constants for the parkeerservice integration."""

from datetime import time, timedelta
from typing import Final

DOMAIN: Final = "parkeerservice"

CONF_CARS: Final = "cars"
CONF_DESCRIPTION: Final = "description"
CONF_LICENSE_PLATE: Final = "license_plate"
CONF_PERMIT: Final = "permit"

# One request per interval for all cars together; toggling a switch refreshes immediately.
UPDATE_INTERVAL: Final = timedelta(minutes=2)

# Planned end of a new session when the user did not set one: end of the day.
DEFAULT_END: Final = time(23, 59, 59)
