"""Tests for REHAU DPT 9 temperature handling."""

import dpt_9001


def test_temperature_round_trip():
    assert dpt_9001.unpack_temperature(dpt_9001.pack_dpt9001(21.5)) == 21.5


def test_rehau_invalid_temperature_sentinels_are_missing():
    assert dpt_9001.unpack_temperature(0x7FFF) is None
    assert dpt_9001.unpack_temperature(0x8116) is None


def test_implausible_temperature_is_missing():
    assert dpt_9001.unpack_temperature(dpt_9001.pack_dpt9001(150)) is None
