"""Script to trigger installation of chrome driver during docker image build"""
import logging
import os

from webdriver_manager.chrome import ChromeDriverManager

from flathunter.logging_fh import wdm_logger

# Cache the driver manager to local folder so that gunicorn can find it
os.environ['WDM_LOCAL'] = '1'
wdm_logger.setLevel(logging.INFO)

ChromeDriverManager().install()
