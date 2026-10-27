"""Constants for the parkeerservice integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "parkeerservice"

CONF_CARS: Final = "cars"
CONF_DESCRIPTION: Final = "description"
CONF_LICENSE_PLATE: Final = "license_plate"
CONF_PERMIT: Final = "permit"

# One request per interval for all cars together; toggling a switch refreshes immediately.
UPDATE_INTERVAL: Final = timedelta(minutes=2)
