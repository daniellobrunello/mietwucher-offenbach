"""Utilities for dealing with times."""
from time import sleep
from datetime import datetime

from flathunter.logging_fh import logger


def is_current_time_between(time_from, time_till):
    """Returns True if current time is in the given time span."""
    if time_from == time_till:
        return False
    current_time = datetime.now().time()
    if time_from < time_till:
        return time_from <= current_time < time_till
    return current_time >= time_from or current_time < time_till


def get_time_span_in_secs(time_a, time_b):
    """Convert time to seconds since midnight and return the time span time_a to time_b."""
    a_secs = (time_a.hour * 60 + time_a.minute) * 60 + time_a.second
    b_secs = (time_b.hour * 60 + time_b.minute) * 60 + time_b.second
    if a_secs < b_secs:
        return b_secs - a_secs
    return (24*60*60) - a_secs + b_secs


def wait_during_period(time_from, time_till):
    """Waits for the end of the pause period if necessary."""
    if is_current_time_between(time_from, time_till):
        logger.info("Paused loop. Waiting till %s.", time_till)
        sleep(get_time_span_in_secs(datetime.now().time(), time_till))
