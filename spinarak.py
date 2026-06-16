import os
import random
import re
import smtplib
import time
import uuid
from datetime import date, datetime, time as datetime_time
from email.message import EmailMessage

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


NUM_ITERATIONS = 10
NUM_OF_GUESTS = 2
LOCATION = "Osaka"
HITS_DIR = "hits"

TARGET_SLOT_RULES = {
    date(2026, 7, 28): datetime_time(17, 30),
    date(2026, 7, 29): None,
    date(2026, 7, 30): None,
}
CALENDAR_MONTHS_TO_SCAN = {(2026, 6), (2026, 7)}
MAX_CALENDAR_PAGES_TO_SCAN = 2

RESERVATION_URLS = {
    "Tokyo": "https://reserve.pokemon-cafe.jp/",
    "Osaka": "https://osaka.pokemon-cafe.jp/",
}


def get_required_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def wait_random(min_seconds=2, max_seconds=4):
    time.sleep(random.randint(min_seconds, max_seconds))


def parse_calendar_month(page_text):
    match = re.search(r"(\d{4})\s*(?:\u5e74|year)?\s*(\d{1,2})\s*(?:\u6708|month)", page_text, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_calendar_day(cell_text):
    match = re.search(r"\b(\d{1,2})\b", cell_text)
    if not match:
        return None
    return int(match.group(1))


def parse_slot_times(text):
    return [
        datetime.strptime(match, "%H:%M").time()
        for match in re.findall(r"\b\d{1,2}:\d{2}\b", text)
    ]


def is_cell_available(cell_text):
    normalized = cell_text.lower()
    unavailable_markers = ["(full)", "full", "n/a", "no seats", "unavailable", "\u00d7"]
    return bool(normalized.strip()) and not any(marker in normalized for marker in unavailable_markers)


def slot_date_for_cell(cell_text, calendar_month):
    if calendar_month is None:
        return None

    day = parse_calendar_day(cell_text)
    if day is None:
        return None

    try:
        return date(calendar_month[0], calendar_month[1], day)
    except ValueError:
        return None


def visible_calendar_month(driver):
    soup = BeautifulSoup(driver.page_source, "html.parser")
    return parse_calendar_month(soup.get_text(" ", strip=True))


def make_chrome_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1200,1200")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--lang=en-US")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    return webdriver.Chrome(options=chrome_options)


def click_first_available(driver, selectors):
    wait = WebDriverWait(driver, 20)
    last_error = None
    for by, selector in selectors:
        try:
            element = wait.until(EC.element_to_be_clickable((by, selector)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            element.click()
            return True
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return False


def click_next_month(driver):
    selectors = [
        (By.PARTIAL_LINK_TEXT, "Next Month"),
        (By.XPATH, "//*[self::a or self::button][contains(normalize-space(.), 'Next Month')]"),
    ]
    for by, selector in selectors:
        elements = driver.find_elements(by, selector)
        for element in elements:
            if element.is_displayed() and element.is_enabled():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                element.click()
                return True
    return False


def click_next_step(driver):
    selectors = [
        (By.XPATH, "//*[self::button or self::a][contains(normalize-space(.), 'Next Step')]"),
        (By.XPATH, "//*[@type='submit' or @role='button'][contains(@value, 'Next Step')]"),
        (By.XPATH, "//*[self::button or self::a][contains(normalize-space(.), '\u6b21\u3078')]"),
    ]
    return click_first_available(driver, selectors)


def calendar_cells(driver):
    return [
        cell
        for cell in driver.find_elements(By.CSS_SELECTOR, "li")
        if parse_calendar_day(cell.text) is not None
    ]


def find_calendar_cell_by_day(driver, target_day):
    for cell in calendar_cells(driver):
        if parse_calendar_day(cell.text) == target_day and is_cell_available(cell.text):
            return cell
    return None


def has_matching_time(cell_text, earliest_time):
    if earliest_time is None:
        return True

    slot_times = parse_slot_times(cell_text)
    return bool(slot_times) and any(slot_time >= earliest_time for slot_time in slot_times)


def inspect_time_page_for_match(driver, earliest_time):
    if earliest_time is None:
        return True

    body_text = driver.find_element(By.TAG_NAME, "body").text
    slot_times = parse_slot_times(body_text)
    return any(slot_time >= earliest_time for slot_time in slot_times)


def target_slot_matches(driver, cell_text, slot_date):
    earliest_time = TARGET_SLOT_RULES[slot_date]

    if has_matching_time(cell_text, earliest_time):
        return True

    if earliest_time is None:
        return True

    # Some reservation pages reveal times only after choosing a day.
    navigated_to_time_page = False
    try:
        cell = find_calendar_cell_by_day(driver, slot_date.day)
        if cell is None:
            return False
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell)
        cell.click()
        wait_random()
        click_next_step(driver)
        navigated_to_time_page = True
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        return inspect_time_page_for_match(driver, earliest_time)
    finally:
        if navigated_to_time_page:
            driver.back()
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))


def find_available_target_slots(driver):
    available_slots = []

    for scan_count in range(MAX_CALENDAR_PAGES_TO_SCAN):
        calendar_month = visible_calendar_month(driver)
        if calendar_month in CALENDAR_MONTHS_TO_SCAN:
            cell_texts = [cell.text.strip() for cell in calendar_cells(driver)]
            for cell_text in cell_texts:
                slot_date = slot_date_for_cell(cell_text, calendar_month)
                if slot_date not in TARGET_SLOT_RULES:
                    continue
                if not is_cell_available(cell_text):
                    continue
                if target_slot_matches(driver, cell_text, slot_date):
                    available_slots.append(f"{slot_date.isoformat()} {cell_text}")

        if calendar_month == (2026, 7):
            break
        if scan_count + 1 >= MAX_CALENDAR_PAGES_TO_SCAN:
            break
        if not click_next_month(driver):
            break
        wait_random()

    return available_slots


def send_email(avail_slots, filename):
    sender_email = get_required_env("GMAIL_SENDER")
    receiver_email = get_required_env("GMAIL_RECIPIENT")
    receiver_email2 = os.environ.get("GMAIL_RECIPIENT_2", "").strip()
    password = get_required_env("GMAIL_APP_PW")

    recipients = [receiver_email]
    if receiver_email2:
        recipients.append(receiver_email2)

    reservation_url = RESERVATION_URLS[LOCATION]
    subject = "Available Pokemon Cafe slot found: " + ", ".join(avail_slots)
    html_days = "".join(f"<li>{slot}</li>" for slot in avail_slots)
    body = f"""
    <p>Go check now: <a href="{reservation_url}">{reservation_url}</a></p>
    <p>Available target slots:</p>
    <ul>{html_days}</ul>
    """

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = ", ".join(recipients)
    message.set_content("Go check now: " + reservation_url + "\n\n" + "\n".join(avail_slots))
    message.add_alternative(body, subtype="html")

    with open(filename, "rb") as image_file:
        message.add_attachment(
            image_file.read(),
            maintype="image",
            subtype="png",
            filename=os.path.basename(filename),
        )

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, password)
        server.send_message(message)

    print("Email sent!")


def open_calendar(driver, num_of_guests):
    wait = WebDriverWait(driver, 20)
    driver.get(RESERVATION_URLS[LOCATION])

    click_first_available(driver, [
        (By.CSS_SELECTOR, "#forms-agree label"),
        (By.XPATH, "//*[@id='forms-agree']//label"),
    ])
    click_first_available(driver, [
        (By.CSS_SELECTOR, "#forms-agree button"),
        (By.XPATH, "//*[@id='forms-agree']//button"),
    ])
    wait_random(3, 6)

    click_first_available(driver, [
        (By.XPATH, "//a[contains(@href, '/reserve/step1')]"),
        (By.XPATH, "/html/body/div/div/div[2]/div/div/a"),
    ])
    wait_random(3, 6)

    guest_select = Select(wait.until(EC.presence_of_element_located((By.NAME, "guest"))))
    guest_select.select_by_index(num_of_guests)
    wait_random()


def create_booking(num_of_guests):
    os.makedirs(HITS_DIR, exist_ok=True)
    driver = make_chrome_driver()

    try:
        open_calendar(driver, num_of_guests)
        available_slots = find_available_target_slots(driver)

        driver.execute_script("document.documentElement.style.scrollBehavior = 'auto'")
        if available_slots:
            print("Slot(s) AVAILABLE:")
            for slot in available_slots:
                print(slot)

            filename = os.path.join(
                HITS_DIR,
                "pokemon-cafe-slot-found-" + date.today().strftime("%Y%m%d") + "-" + uuid.uuid4().hex + ".png",
            )
            driver.save_screenshot(filename)
            send_email(available_slots, filename)
        else:
            print("No matching target slots found.")
    except (NoSuchElementException, TimeoutException) as exc:
        print(f"Reservation page flow failed: {exc}")
    finally:
        driver.quit()


if __name__ == "__main__":
    for _ in range(NUM_ITERATIONS):
        create_booking(NUM_OF_GUESTS)
