#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Flathunter - search for flats by crawling property portals. This is the main 
   command-line executable, for running on the console. To run as a webservice, 
   look at main.py"""

import time
from datetime import time as dtime

from flathunter.argument_parser import parse
from flathunter.logging_fh import logger, configure_logging
from flathunter.idmaintainer_mongo import IdMaintainer
from flathunter.hunter import Hunter
from flathunter.config import Config
from flathunter.time_utils import wait_during_period

__author__ = "Jan Harrie"
__version__ = "1.0"
__maintainer__ = "Nody"
__email__ = "harrymcfly@protonmail.com"
__status__ = "Production"


def launch_flat_hunt(config):
    """Starts the crawler / notification loop"""
    import os
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = "flathunter"
    id_watch = IdMaintainer(MONGO_URI, DB_NAME)

    time_from = dtime.fromisoformat(config.loop_pause_from())
    time_till = dtime.fromisoformat(config.loop_pause_till())

    wait_during_period(time_from, time_till)

    hunter = Hunter(config, id_watch)
    hunter.hunt_flats()
    counter = 0

    while config.loop_is_active():
        wait_during_period(time_from, time_till)

        counter += 1
        time.sleep(config.loop_period_seconds())
        hunter.hunt_flats()


def main():
    """Processes command-line arguments, loads the config, launches the flathunter"""
    # load config
    args = parse()
    config_handle = args.config
    if config_handle is not None:
        config = Config(config_handle.name)
    else:
        config = Config()

    # setup logging
    configure_logging(config)

    # initialize search plugins for config
    config.init_searchers()

    # check config
    if len(config.target_urls()) == 0:
        logger.error("No URLs configured. Starting like this would be pointless...")
        return

    # start hunting for flats
    launch_flat_hunt(config)


if __name__ == "__main__":
    main()
