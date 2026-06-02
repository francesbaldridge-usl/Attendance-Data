import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.edge.options import Options
import time

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Edge(options=options)  # pass options here

URL = "https://www.uslchampionship.com/league-schedule"
WAIT_SECONDS = 15


def get_html(element, css):
    try:
        return element.find_element(By.CSS_SELECTOR, css).get_attribute('innerHTML').strip()
    except NoSuchElementException:
        return None


# def scrape_schedule(url: str) -> pd.DataFrame:
    # driver = webdriver.Edge()
    # wait = WebDriverWait(driver, WAIT_SECONDS)
    # records = []

    # try:
    #     driver.get(url)
    #     wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody.Opta-fixture")))
    #     time.sleep(3)

    #     # Grab ALL tbody elements — both date headers and fixtures are tbody in this widget
    #     all_rows = driver.find_elements(By.CSS_SELECTOR, "table tbody")
    #     print(f"Total tbody rows found: {len(all_rows)}")

    #     current_date = None  # tracks the most recently seen date header

    #     for i, tbody in enumerate(all_rows):
    #         driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tbody)
    #         time.sleep(0.5)

    #         classes = tbody.get_attribute("class") or ""

    #         # ── Date header row ───────────────────────────────────────────────
    #         # Header tbodys have no Opta-fixture class — they just contain a td > h4 > span
    #         if "Opta-fixture" not in classes:
    #             try:
    #                 span = tbody.find_element(By.CSS_SELECTOR, "tr > td > h4 > span")
    #                 date_text = span.get_attribute('innerHTML').strip()
    #                 if date_text:
    #                     current_date = date_text
    #                     print(f"\n  Date: {current_date}")
    #             except NoSuchElementException:
    #                 pass
    #             continue  # not a match row, move on

    #         # ── Stop at first unplayed match ──────────────────────────────────
    #         if "Opta-prematch" in classes:
    #             print(f"  [{i}] First unplayed match — stopping.")
    #             break

    #         if "Opta-result" not in classes:
    #             continue

    #         record = {
    #             "date":       current_date,
    #             "home_team":  None,
    #             "away_team":  None,
    #             "attendance": None,
    #         }

    #         try:
    #             score_row = tbody.find_element(By.CSS_SELECTOR, "tr.Opta-Scoreline")
    #             record["home_team"] = get_html(score_row, "td.Opta-Home.Opta-TeamName")
    #             record["away_team"] = get_html(score_row, "td.Opta-Away.Opta-TeamName")

    #             button = score_row.find_element(By.CSS_SELECTOR, "button.Opta-Nest-Control")
    #             expansion_id = button.get_attribute("data-expansion_id")

    #             driver.execute_script("arguments[0].click();", button)

    #             try:
    #                 panel = driver.find_element(By.ID, expansion_id)
                    
    #                 # Wait until the attendance dt is actually present inside this panel
    #                 wait.until(
    #                     EC.presence_of_element_located((By.XPATH, 
    #                         f"//*[@id='{expansion_id}']//div[@class='Opta-Matchdata']//dt[text()='Attendance']"
    #                     ))
    #                 )
                    
    #                 att_el = panel.find_element(
    #                     By.XPATH, ".//div[@class='Opta-Matchdata']//dt[text()='Attendance']/following-sibling::dd[1]"
    #                 )
    #                 record["attendance"] = att_el.get_attribute('innerHTML').strip() or None

    #             except (NoSuchElementException, TimeoutException):
    #                 record["attendance"] = None

    #             driver.execute_script("arguments[0].click();", button)
    #             time.sleep(0.3)

    #             print(f"  [{i}] {record['date']} | {record['home_team']} vs {record['away_team']} | Att: {record['attendance']}")

    #         except Exception as e:
    #             print(f"  [{i}] Error: {e}")

    #         records.append(record)

    # finally:
    #     driver.quit()

    # return pd.DataFrame(records)

def scrape_schedule(url: str) -> pd.DataFrame:
    driver = webdriver.Edge()
    wait = WebDriverWait(driver, WAIT_SECONDS)
    records = []

    try:
        for attempt in range(3):
            try:
                driver.get(url)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"Page load attempt {attempt + 1} failed, retrying...")
                time.sleep(5)

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody.Opta-fixture")))
        time.sleep(3)

        all_rows = driver.find_elements(By.CSS_SELECTOR, "table tbody")
        print(f"Total tbody rows found: {len(all_rows)}")

        current_date = None

        for i, tbody in enumerate(all_rows):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tbody)
            except Exception:
                pass
            time.sleep(0.5)

            try:
                classes = tbody.get_attribute("class") or ""
            except Exception:
                continue

            classes = tbody.get_attribute("class") or ""

            if "Opta-fixture" not in classes:
                try:
                    span = tbody.find_element(By.CSS_SELECTOR, "tr > td > h4 > span")
                    date_text = span.get_attribute('innerHTML').strip()
                    if date_text:
                        current_date = date_text
                        print(f"\n  Date: {current_date}")
                except NoSuchElementException:
                    pass
                continue

            if "Opta-prematch" in classes:
                print(f"  [{i}] First unplayed match — stopping.")
                break

            if "Opta-result" not in classes:
                continue

            record = {
                "date":       current_date,
                "home_team":  None,
                "away_team":  None,
                "attendance": None,
            }

            try:
                score_row = tbody.find_element(By.CSS_SELECTOR, "tr.Opta-Scoreline")
                record["home_team"] = get_html(score_row, "td.Opta-Home.Opta-TeamName")
                record["away_team"] = get_html(score_row, "td.Opta-Away.Opta-TeamName")

                button = score_row.find_element(By.CSS_SELECTOR, "button.Opta-Nest-Control")
                expansion_id = button.get_attribute("data-expansion_id")

                driver.execute_script("arguments[0].click();", button)

                try:
                    panel = driver.find_element(By.ID, expansion_id)

                    wait.until(
                        EC.presence_of_element_located((By.XPATH,
                            f"//*[@id='{expansion_id}']//div[@class='Opta-Matchdata']//dt[text()='Attendance']"
                        ))
                    )

                    att_el = panel.find_element(
                        By.XPATH, ".//div[@class='Opta-Matchdata']//dt[text()='Attendance']/following-sibling::dd[1]"
                    )
                    record["attendance"] = att_el.get_attribute('innerHTML').strip() or None

                except (NoSuchElementException, TimeoutException):
                    record["attendance"] = None

                driver.execute_script("arguments[0].click();", button)
                time.sleep(0.3)

                print(f"  [{i}] {record['date']} | {record['home_team']} vs {record['away_team']} | Att: {record['attendance']}")

            except Exception as e:
                print(f"  [{i}] Error: {e}")

            records.append(record)

    finally:
        driver.quit()

    return pd.DataFrame(records)

if __name__ == "__main__":
    df = scrape_schedule(URL)
    print(f"\n{df.head(10)}")
    df.to_excel("CH_attendance_data.xlsx", index=False)