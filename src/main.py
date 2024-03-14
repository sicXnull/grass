import os
import re
import time
import hashlib
import requests
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import WebDriverException, NoSuchElementException

extensionId = 'ilehaonighjijnmpnagapkhpcdbhclfg'
CRX_URL = "https://clients2.google.com/service/update2/crx?response=redirect&prodversion=98.0.4758.102&acceptformat=crx2,crx3&x=id%3D~~~~%26uc&nacl_arch=x86-64"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"

try:
    USER = os.environ['GRASS_USER']
    PASSW = os.environ['GRASS_PASS']
except KeyError:
    USER = ''
    PASSW = ''

ALLOW_DEBUG = os.environ.get('ALLOW_DEBUG', 'False').lower() == 'true'

# Check if environment variables are set
if USER == '' or PASSW == '':
    print('Please set GRASS_USER and GRASS_PASS env variables')
    exit()

# Debugging enabled message
if ALLOW_DEBUG:
    print('Debugging is enabled! This will generate a screenshot and console logs on error!')

# Download extension
def download_extension(extension_id):
    url = CRX_URL.replace("~~~~", extension_id)
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, stream=True, headers=headers)
    with open("grass.crx", "wb") as fd:
        for chunk in r.iter_content(chunk_size=128):
            fd.write(chunk)
    if ALLOW_DEBUG:
        md5 = hashlib.md5(open('grass.crx', 'rb').read()).hexdigest()
        print('Extension MD5: ' + md5)

# Generate error report
def generate_error_report(driver):
    if not ALLOW_DEBUG:
        return
    
    driver.save_screenshot('error.png')
    logs = driver.get_log('browser')
    with open('error.log', 'w') as f:
        for log in logs:
            f.write(str(log))
            f.write('\n')

    url = 'https://imagebin.ca/upload.php'
    files = {'file': ('error.png', open('error.png', 'rb'), 'image/png')}
    response = requests.post(url, files=files)
    print(response.text)
    print('Error report generated! Provide the above information to the developer for debugging purposes.')

# Download extension
print('Downloading extension...')
download_extension(extensionId)
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
except WebDriverException as e:
    print('Could not start with Manager! Trying to default to manual path...')
    try:
        driver_path = "/usr/bin/chromedriver"
        service = ChromeService(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except WebDriverException as e:
        print('Could not start with manual path! Exiting...')
        exit()

# Open login page
print('Started! Logging in...')
driver.get('https://app.getgrass.io/')

# Wait for login form
for _ in range(15):
    try:
        driver.find_element('xpath', '//*[@name="user"]')
        driver.find_element('xpath', '//*[@name="password"]')
        driver.find_element('xpath', '//*[@type="submit"]')
        break
    except NoSuchElementException:
        time.sleep(1)
        print('Loading login form...')

else:
    print('Could not load login form! Exiting...')
    generate_error_report(driver)
    driver.quit()
    exit()

# Fill in login credentials
user = driver.find_element('xpath', '//*[@name="user"]')
passw = driver.find_element('xpath', '//*[@name="password"]')
submit = driver.find_element('xpath', '//*[@type="submit"]')

user.send_keys(USER)
passw.send_keys(PASSW)
submit.click()

# Wait for dashboard
for _ in range(30):
    try:
        driver.find_element('xpath', '//*[contains(text(), "Dashboard")]')
        break
    except NoSuchElementException:
        time.sleep(1)
        print('Logging in...')

else:
    print('Could not login! Double Check your username and password! Exiting...')
    generate_error_report(driver)
    driver.quit()
    exit()

print('Logged in! Waiting for connection...')
driver.get('chrome-extension://'+extensionId+'/index.html')

# Wait for connection
for _ in range(30):
    try:
        driver.find_element('xpath', '//*[contains(text(), "Open dashboard")]')
        break
    except NoSuchElementException:
        time.sleep(1)
        print('Loading connection...')

else:
    print('Could not load connection! Exiting...')
    generate_error_report(driver)
    driver.quit()
    exit()

print('Connected! Starting API...')

# Initialize Flask app
app = Flask(__name__)

# API route
@app.route('/')
def get():
    try:
        network_quality = re.search(r'\d+', driver.find_element('xpath', '//*[contains(text(), "Network quality")]').text).group()
    except:
        network_quality = False
        print('Could not get network quality!')
        generate_error_report(driver)

    try:
        epoch_earnings = driver.find_element('xpath', '//*[@alt="token"]/following-sibling::div').text
    except:
        epoch_earnings = False
        print('Could not get earnings!')
        generate_error_report(driver)

    try:
        badges = driver.find_elements('xpath', '//*[@class="chakra-badge"]')
        connected = any('Connected' in badge.find_element_by_xpath('child::div').text for badge in badges)
    except:
        connected = False
        print('Could not get connection status!')
        generate_error_report(driver)

    return {'connected': connected, 'network_quality': network_quality, 'epoch_earnings': epoch_earnings}

# Run Flask app
app.run(host='0.0.0.0', port=80, debug=False)

# Quit driver after Flask app is terminated
driver.quit()

app.run(host='0.0.0.0',port=80, debug=False)
driver.quit()
