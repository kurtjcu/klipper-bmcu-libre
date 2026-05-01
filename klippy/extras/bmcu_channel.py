"""
bmcu_channel.py — Klipper config prefix handler for [bmcu_channel N] sections.

Klipper resolves config section prefixes by module filename. This module
exists so that [bmcu_channel 0] loads correctly, delegating to BmcuChannel
defined in bmcu_feeder.py.
"""

from extras.bmcu_feeder import BmcuChannel


def load_config_prefix(config):
    return BmcuChannel(config)
