"""Chrome needs some special handling to work out where the correct
binary is, to attach the correct selenium chromedriver, and to set
the correct version number"""
import os
import re
import subprocess
from typing import List
from sys import platform
import undetected_chromedriver as uc

from flathunter.logging_fh import logger
from flathunter.exceptions import ChromeNotFound

CHROME_VERSION_REGEXP = re.compile(r'.* (\d+\.\d+\.\d+\.\d+)( .*)?')
WINDOWS_CHROME_REG_PATH = r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon'
WINDOWS_CHROME_REG_REGEXP = re.compile(r'\s*version\s*REG_SZ\s*(\d+)\..*')

# Check environment variables first, then fallback to common names
_chrome_env_bin = os.getenv('CHROME_BIN') or os.getenv('CHROME_PATH')
CHROME_BINARY_NAMES = (
    [_chrome_env_bin] if _chrome_env_bin else []
) + ['google-chrome', 'chromium', 'chrome', 'chromium-browser',
     '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']

def get_command_output(args) -> List[str]:
    """Run a command and return stdout"""
    try:
        with subprocess.Popen(args,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    universal_newlines=True) as process:
            if process.stdout is None:
                return []
            return process.stdout.readlines()
    except FileNotFoundError:
        return []

def get_chrome_version() -> int:
    """Determine the correct name for the chrome binary"""
    logger.info(f'Searching for Chrome binary in: {CHROME_BINARY_NAMES}')
    for binary_name in CHROME_BINARY_NAMES:
        try:
            version_output = get_command_output([binary_name, '--version'])
            if not version_output:
                logger.debug(f'No version output for {binary_name}')
                continue
            logger.info(f'Got version output from {binary_name}: {version_output[0].strip()}')
            match = CHROME_VERSION_REGEXP.match(version_output[0])
            if match is None:
                logger.debug(f'Version output did not match expected format')
                continue
            version = int(match.group(1).split('.')[0])
            logger.info(f'Successfully detected Chrome version {version} from {binary_name}')
            return version
        except FileNotFoundError:
            logger.debug(f'Binary not found: {binary_name}')
            pass
    try:
        # on Windows, Chrome doesn't respond to --version, but we can find
        # the version in the registry
        output = get_command_output(
            ['reg', 'query', WINDOWS_CHROME_REG_PATH, '/v', 'version']
        )
        version_matches = (WINDOWS_CHROME_REG_REGEXP.match(l) for l in output)
        version_matches = [m for m in version_matches if m is not None]
        if version_matches:
            return int(version_matches[0].group(1))
    except FileNotFoundError:
        pass
    raise ChromeNotFound()

def get_chrome_driver(driver_arguments):
    """Configure Chrome WebDriver"""
    logger.info('Initializing Chrome WebDriver for crawler...')
    chrome_options = uc.ChromeOptions() # pylint: disable=no-member
    
    # Set binary location from environment variable if available
    chrome_bin = os.getenv('CHROME_BIN') or os.getenv('CHROME_PATH')
    if chrome_bin:
        logger.info(f'Using Chrome binary from environment: {chrome_bin}')
        chrome_options.binary_location = chrome_bin
    
    if driver_arguments is not None:
        for driver_argument in driver_arguments:
            chrome_options.add_argument(driver_argument)
    
    chrome_version = get_chrome_version()
    logger.info(f'Detected Chrome version: {chrome_version}')
    
    # Headless and Docker-friendly arguments
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    # Get chromedriver path from environment or use default
    chromedriver_path = os.getenv('CHROMEDRIVER_PATH')
    
    try:
        # Try with explicit driver path and use_subprocess=False for Docker compatibility
        if chromedriver_path:
            logger.info(f'Using chromedriver from: {chromedriver_path}')
            driver = uc.Chrome(
                version_main=chrome_version, 
                options=chrome_options, 
                headless=True,
                driver_executable_path=chromedriver_path,
                use_subprocess=False
            )
        else:
            driver = uc.Chrome(
                version_main=chrome_version, 
                options=chrome_options, 
                headless=True,
                use_subprocess=False
            )
    except Exception as e:
        logger.warning(f'Failed to initialize with undetected_chromedriver: {e}')
        logger.info('Attempting to use standard Selenium WebDriver as fallback...')
        
        # Fallback to standard Selenium if undetected_chromedriver fails
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        
        if chromedriver_path:
            service = Service(executable_path=chromedriver_path)
        else:
            service = Service()
        
        driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/135.0.0.0 Safari/537.36"
            },
        )

        driver.execute_cdp_cmd('Network.setBlockedURLs',
            {"urls": ["https://api.geetest.com/get.*"]})
        driver.execute_cdp_cmd('Network.enable', {})
    except Exception as e:
        logger.warning(f"Failed to configure CDP commands: {e}")
    
    return driver
