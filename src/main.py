import os
import re
import time
import hashlib
import requests
import logging
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, NoSuchElementException

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

EXTENSION_ID = 'ilehaonighjijnmpnagapkhpcdbhclfg'
CRX_URL_TEMPLATE = "https://clients2.google.com/service/update2/crx?response=redirect&prodversion=98.0.4758.102&acceptformat=crx2,crx3&x=id%3D{extension_id}%26uc&nacl_arch=x86-64"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"

USER = os.getenv('GRASS_USER', '')
PASSW = os.getenv('GRASS_PASS', '')
ALLOW_DEBUG = os.getenv('ALLOW_DEBUG', 'False').lower() == 'true'

if not USER or not PASSW:
    print('Please set GRASS_USER and GRASS_PASS env variables')
    exit()

if ALLOW_DEBUG:
    print('Debugging is enabled! This will generate a screenshot and console logs on error!')

# Download extension
def download_extension(extension_id):
    url = CRX_URL_TEMPLATE.format(extension_id=extension_id)
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, stream=True, headers=headers)
    with open("grass.crx", "wb") as fd:
        for chunk in response.iter_content(chunk_size=128):
            fd.write(chunk)
    if ALLOW_DEBUG:
        md5 = hashlib.md5(open('grass.crx', 'rb').read()).hexdigest()
        print(f'Extension MD5: {md5}')

# Generate error report
def generate_error_report(driver):
    if not ALLOW_DEBUG:
        return
    
    driver.save_screenshot('error.png')
    logs = driver.get_log('browser')
    with open('error.log', 'w') as f:
        for log in logs:
            f.write(str(log) + '\n')

    files = {'file': ('error.png', open('error.png', 'rb'), 'image/png')}
    response = requests.post('https://imagebin.ca/upload.php', files=files)
    print(response.text)
    print('Error report generated! Provide the above information to the developer for debugging purposes.')

# Download and install extension
print('Downloading extension...')
download_extension(EXTENSION_ID)
print('Downloaded! Installing extension and driver manager...')

# Set Chrome options
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--disable-dev-shm-usage")
options.add_argument('--no-sandbox')
options.add_extension('grass.crx')

# Initialize Chrome driver
print('Installed! Starting...')
try:
    driver = webdriver.Chrome(options=options)
except WebDriverException:
    print('Could not start with Manager! Trying to default to manual path...')
    try:
        driver_path = "/usr/bin/chromedriver"
        service = ChromeService(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except WebDriverException:
        print('Could not start with manual path! Exiting...')
        exit()

# Open login page and wait for login form
print('Started! Logging in...')
driver.get('https://app.getgrass.io/')

try:
    wait = WebDriverWait(driver, 30)
    user = wait.until(EC.presence_of_element_located((By.NAME, 'user')))
    passw = wait.until(EC.presence_of_element_located((By.NAME, 'password')))
    submit = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@type="submit"]')))

    # Fill in login credentials
    user.send_keys(USER)
    passw.send_keys(PASSW)
    submit.click()

    # Wait for dashboard
    dashboard = wait.until(EC.presence_of_element_located((By.XPATH, '//*[contains(text(), "Dashboard")]')))
    print('Logged in! Waiting for connection...')
    
    driver.get(f'chrome-extension://{EXTENSION_ID}/index.html')

    # Wait for connection
    connection = wait.until(EC.presence_of_element_located((By.XPATH, '//*[contains(text(), "Open dashboard")]')))
    print('Connected! Starting API...')
except Exception as e:
    print(f'Error during login or connection: {str(e)}')
    generate_error_report(driver)
    driver.quit()
    exit()

app = Flask(__name__)

@app.route('/')
def get():
    try:
        network_quality_text = driver.find_element('xpath', '//*[contains(text(), "Network quality")]').text
        network_quality = int(re.findall(r'\d+', network_quality_text)[0])
        connected = network_quality > 0
    except Exception as e:
        network_quality = connected = False
        print(f'Could not get network quality: {str(e)}')
        generate_error_report(driver)

    try:
        token = driver.find_element('xpath', '//*[@alt="token"]').find_element('xpath', 'following-sibling::div').text
        epoch_earnings = token
    except Exception as e:
        epoch_earnings = False
        print(f'Could not get earnings: {str(e)}')
        generate_error_report(driver)

    return {'connected': connected, 'network_quality': network_quality, 'epoch_earnings': epoch_earnings}

if __name__ == "__main__":
    from gunicorn.app.base import BaseApplication

    class FlaskApplication(BaseApplication):
        def __init__(self, app):
            self.application = app
            super().__init__()

        def load_config(self):
            self.cfg.set('bind', '0.0.0.0:80')
            self.cfg.set('workers', 1)
            self.cfg.set('timeout', 120)

        def load(self):
            return self.application

    FlaskApplication(app).run()

driver.quit()
