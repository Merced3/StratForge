import asyncio
from datetime import date, datetime
from typing import List, Optional

import pytz
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from shared_state import print_log

from ..models import EconomicCalendarWeek, EconomicEvent


class TradingEconomicsCalendarProvider:
    name = "tradingeconomics"
    url = "https://tradingeconomics.com/calendar"

    def __init__(self, timezone_name: str = "America/Chicago", logger=print_log) -> None:
        self.timezone = timezone_name
        self.logger = logger

    async def fetch_week(self, week_start: date, week_end: date) -> EconomicCalendarWeek:
        driver = self._build_driver()
        try:
            wait = WebDriverWait(driver, 20)
            self._log("[ECON] Loading Trading Economics calendar.")
            driver.get(self.url)
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
            await asyncio.sleep(1)

            await self._set_date_range_this_week(driver, wait)
            await self._set_impact_three_stars(driver, wait)
            await self._set_country_america(driver, wait)
            await self._set_category_all_events(driver, wait)
            await self._set_timezone(driver, wait)

            events = self._extract_events(driver, wait)
            events.sort(key=lambda event: (event.date, event.time_label, event.title))

            return EconomicCalendarWeek(
                week_start=week_start,
                week_end=week_end,
                timezone=self.timezone,
                source=self.name,
                events=tuple(events),
            )
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    def _build_driver(self) -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--allow-insecure-localhost")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920x1080")
        # options.add_argument("--headless=new")
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    async def _set_date_range_this_week(self, driver, wait) -> None:
        self._log("[ECON] Setting date range: This Week.")
        dropdown_locator = (
            By.XPATH,
            "//div[contains(@class, 'btn-group-calendar')]/div/ul[contains(@class, 'dropdown-menu')]",
        )
        for _ in range(6):
            button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-group-calendar .btn-calendar")))
            button.click()
            await asyncio.sleep(1)
            dropdown = wait.until(EC.presence_of_element_located(dropdown_locator))
            if "show" in dropdown.get_attribute("class"):
                break
        else:
            raise RuntimeError("Date range dropdown did not open.")

        option = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//ul[contains(@class, 'dropdown-menu show')]//a[@onclick=\"setCalendarRange('3')\"]")
            )
        )
        self._safe_click(driver, option)
        await asyncio.sleep(1)

    async def _set_impact_three_stars(self, driver, wait) -> None:
        self._log("[ECON] Setting impact: 3 stars.")
        dropdown_locator = (
            By.XPATH,
            "//button[@id='ctl00_ContentPlaceHolder1_ctl02_Button1']/following-sibling::ul[contains(@class, 'dropdown-menu')]",
        )
        for _ in range(6):
            button = wait.until(EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder1_ctl02_Button1")))
            button.click()
            await asyncio.sleep(1)
            dropdown = wait.until(EC.presence_of_element_located(dropdown_locator))
            if "show" in dropdown.get_attribute("class"):
                break
        else:
            raise RuntimeError("Impact dropdown did not open.")

        option = wait.until(EC.element_to_be_clickable((By.XPATH, "//ul[contains(@class, 'dropdown-menu show')]/li[3]/a")))
        self._safe_click(driver, option)
        await asyncio.sleep(1)

    async def _set_country_america(self, driver, wait) -> None:
        self._log("[ECON] Setting country: America.")
        panel_locator = (By.XPATH, "//*[@id='te-c-main-countries']")
        for _ in range(6):
            button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@onclick='toggleMainCountrySelection();' and contains(., 'Countries')]")
                )
            )
            button.click()
            await asyncio.sleep(1)
            panel = wait.until(EC.presence_of_element_located(panel_locator))
            if "d-none" not in panel.get_attribute("class"):
                break
        else:
            raise RuntimeError("Country panel did not open.")

        option = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id='te-c-main-countries']/div/div[1]/span[4]")))
        self._safe_click(driver, option)

        save_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//*[@id='te-c-main-countries']/div/div[2]/div[3]"))
        )
        self._safe_click(driver, save_button)
        wait.until(lambda d: "d-none" in d.find_element(*panel_locator).get_attribute("class"))
        await asyncio.sleep(1)

    async def _set_category_all_events(self, driver, wait) -> None:
        self._log("[ECON] Setting category: All Events.")
        dropdown_locator = (
            By.XPATH,
            "//button[contains(@class, 'btn-calendar') and .//span[contains(text(), 'Category')]]"
            "/following-sibling::ul[contains(@class, 'dropdown-menu')]",
        )
        for _ in range(6):
            button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@class, 'btn-calendar') and .//span[contains(text(), 'Category')]]")
                )
            )
            button.click()
            await asyncio.sleep(1)
            dropdown = wait.until(EC.presence_of_element_located(dropdown_locator))
            if "show" in dropdown.get_attribute("class"):
                break
        else:
            raise RuntimeError("Category dropdown did not open.")

        option = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//ul[contains(@class, 'dropdown-menu') and contains(@class, 'show')]//a[contains(text(), 'All Events')]")
            )
        )
        self._safe_click(driver, option)
        await asyncio.sleep(1)

    async def _set_timezone(self, driver, wait) -> None:
        offset_minutes = _timezone_offset_minutes(self.timezone)
        self._log(f"[ECON] Setting timezone offset minutes: {offset_minutes}.")

        for _ in range(6):
            dropdown = wait.until(EC.element_to_be_clickable((By.ID, "DropDownListTimezone")))
            dropdown.click()
            await asyncio.sleep(1)

            selected = driver.find_element(By.XPATH, "//*[@id='DropDownListTimezone']/option[@selected]")
            current_value = selected.get_attribute("value")
            if current_value == str(offset_minutes):
                return

            driver.execute_script("document.querySelector('#DropDownListTimezone').value = arguments[0];", str(offset_minutes))
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", dropdown)
            await asyncio.sleep(1)

            selected = driver.find_element(By.XPATH, "//*[@id='DropDownListTimezone']/option[@selected]")
            if selected.get_attribute("value") == str(offset_minutes):
                return

        raise RuntimeError("Timezone selection did not apply.")

    def _extract_events(self, driver, wait) -> List[EconomicEvent]:
        self._log("[ECON] Extracting calendar events.")
        events: List[EconomicEvent] = []
        tz = pytz.timezone(self.timezone)
        calendar_table = wait.until(EC.presence_of_element_located((By.ID, "calendar")))
        date_headers = calendar_table.find_elements(By.CLASS_NAME, "table-header")

        if not date_headers:
            self._log("[ECON] No date headers found; calendar may not have loaded.")

        for header in date_headers:
            try:
                date_text = header.find_element(By.XPATH, ".//th[@colspan='3']").text.strip()
                event_date = datetime.strptime(date_text, "%A %B %d %Y").date()
            except Exception:
                continue

            try:
                tbody = header.find_element(By.XPATH, "following-sibling::tbody")
                event_rows = tbody.find_elements(By.XPATH, ".//tr")
            except Exception:
                continue

            for row in event_rows:
                try:
                    time_label = row.find_element(By.XPATH, "./td[1]/span").text.strip()
                    title = row.find_element(By.XPATH, "./td[3]/a").text.strip()
                except NoSuchElementException:
                    continue

                if not time_label or not title:
                    continue

                events.append(
                    EconomicEvent(
                        date=event_date,
                        time_label=time_label,
                        title=title,
                        starts_at=_parse_time_label(event_date, time_label, tz),
                        source=self.name,
                    )
                )

        return _dedupe_events(events)

    def _safe_click(self, driver, element) -> None:
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)


def _timezone_offset_minutes(timezone_name: str) -> int:
    tz = pytz.timezone(timezone_name)
    now = datetime.now(tz)
    offset = now.utcoffset()
    if not offset:
        return 0
    return int(offset.total_seconds() / 60)


def _parse_time_label(event_date: date, time_label: str, tz) -> Optional[datetime]:
    label = time_label.strip()
    if not label:
        return None
    try:
        time_obj = datetime.strptime(label, "%I:%M %p").time()
    except ValueError:
        return None
    return tz.localize(datetime.combine(event_date, time_obj))


def _dedupe_events(events: List[EconomicEvent]) -> List[EconomicEvent]:
    seen = set()
    deduped: List[EconomicEvent] = []
    for event in events:
        key = (event.date, event.time_label, event.title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped
