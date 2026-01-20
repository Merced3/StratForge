# economic_calender_scraper.py
import json
import os
import asyncio
import pytz
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from error_handler import error_log_and_discord_message
from shared_state import print_log
from paths import pretty_path, WEEK_ECOM_CALENDER_PATH

# WebDriver options
options = webdriver.ChromeOptions()

# Security-related options
options.add_argument('--ignore-certificate-errors')
options.add_argument('--ignore-ssl-errors')
options.add_argument('--allow-insecure-localhost')

# Performance optimizations
options.add_argument("--disable-gpu")   # For Windows compatibility
options.add_argument("--window-size=1920x1080")  # Set a virtual resolution
#options.add_argument("--headless=new")  # Uses the latest headless mode, Caused a error

async def ensure_economic_calendar_data():
    
    # Check if the JSON file exists
    if not os.path.exists(WEEK_ECOM_CALENDER_PATH):
        await get_economic_calendar_data()
        return

    # Read the JSON data
    with open(WEEK_ECOM_CALENDER_PATH, 'r') as file:
        data = json.load(file)

    # Extract week_timespan
    week_timespan = data.get('week_timespan', "")
    if not week_timespan:
        await get_economic_calendar_data()
        return

    # Parse the week_timespan
    try:
        start_date_str, end_date_str = week_timespan.split(" to ")
        start_date = datetime.strptime(start_date_str, '%m-%d-%y')
        end_date = datetime.strptime(end_date_str, '%m-%d-%y')
    except ValueError:
        await get_economic_calendar_data()
        return

    # Get today's date
    today_date = datetime.now()

    # Check if today's date is within the week_timespan
    if not (start_date <= today_date <= end_date):
        await get_economic_calendar_data()

async def get_economic_calendar_data():
    """Scrapes economic calendar data with improved reliability."""
    print_log(f"[GECD] Get Economic Calender Data:")
    # Initialize the WebDriver without specifying a version
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.get("https://tradingeconomics.com/calendar")

    try:
        wait = WebDriverWait(driver, 20)

        # **Wait Until Page is Fully Loaded**
        print_log(f"    [GECD] Waiting for page to fully load...")
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        print_log(f"    [GECD] Page has fully loaded!")



        # 1️⃣ **Set Date Range (Ensure "This Week" is Clicked)**
        print_log(f"    [GECD] Handling Date Range Section...")
        while True:
            date_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-group-calendar .btn-calendar")))
            date_button.click()
            await asyncio.sleep(1)

            # Check for the correct dropdown within the button group
            try:
                date_dropdown = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'btn-group-calendar')]/div/ul[contains(@class, 'dropdown-menu')]")))
                dropdown_class = date_dropdown.get_attribute("class")
                print_log(f"    [GECD] Dropdown found, class attribute: {dropdown_class}")

                if "show" in dropdown_class:
                    print_log(f"    [GECD] Dropdown is now open!")
                    break
            except Exception:
                print_log(f"    [GECD] Dropdown not detected, retrying...")

        # Select "This Week" from dropdown
        try:
            print_log(f"    [GECD] Selecting 'This Week' from dropdown...")
            # Target only the "This Week" option based on the unique onclick attribute
            this_week_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//ul[contains(@class, 'dropdown-menu show')]//a[@onclick=\"setCalendarRange('3')\"]")))
            this_week_option.click()
            print_log(f"    [GECD] Successfully selected 'This Week'.")
        except Exception:
            print_log(f"    [GECD] 'This Week' not directly clickable, using JavaScript click...")
            driver.execute_script("arguments[0].click();", this_week_option)
        print_log("\n")
        await asyncio.sleep(1)



        # 2️⃣ **Set Impact to 3 Stars (Using Reliable ID Selector)**
        print_log(f"    [GECD] Handling Impact Level Section...")
        while True:
            impact_button = wait.until(EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder1_ctl02_Button1")))
            impact_button.click()
            await asyncio.sleep(1)

            # Check for the correct dropdown within the impact selection group
            try:
                impact_dropdown = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@id='ctl00_ContentPlaceHolder1_ctl02_Button1']/following-sibling::ul[contains(@class, 'dropdown-menu')]")))
                dropdown_class = impact_dropdown.get_attribute("class")
                print_log(f"    [GECD] Dropdown found, class attribute: {dropdown_class}")

                if "show" in dropdown_class:
                    print_log(f"    [GECD] Impact dropdown is now open!")

                    # **Best approach:** Target the <li> tag, then click its <a> child
                    three_star_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//ul[contains(@class, 'dropdown-menu show')]/li[3]/a")))
                    three_star_option.click()
                    print_log(f"    [GECD] Successfully selected 3-Star impact level.")
                    break
            except Exception:
                print_log(f"    [GECD] Impact dropdown not detected, retry...")
        print_log("\n")
        await asyncio.sleep(1)

        # 3️⃣ **Set Country to "America" (Retry Until Success)**
        print_log(f"    [GECD] Handling Country Selection...")
        while True:
            country_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@onclick='toggleMainCountrySelection();' and contains(., 'Countries')]")))
            country_button.click()
            await asyncio.sleep(1)

            # Check for the correct dropdown menu
            try:
                country_panel = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//*[@id='te-c-main-countries']")
                ))
                panel_class = country_panel.get_attribute("class")
                print_log(f"    [GECD] Country Panel Found - ID: 'te-c-main-countries', Class: {panel_class}")

                if "d-none" not in panel_class: # Panel is open when "d-none" is missing
                    print_log(f"    [GECD] Country selection panel is now open!")
                    break

            except Exception:
                print_log(f"    [GECD] Country panel not detected, retrying...")

        # Select "America" as the country
        try:
            print_log(f"    [GECD] Selecting 'America' from the country list...")

            # More precise XPath targeting the "America" button
            country_option = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//*[@id='te-c-main-countries']/div/div[1]/span[4]")
            ))

            country_option.click()
            print_log(f"    [GECD] Successfully selected 'America'.")

        except Exception:
            print_log(f"    [GECD] 'America' not directly clickable, using JavaScript click...")
            driver.execute_script("arguments[0].click();", country_option)

        # Click Save Button (Only After Country is Selected)
        try:
            save_button = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//*[@id='te-c-main-countries']/div/div[2]/div[3]")
            ))
            save_button.click()
            print_log(f"    [GECD] Country selection saved successfully.")

        except Exception:
            print_log(f"    [GECD] Save button not directly clickable, using JavaScript click...")
            driver.execute_script("arguments[0].click();", save_button)
        # **Wait for the Country Panel to Disappear**
        print_log(f"    [GECD] Waiting for Country Panel to go away...")
        wait.until(lambda driver: "d-none" in driver.find_element(By.XPATH, "//*[@id='te-c-main-countries']").get_attribute("class"))
        print_log(f"    [GECD] Panel Gone!\n")

        
        # 4️⃣ **Get Category (Select "All Events")**
        print_log(f"    [GECD] Handling Category Section...")
        while True:
            category_button = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//button[contains(@class, 'btn-calendar') and .//span[contains(text(), 'Category')]]"
            )))
            category_button.click()
            await asyncio.sleep(1)

            try:
                category_dropdown = wait.until(EC.presence_of_element_located((
                    By.XPATH, "//button[contains(@class, 'btn-calendar') and .//span[contains(text(), 'Category')]]/following-sibling::ul[contains(@class, 'dropdown-menu')]"
                )))
                dropdown_class = category_dropdown.get_attribute("class")
                print_log(f"    [GECD] Dropdown found, class attribute: {dropdown_class}")

                if "show" in dropdown_class:
                    print_log(f"    [GECD] Category dropdown is now open!")
                    AE_option = wait.until(EC.element_to_be_clickable((
                        By.XPATH, "//ul[contains(@class, 'dropdown-menu') and contains(@class, 'show')]//a[contains(text(), 'All Events')]"
                    )))
                    AE_option.click()
                    print_log(f"    [GECD] Successfully selected 'All Events'.")
                    break
            except Exception:
                print_log(f"    [GECD] Category dropdown not detected, retry...")
        print_log("\n")
        await asyncio.sleep(1)

        # 5️⃣ **GET TimeZone (UTC-5)**
        print_log(f"    [GECD] TimeZone Handling...")
        # Get the correct UTC offset for San Antonio (auto-detect DST)
        san_antonio_offset = get_san_antonio_timezone()
        print_log(f"    [GECD] Detected UTC offset for San Antonio: {san_antonio_offset} minutes")
        while True:
            try:
                # Select the dropdown menu
                print_log(f"    [GECD] Attempting to open the TimeZone dropdown...")
                timezone_dropdown = wait.until(EC.element_to_be_clickable((By.ID, "DropDownListTimezone")))
                timezone_dropdown.click()
                await asyncio.sleep(1)  # Allow time for the dropdown to open

                # Get the currently selected value
                selected_option = driver.find_element(By.XPATH, "//*[@id='DropDownListTimezone']/option[@selected]")
                current_value = selected_option.get_attribute("value")
                print_log(f"    [GECD] Currently selected TimeZone: {current_value}")

                # If already correct, break out of the loop
                if current_value == str(san_antonio_offset):
                    print_log(f"    [GECD] TimeZone is already correct. No changes needed.")
                    break

                # Select the correct timezone
                print_log(f"    [GECD] Selecting TimeZone option: UTC {san_antonio_offset // 60}")
                driver.execute_script(
                    f"document.querySelector('#DropDownListTimezone').value = '{san_antonio_offset}';"
                )

                # Manually trigger change event to ensure selection is applied
                driver.execute_script(
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                    timezone_dropdown
                )
                await asyncio.sleep(1)  # Give time for the change to register

                # Verify that the selection changed
                selected_option = driver.find_element(By.XPATH, "//*[@id='DropDownListTimezone']/option[@selected]")
                new_value = selected_option.get_attribute("value")

                if new_value == str(san_antonio_offset):
                    print_log(f"    [GECD] Successfully selected 'UTC {san_antonio_offset // 60}'.")
                    break
                else:
                    print_log(f"    [GECD] TimeZone selection did not apply correctly, retrying...")
            except Exception:
                print_log(f"    [GECD] TimeZone selection failed, retrying... Error: {str(e)}")
        print_log("\n")
        await asyncio.sleep(1)
            
            
        # 6️⃣ **Extract Data**
        print_log("    [GECD] Extracting Data From Calender...")
        data = {}
        try: 
            # Locate the main calendar table
            calendar_table = wait.until(EC.presence_of_element_located((By.ID, "calendar")))
            date_headers = calendar_table.find_elements(By.CLASS_NAME, "table-header")
        
            if not date_headers:
                print_log("    [GECD] ERROR: No date headers found! The page might not have loaded correctly.")

            for header in date_headers:
                try:
                    # Extract Date
                    date_text = header.find_element(By.XPATH, ".//th[@colspan='3']").text.strip()
                    formatted_date = datetime.strptime(date_text, "%A %B %d %Y").strftime("%m-%d-%y")

                    print_log(f"    [GECD] Processing Date: {formatted_date}")

                    if formatted_date not in data:
                        data[formatted_date] = {}

                    tbody = header.find_element(By.XPATH, "following-sibling::tbody")
                    event_rows = tbody.find_elements(By.XPATH, ".//tr")

                    if not event_rows:
                        print_log(f"    [GECD] WARNING: No events found for {formatted_date}")
                    print_log(f"    [GECD] Extracting {len(event_rows)} events for {formatted_date}...")

                    for event_row in event_rows:
                        try:
                            # Extract Time and Event Name
                            time_td = event_row.find_element(By.XPATH, "./td[1]/span").text.strip()
                            event_td = event_row.find_element(By.XPATH, "./td[3]/a").text.strip()

                            if formatted_date and time_td and event_td:
                                if time_td not in data[formatted_date]:
                                    data[formatted_date][time_td] = []
                                data[formatted_date][time_td].append(event_td)
                        except NoSuchElementException:
                            print_log(f"    [GECD] Skipping event row due to missing elements.")

                except NoSuchElementException:
                    print_log(f"    [GECD] Skipping a header due to missing date element.")
        except Exception as e:
            print_log(f"[GECD] ERROR: Failed to extract data: {str(e)}")
            driver.quit()
            raise

        driver.quit()

        # 7️⃣ **Save Data to JSON**
        timespan_label = f"{(datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%m-%d-%y')} to {(datetime.now() + timedelta(days=6-datetime.now().weekday())).strftime('%m-%d-%y')}"
        final_data = {f"week_timespan": timespan_label, "dates": data}

        with open(WEEK_ECOM_CALENDER_PATH, 'w') as f:
            json.dump(final_data, f, indent=4)

        print_log(f"    [GECD] ✅ Data extraction completed! Total Dates: {len(data.keys())}, File Saved: `{pretty_path(WEEK_ECOM_CALENDER_PATH)}`")

    except Exception as e:
        await error_log_and_discord_message(e, "economic_calender_scraper", "get_economic_calendar_data")
        driver.quit()

# Determine the correct UTC offset for San Antonio, TX
def get_san_antonio_timezone():
    tz = pytz.timezone("America/Chicago")  # Central Time Zone (CST/CDT)
    now = datetime.now(tz)
    offset = now.utcoffset().total_seconds() / 60  # Convert seconds to minutes
    return int(offset)  # Returns -300 (UTC -5) or -360 (UTC -6)

def check_order_time_to_event_time(time_threshold=20, sim_active=False):
    if sim_active:
        return True
    # Ensure the JSON file exists
    if not os.path.exists(WEEK_ECOM_CALENDER_PATH):
        raise FileNotFoundError(f"`{pretty_path(WEEK_ECOM_CALENDER_PATH)}` does not exist")

    # Read the JSON data
    with open(WEEK_ECOM_CALENDER_PATH, 'r') as file:
        data = json.load(file)

    # Extract today's date in the format "mm-dd-yy"
    today_date = datetime.now().strftime('%m-%d-%y')

    # Check if there are events for today
    if today_date not in data['dates']:
        #print_log("No Events today")
        return True  # No events today

    # Get the list of events for today
    events_today = data['dates'][today_date]
    #print_log(f"Event(s): {events_today}")

    # Get and convert the current time to a datetime object for comparison
    current_time = datetime.now().strftime("%I:%M %p")
    current_time_obj = datetime.strptime(current_time, "%I:%M %p")
    #print_log(f"Current Time: {current_time_obj}")
    # Check each event time
    for event_time_str in events_today:
        event_time_obj = datetime.strptime(event_time_str, "%I:%M %p")
        
        # Calculate the time difference
        time_diff = (event_time_obj - current_time_obj).total_seconds() / 60

        # Check if the current time is within the threshold before the event
        if 0 <= time_diff <= time_threshold:
            return False  # Within the threshold before an event

    return True  # No events within the threshold

def setup_economic_news_message():
    # Ensure the JSON file exists
    if not os.path.exists(WEEK_ECOM_CALENDER_PATH):
        raise FileNotFoundError(f"`{pretty_path(WEEK_ECOM_CALENDER_PATH)}` does not exist")

    # Read the JSON data
    with open(WEEK_ECOM_CALENDER_PATH, 'r') as file:
        data = json.load(file)

    # Extract today's date in the format "mm-dd-yy"
    today_date = datetime.now().strftime('%m-%d-%y')

    # Check if there are events for today
    if today_date not in data['dates']:
        return f"""
**NO MAJOR NEWS EVENTS TODAY**
"""

    # Get the list of events for today
    events_today = data['dates'][today_date]

    # Generate the message
    message = f"""
**TODAYS MAJOR ECONOMIC NEWS**
-----
"""

    for event_time, events in events_today.items():
        message += f"**{event_time}**\n"
        for event in events:
            message += f"- {event}\n"
        message += "\n"  # Add an extra newline for separation between event times

    return message.strip()


# Example usage in an asynchronous context
async def main():
    await get_economic_calendar_data()

if __name__ == "__main__":
    asyncio.run(main()) 