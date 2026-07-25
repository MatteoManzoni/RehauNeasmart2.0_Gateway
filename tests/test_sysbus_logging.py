"""Tests for narrow pymodbus SYSBUS log filtering."""

import logging

import main


def record(message):
    return logging.LogRecord(
        "pymodbus.logging",
        logging.ERROR,
        __file__,
        1,
        message,
        (),
        None,
    )


def test_unconfigured_slave_noise_is_suppressed():
    log_filter = main.PymodbusSysbusNoiseFilter([240, 241])

    assert not log_filter.filter(record("requested slave does not exist: 16"))
    assert log_filter.filter(record("requested slave does not exist: 240"))
    assert log_filter.stats() == {
        "enabled": True,
        "missing_slave": 1,
        "short_frame": 0,
        "total": 1,
    }


def test_only_known_short_frame_error_is_suppressed():
    log_filter = main.PymodbusSysbusNoiseFilter([240, 241])

    assert not log_filter.filter(
        record(
            'Unknown exception "unpack requires a buffer of 4 bytes" '
            "on stream ('192.0.2.1', 1234) forcing disconnect"
        )
    )
    assert log_filter.filter(
        record('Unknown exception "connection reset" on stream 1 forcing disconnect')
    )


def test_filter_can_be_disabled_and_reconfigured():
    main.configure_pymodbus_logging([240, 241], True)
    assert main.pymodbus_noise_stats()["enabled"]

    main.configure_pymodbus_logging([240, 241], False)
    assert main.pymodbus_noise_stats() == {
        "enabled": False,
        "missing_slave": 0,
        "short_frame": 0,
        "total": 0,
    }
