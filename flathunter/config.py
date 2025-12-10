"""Wrap configuration options as an object"""
import os
from typing import Optional, Dict, Any, List, Callable

import json
import yaml
from dotenv import load_dotenv

from flathunter.captcha.captcha_solver import CaptchaSolver
from flathunter.captcha.imagetyperz_solver import ImageTyperzSolver
from flathunter.captcha.twocaptcha_solver import TwoCaptchaSolver
from flathunter.captcha.capmonster_solver import CapmonsterSolver
from flathunter.crawler.kleinanzeigen import Kleinanzeigen
from flathunter.crawler.immobilienscout import Immobilienscout
from flathunter.crawler.immowelt import Immowelt
from flathunter.filter import Filter
from flathunter.logging_fh import logger
from flathunter.exceptions import ConfigException

load_dotenv()


def _read_env(key: str, fallback: Optional[str] = None) -> Callable[[], Optional[str]]:
    """ read the given key from environment"""
    return lambda: os.environ.get(key, fallback)


class Env:
    """Reads data from the environment"""

    # Captcha setup
    FLATHUNTER_2CAPTCHA_KEY = _read_env("FLATHUNTER_2CAPTCHA_KEY")
    FLATHUNTER_IMAGETYPERZ_TOKEN = _read_env("FLATHUNTER_IMAGETYPERZ_TOKEN")
    FLATHUNTER_CAPMONSTER_KEY = _read_env("FLATHUNTER_CAPMONSTER_KEY")
    FLATHUNTER_HEADLESS_BROWSER = _read_env("FLATHUNTER_HEADLESS_BROWSER")
    FLATHUNTER_IS24_COOKIE = _read_env("FLATHUNTER_IS24_COOKIE")

    # Generic Config
    FLATHUNTER_TARGET_URLS = _read_env("FLATHUNTER_TARGET_URLS")
    FLATHUNTER_DATABASE_LOCATION = _read_env("FLATHUNTER_DATABASE_LOCATION")
    FLATHUNTER_VERBOSE_LOG = _read_env("FLATHUNTER_VERBOSE_LOG")
    FLATHUNTER_LOOP_PERIOD_SECONDS = _read_env(
        "FLATHUNTER_LOOP_PERIOD_SECONDS")
    FLATHUNTER_LOOP_PAUSE_FROM = _read_env("FLATHUNTER_LOOP_PAUSE_FROM")
    FLATHUNTER_LOOP_PAUSE_TILL = _read_env("FLATHUNTER_LOOP_PAUSE_TILL")
    FLATHUNTER_MESSAGE_FORMAT = _read_env("FLATHUNTER_MESSAGE_FORMAT")

    # Website setup
    FLATHUNTER_WEBSITE_SESSION_KEY = _read_env(
        "FLATHUNTER_WEBSITE_SESSION_KEY")
    FLATHUNTER_WEBSITE_DOMAIN = _read_env("FLATHUNTER_WEBSITE_DOMAIN")
    FLATHUNTER_WEBSITE_BOT_NAME = _read_env("FLATHUNTER_WEBSITE_BOT_NAME")

    # Filters
    FLATHUNTER_FILTER_EXCLUDED_TITLES = _read_env(
        "FLATHUNTER_FILTER_EXCLUDED_TITLES")
    FLATHUNTER_FILTER_MIN_PRICE = _read_env("FLATHUNTER_FILTER_MIN_PRICE")
    FLATHUNTER_FILTER_MAX_PRICE = _read_env("FLATHUNTER_FILTER_MAX_PRICE")
    FLATHUNTER_FILTER_MIN_SIZE = _read_env("FLATHUNTER_FILTER_MIN_SIZE")
    FLATHUNTER_FILTER_MAX_SIZE = _read_env("FLATHUNTER_FILTER_MAX_SIZE")
    FLATHUNTER_FILTER_MIN_ROOMS = _read_env("FLATHUNTER_FILTER_MIN_ROOMS")
    FLATHUNTER_FILTER_MAX_ROOMS = _read_env("FLATHUNTER_FILTER_MAX_ROOMS")
    FLATHUNTER_FILTER_MAX_PRICE_PER_SQUARE = _read_env(
        "FLATHUNTER_FILTER_MAX_PRICE_PER_SQUARE")


def elide(string):
    """Obfuscate the value of a string for debug purposes"""
    if string is None or len(string) == 0:
        return None
    if len(string) < 6:
        return "x" * len(string)
    blanks = "x" * (len(string)-6)
    return f"{string[0:3]}{blanks}{string[-3:]}"


class YamlConfig:  # pylint: disable=too-many-public-methods
    """Generic config object constructed from nested dictionaries"""

    DEFAULT_MESSAGE_FORMAT = """{title}
Zimmer: {rooms}
Größe: {size}
Preis: {price}

{url}"""

    def __init__(self, config=None):
        if config is None:
            config = {}
        self.config = config
        self.__searchers__ = []
        self.check_deprecated()

    def __iter__(self):
        """Emulate dictionary"""
        return self.config.__iter__()

    def __getitem__(self, value):
        """Emulate dictionary"""
        return self.config[value]

    def init_searchers(self):
        """Initialize search plugins"""
        self.__searchers__ = [
            Immobilienscout(self),
            Kleinanzeigen(self),
            Immowelt(self),
        ]

    def check_deprecated(self):
        """Notifies user of deprecated config items"""
        captcha_config = self.config.get("captcha")
        if captcha_config is not None:
            if captcha_config.get("imagetypers") is not None:
                logger.warning(
                    'Captcha configuration for "imagetypers" (captcha/imagetypers) has been '
                    'renamed to "imagetyperz". '
                    'We found an outdated entry, which has to be renamed accordingly, in order '
                    'to be detected again.'
                )
            if captcha_config.get("driver_path") is not None:
                logger.warning(
                    'Captcha configuration for "driver_path" (captcha/driver_path) is no longer '
                    'required, as driver setup has been automated.'
                )

    def get(self, key, value=None):
        """Emulate dictionary"""
        return self.config.get(key, value)

    def _read_yaml_path(self, path, default_value):
        """Resolve a dotted variable path in nested dictionaries"""
        config = self.config
        parts = path.split('.')
        while len(parts) > 1 and config is not None:
            config = config.get(parts[0], {})
            parts = parts[1:]
        if config is None:
            return default_value
        res = config.get(parts[0], default_value)
        if res is None:
            return default_value
        return res

    def set_searchers(self, searchers):
        """Update the active search plugins"""
        self.__searchers__ = searchers

    def searchers(self):
        """Get the list of search plugins"""
        return self.__searchers__

    def get_filter(self):
        """Read the configured filter"""
        builder = Filter.builder()
        builder.read_config(self)
        return builder.build()

    def captcha_enabled(self):
        """Check if captcha is configured"""
        return self._get_captcha_solver() is not None

    def get_captcha_checkbox(self) -> bool:
        """Check if captcha checkbox support is needed"""
        return self._read_yaml_path('captcha.checkbox', False)

    def get_captcha_afterlogin_string(self):
        """Check if afterlogin string should be presented"""
        return self._read_yaml_path('captcha.afterlogin_string', '')

    def database_location(self):
        """Return the location of the database folder"""
        config_database_location = self._read_yaml_path('database_location', None)
        if config_database_location is not None:
            return config_database_location
        return os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + "/..")

    def target_urls(self) -> List[str]:
        """List of target URLs for crawling"""
        return self._read_yaml_path('urls', [])

    def verbose_logging(self):
        """Return true if logging should be verbose"""
        return self._read_yaml_path('verbose', None) is not None

    def debug_save_pages(self):
        """Return true if debug mode is enabled to save downloaded pages"""
        return self._read_yaml_path('debug.save_pages', False)

    def debug_output_directory(self):
        """Return the directory path for saving debug HTML pages"""
        return self._read_yaml_path('debug.output_directory', './debug_pages')

    def loop_is_active(self):
        """Return true if flathunter should be crawling in a loop"""
        return self._read_yaml_path('loop.active', False)

    def loop_period_seconds(self):
        """Number of seconds to wait between crawls when looping"""
        return self._read_yaml_path('loop.sleeping_time', 60 * 10)

    def loop_pause_from(self):
        """Start time of loop pause"""
        return self._read_yaml_path('loop.pause.from', "00:00")

    def loop_pause_till(self):
        """End time of loop pause"""
        return self._read_yaml_path('loop.pause.till', "00:00")

    def has_website_config(self):
        """True if the flathunter website configuration is present"""
        return 'website' in self.config

    def website_session_key(self):
        """Secret session key for the flathunter website"""
        return self._read_yaml_path('website.session_key', None)

    def website_domain(self):
        """Domain that the flathunter website is hosted at"""
        return self._read_yaml_path('website.domain', None)

    def website_bot_name(self):
        """Name of the bot used by the flathunter website"""
        return self._read_yaml_path('website.bot_name', None)

    def message_format(self):
        """Format of the message to send in user notifications"""
        config_format = self._read_yaml_path('message', None)
        if config_format is not None:
            return config_format
        return self.DEFAULT_MESSAGE_FORMAT

    def _get_imagetyperz_token(self):
        """API Token for Imagetyperz"""
        return self._read_yaml_path("captcha.imagetyperz.token", "")

    def get_twocaptcha_key(self) -> str:
        """API Token for 2captcha"""
        return self._read_yaml_path("captcha.2captcha.api_key", "")

    def get_capmonster_key(self) -> str:
        """API Token for Capmonster"""
        return self._read_yaml_path("captcha.capmonster.api_key", "")

    def _get_captcha_solver(self) -> Optional[CaptchaSolver]:
        """Get configured captcha solver"""
        imagetyperz_token = self._get_imagetyperz_token()
        if imagetyperz_token:
            return ImageTyperzSolver(imagetyperz_token)

        twocaptcha_api_key = self.get_twocaptcha_key()
        if twocaptcha_api_key:
            return TwoCaptchaSolver(twocaptcha_api_key)

        capmonster_api_key = self.get_capmonster_key()
        if capmonster_api_key:
            return CapmonsterSolver(capmonster_api_key)

        return None

    def get_captcha_solver(self) -> CaptchaSolver:
        """Return the configured captcha solver (or raise exception)"""
        solver = self._get_captcha_solver()
        if solver is not None:
            return solver
        raise ConfigException("No captcha solver configured properly.")

    def captcha_driver_arguments(self):
        """The list of driver arguments for Selenium / Webdriver"""
        return self._read_yaml_path('captcha.driver_arguments', [])

    def use_proxy(self):
        """Check if proxy is configured"""
        return "use_proxy_list" in self.config and self.config["use_proxy_list"]

    def set_keys(self, dict_keys: Dict[str, Any]):
        """Update the config keys based on the content of the dictionary passed"""
        self.config.update(dict_keys)

    def _get_filter_config(self, key: str) -> Optional[Any]:
        return (self.config.get("filters", {}) or {}).get(key, None)

    def excluded_titles(self):
        """Return the configured list of titles to exclude"""
        if "excluded_titles" in self.config:
            return self.config["excluded_titles"]
        return self._get_filter_config("excluded_titles") or []

    def min_price(self):
        """Return the configured minimum price"""
        return self._get_filter_config("min_price")

    def max_price(self):
        """Return the configured maximum price"""
        return self._get_filter_config("max_price")

    def min_size(self):
        """Return the configured minimum size"""
        return self._get_filter_config("min_size")

    def max_size(self):
        """Return the configured maximum size"""
        return self._get_filter_config("max_size")

    def min_rooms(self):
        """Return the configured minimum number of rooms"""
        return self._get_filter_config("min_rooms")

    def max_rooms(self):
        """Return the configured maximum number of rooms"""
        return self._get_filter_config("max_rooms")

    def max_price_per_square(self):
        """Return the configured maximum price per square meter"""
        return self._get_filter_config("max_price_per_square")

    def immoscout_cookie(self):
        """Return the precalculated immoscout cookie"""
        return self._read_yaml_path('immoscout_cookie', None)

    def __repr__(self):
        return json.dumps({
            "captcha_enabled": self.captcha_enabled(),
            "captcha_driver_arguments": self.captcha_driver_arguments(),
            "captcha_solver": type(self._get_captcha_solver()).__name__,
            "imagetyperz_token": elide(self._get_imagetyperz_token()),
            "twocaptcha_key": elide(self.get_twocaptcha_key()),
            "target_urls": self.target_urls(),
            "use_proxy": self.use_proxy(),
        })


class CaptchaEnvironmentConfig(YamlConfig):
    """Mixin to add environment-variable captcha support to config object"""

    def _get_imagetyperz_token(self):
        return Env.FLATHUNTER_IMAGETYPERZ_TOKEN() or super()._get_imagetyperz_token()  # pylint: disable=no-member

    def get_twocaptcha_key(self) -> str:
        """Return the currently configured 2captcha API key"""
        return Env.FLATHUNTER_2CAPTCHA_KEY() or super().get_twocaptcha_key()  # pylint: disable=no-member

    def get_capmonster_key(self) -> str:
        """Return the currently configured Capmonster API key"""
        return Env.FLATHUNTER_CAPMONSTER_KEY() or super().get_capmonster_key()

    def captcha_driver_arguments(self):
        """The list of driver arguments for Selenium / Webdriver"""
        if Env.FLATHUNTER_HEADLESS_BROWSER() is not None:
            return [
                "--no-sandbox",
                "--headless",
                "--disable-gpu",
                "--remote-debugging-port=9222",
                "--disable-dev-shm-usage",
                "--window-size=1024,768"
            ]
        return super().captcha_driver_arguments()  # pylint: disable=no-member


class Config(CaptchaEnvironmentConfig):  # pylint: disable=too-many-public-methods
    """Class to represent flathunter configuration, built from a file, supporting
    environment variable overrides
    """

    def __init__(self, filename=None):
        if filename is None and Env.FLATHUNTER_TARGET_URLS() is None:
            raise ConfigException(
                "Config file loaction must be specified, or FLATHUNTER_TARGET_URLS must be set")
        if filename is not None:
            logger.info("Using config path %s", filename)
            if not os.path.exists(filename):
                raise ConfigException("No config file found at location %s")
            with open(filename, encoding="utf-8") as file:
                config = yaml.safe_load(file)
        else:
            config = {}
        super().__init__(config)

    def database_location(self):
        """Return the location of the database folder"""
        return Env.FLATHUNTER_DATABASE_LOCATION() or super().database_location()

    def target_urls(self):
        env_urls = Env.FLATHUNTER_TARGET_URLS()
        if env_urls is not None:
            return env_urls.split(';')
        return super().target_urls()

    def verbose_logging(self):
        if Env.FLATHUNTER_VERBOSE_LOG() is not None:
            return True
        return super().verbose_logging()

    def loop_is_active(self):
        if Env.FLATHUNTER_LOOP_PERIOD_SECONDS() is not None:
            return True
        return super().loop_is_active()

    def loop_period_seconds(self):
        env_seconds = Env.FLATHUNTER_LOOP_PERIOD_SECONDS()
        if env_seconds is not None:
            return int(env_seconds)
        return super().loop_period_seconds()

    def loop_pause_from(self):
        env_pause = Env.FLATHUNTER_LOOP_PAUSE_FROM()
        if env_pause is not None:
            return str(env_pause)
        return super().loop_pause_from()

    def loop_pause_till(self):
        env_until = Env.FLATHUNTER_LOOP_PAUSE_TILL()
        if env_until is not None:
            return str(env_until)
        return super().loop_pause_till()

    def has_website_config(self):
        if Env.FLATHUNTER_WEBSITE_SESSION_KEY() is not None:
            return True
        return super().has_website_config()

    def website_session_key(self):
        return Env.FLATHUNTER_WEBSITE_SESSION_KEY() or super().website_session_key()

    def website_domain(self):
        return Env.FLATHUNTER_WEBSITE_DOMAIN() or super().website_domain()

    def website_bot_name(self):
        return Env.FLATHUNTER_WEBSITE_BOT_NAME() or super().website_bot_name()

    def message_format(self):
        env_message_format = Env.FLATHUNTER_MESSAGE_FORMAT()
        if env_message_format is not None:
            return '\n'.join(env_message_format.split('#CR#'))
        return super().message_format()

    def excluded_titles(self):
        env_filter = Env.FLATHUNTER_FILTER_EXCLUDED_TITLES()
        if env_filter is not None:
            return env_filter.split(";")
        return super().excluded_titles()

    def min_price(self):
        env_price = Env.FLATHUNTER_FILTER_MIN_PRICE()
        if env_price is not None:
            return int(env_price)
        return super().min_price()

    def max_price(self):
        env_price = Env.FLATHUNTER_FILTER_MAX_PRICE()
        if env_price is not None:
            return int(env_price)
        return super().max_price()

    def min_size(self):
        env_size = Env.FLATHUNTER_FILTER_MIN_SIZE()
        if env_size is not None:
            return int(env_size)
        return super().min_size()

    def max_size(self):
        env_size = Env.FLATHUNTER_FILTER_MAX_SIZE()
        if env_size is not None:
            return int(env_size)
        return super().max_size()

    def min_rooms(self):
        env_rooms = Env.FLATHUNTER_FILTER_MIN_ROOMS()
        if env_rooms is not None:
            return int(env_rooms)
        return super().min_rooms()

    def max_rooms(self):
        env_rooms = Env.FLATHUNTER_FILTER_MAX_ROOMS()
        if env_rooms is not None:
            return int(env_rooms)
        return super().max_rooms()

    def max_price_per_square(self):
        env_price = Env.FLATHUNTER_FILTER_MAX_PRICE_PER_SQUARE()
        if env_price is not None:
            return float(env_price)
        return super().max_price_per_square()

    def immoscout_cookie(self):
        return Env.FLATHUNTER_IS24_COOKIE() or super().immoscout_cookie()
