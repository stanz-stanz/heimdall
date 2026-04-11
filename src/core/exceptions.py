"""Heimdall shared exception types."""


class ScanToolError(Exception):
    """Scan tool subprocess failure, timeout, or missing binary."""


class DeliveryError(Exception):
    """Telegram send or approval failure."""


class ConfigError(Exception):
    """Missing or invalid configuration file."""
