import os
import time
import json
import smtplib
import pandas as pd
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
URL = "https://www.uslleagueone.com/league-schedule"
EXCEL_FILE = "attendance.xlsx"
EMAIL_SENDER = "frances.baldridge@usl.com"        # fill in
EMAIL_RECIPIENT = "frances.baldridge@usl.com"     # fill in
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")


# ─────────────────────────────────────────
# DRIVER SETUP
# ─────────────────────────────────────────
def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver


# ─────────────────────────────────────────
# LOAD EXISTING DATA  
# ─────────────────────────────────────────
def load_existing_data():
    """Load existing excel file if it exists, return empty df if not."""
    if os.path.exists(EXCEL_FILE):
        return pd.read_excel(EXCEL_FILE)
    return pd.DataFrame(columns=["date", "home_team", "away_team", "attendance"])


# ─────────────────────────────────────────
# SCRAPER — FULL PAGE VERSION
# pulls every match on the page regardless of date
# ─────────────────────────────────────────
def scrape_full_page():
    print("Starting full page scrape...")
    driver = get_driver()
    wait = WebDriverWait(driver, 15)
    results = []

    try:
        driver.get(URL)
        time.sleep(5)  # let Opta widget fully load

        # Find all match rows — each match is a tbody with class Opta-fixture
        match_rows = driver.find_elements(
            By.CSS_SELECTOR, "tbody.Opta-fixture"
        )
        print(f"Found {len(match_rows)} match rows")

        for i, row in enumerate(match_rows):
            try:
                # ── Get match date from the nearest date header above ──
                # Date headers sit in thead rows above each group of matches
                # We'll grab it from the row's data attribute or nearest header
                try:
                    date_el = driver.execute_script("""
                        var el = arguments[0];
                        var prev = el.previousElementSibling;
                        while (prev) {
                            if (prev.tagName === 'THEAD') {
                                return prev.innerText;
                            }
                            prev = prev.previousElementSibling;
                        }
                        // walk up to table then look for thead
                        var table = el.closest('table');
                        if (table) {
                            var thead = table.querySelector('thead');
                            if (thead) return thead.innerText;
                        }
                        return '';
                    """, row)
                    match_date = date_el.strip() if date_el else "Unknown"
                except Exception:
                    match_date = "Unknown"

                # ── Get home team name ──
                try:
                    home_el = row.find_element(
                        By.CSS_SELECTOR,
                        "td.Opta-Team.Opta-Home span, "
                        "td.Opta-TeamName.Opta-Home, "
                        "td.Opta-Home .Opta-TeamName"
                    )
                    home_team = home_el.text.strip()
                except Exception:
                    try:
                        home_el = row.find_element(
                            By.CSS_SELECTOR, "td.Opta-Home"
                        )
                        home_team = home_el.text.strip()
                    except Exception:
                        home_team = "Unknown"

                # ── Get away team name ──
                try:
                    away_el = row.find_element(
                        By.CSS_SELECTOR,
                        "td.Opta-Team.Opta-Away span, "
                        "td.Opta-TeamName.Opta-Away, "
                        "td.Opta-Away .Opta-TeamName"
                    )
                    away_team = away_el.text.strip()
                except Exception:
                    try:
                        away_el = row.find_element(
                            By.CSS_SELECTOR, "td.Opta-Away"
                        )
                        away_team = away_el.text.strip()
                    except Exception:
                        away_team = "Unknown"

                # ── Check if match has been played ──
                # Unplayed matches won't have the expand button active
                # or won't have result data
                is_result = "Opta-result" in row.get_attribute("class")
                if not is_result:
                    print(f"  Row {i+1}: {home_team} vs {away_team} — not played yet, skipping")
                    continue

                # ── Find and click the expand button ──
                try:
                    expand_btn = row.find_element(
                        By.CSS_SELECTOR, "td:nth-child(9) button"
                    )
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        expand_btn
                    )
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", expand_btn)
                    time.sleep(1.5)  # wait for dropdown to expand
                except Exception as e:
                    print(f"  Row {i+1}: Could not click expand button — {e}")
                    results.append({
                        "date": match_date,
                        "home_team": home_team,
                        "away_team": away_team,
                        "attendance": None
                    })
                    continue

                # ── Find attendance in expanded dropdown ──
                # The expanded panel gets a unique Opta_N id
                # We search all expanded panels for attendance dd element
                attendance = None
                try:
                    # Wait for any Opta match data panel to appear
                    wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div.Opta-Matchdata")
                        )
                    )
                    # Find all matchdata panels and grab the one
                    # that belongs to this match
                    matchdata_panels = driver.find_elements(
                        By.CSS_SELECTOR, "div.Opta-Matchdata"
                    )
                    for panel in matchdata_panels:
                        # Check if panel is visible
                        if panel.is_displayed():
                            try:
                                # Attendance is in a dl > dd element
                                # Usually the second dl on the panel
                                dls = panel.find_elements(By.TAG_NAME, "dl")
                                for dl in dls:
                                    try:
                                        dt = dl.find_element(By.TAG_NAME, "dt")
                                        if "attend" in dt.text.lower():
                                            dd = dl.find_element(By.TAG_NAME, "dd")
                                            attendance = dd.text.strip()
                                            break
                                    except Exception:
                                        continue
                                if attendance:
                                    break
                            except Exception:
                                continue

                    # Fallback: try direct dd selector if above didn't work
                    if not attendance:
                        try:
                            dds = driver.find_elements(
                                By.CSS_SELECTOR,
                                "div.Opta-Matchdata dl dd"
                            )
                            for dd in dds:
                                if dd.is_displayed() and dd.text.strip().isdigit():
                                    attendance = dd.text.strip()
                                    break
                        except Exception:
                            pass

                except Exception as e:
                    print(f"  Row {i+1}: Could not find attendance — {e}")

                print(f"  Row {i+1}: {home_team} vs {away_team} | "
                      f"Date: {match_date} | Attendance: {attendance}")

                results.append({
                    "date": match_date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "attendance": attendance
                })

                # ── Close the dropdown before moving on ──
                try:
                    driver.execute_script("arguments[0].click();", expand_btn)
                    time.sleep(0.5)
                except Exception:
                    pass

            except Exception as e:
                print(f"  Row {i+1}: Unexpected error — {e}")
                continue

    finally:
        driver.quit()

    return pd.DataFrame(results)


# ─────────────────────────────────────────
# SCRAPER — DATE RANGE VERSION
# only pulls matches between last_pull_date and today
# use this if the full scrape breaks or you want incremental updates
# ─────────────────────────────────────────
def scrape_date_range(start_date=None, end_date=None):
    """
    start_date: datetime object — defaults to 7 days ago
    end_date:   datetime object — defaults to today
    """
    if start_date is None:
        start_date = datetime.now() - timedelta(days=7)
    if end_date is None:
        end_date = datetime.now()

    print(f"Scraping matches between {start_date.date()} and {end_date.date()}")

    # Run the full scrape first
    df = scrape_full_page()

    if df.empty:
        return df

    # Parse dates and filter to range
    # The date format from Opta headers is typically like "Saturday 3rd May 2025"
    # so we try a few formats
    def parse_date(date_str):
        if not date_str or date_str == "Unknown":
            return None
        # Clean up ordinal suffixes (1st, 2nd, 3rd, 4th etc)
        import re
        clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str).strip()
        for fmt in ["%A %d %B %Y", "%d %B %Y", "%B %d %Y",
                    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                continue
        return None

    df["parsed_date"] = df["date"].apply(parse_date)

    filtered = df[
        (df["parsed_date"] >= start_date) &
        (df["parsed_date"] <= end_date)
    ].copy()

    print(f"Found {len(filtered)} matches in date range "
          f"(out of {len(df)} total)")

    return filtered.drop(columns=["parsed_date"])


# ─────────────────────────────────────────
# MERGE NEW DATA WITH EXISTING
# avoids duplicates when appending weekly
# ─────────────────────────────────────────
def merge_data(existing_df, new_df):
    if existing_df.empty:
        return new_df

    combined = pd.concat([existing_df, new_df], ignore_index=True)

    # Drop duplicates based on date + home team + away team
    combined = combined.drop_duplicates(
        subset=["date", "home_team", "away_team"],
        keep="last"  # keep newest pull if duplicate
    )

    # Sort by date
    combined = combined.sort_values("date").reset_index(drop=True)

    return combined


# ─────────────────────────────────────────
# SAVE TO EXCEL
# ─────────────────────────────────────────
def save_to_excel(df, filepath=EXCEL_FILE):
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Attendance")

        # Auto-size columns
        worksheet = writer.sheets["Attendance"]
        for col in worksheet.columns:
            max_len = max(
                len(str(cell.value)) if cell.value else 0
                for cell in col
            )
            worksheet.column_dimensions[
                col[0].column_letter
            ].width = max_len + 4

    print(f"Saved to {filepath}")


# ─────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────
def send_email(filepath, new_row_count):
    if not EMAIL_SENDER or not EMAIL_RECIPIENT or not EMAIL_PASSWORD:
        print("Email credentials not set — skipping email")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg["Subject"] = (
        f"USL League One Attendance — "
        f"Weekly Update {datetime.now().strftime('%B %d %Y')}"
    )

    body = (
        f"Hi,\n\n"
        f"Attached is the updated USL League One attendance data.\n\n"
        f"This week's pull added {new_row_count} new matches.\n"
        f"Report generated: {datetime.now().strftime('%A %B %d %Y at %I:%M %p')}\n\n"
        f"Source: https://www.uslleagueone.com/league-schedule"
    )
    msg.attach(MIMEText(body, "plain"))

    with open(filepath, "rb") as f:
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition",
            f'attachment; filename="USL_L1_Attendance_{datetime.now().strftime("%Y%m%d")}.xlsx"'
        )
        msg.attach(attachment)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print(f"Email sent to {EMAIL_RECIPIENT}")
    except Exception as e:
        print(f"Email failed: {e}")


# ─────────────────────────────────────────
# MAIN — FULL WEEKLY VERSION
# runs the full page scrape, merges with 
# existing data, saves excel, sends email
# ─────────────────────────────────────────
def main_full():
    print("=" * 50)
    print("USL LEAGUE ONE ATTENDANCE SCRAPER — FULL")
    print(f"Run time: {datetime.now()}")
    print("=" * 50)

    existing_df = load_existing_data()
    print(f"Existing records: {len(existing_df)}")

    new_df = scrape_full_page()
    print(f"Scraped records: {len(new_df)}")

    if new_df.empty:
        print("No data scraped — exiting")
        return

    merged_df = merge_data(existing_df, new_df)
    new_rows = len(merged_df) - len(existing_df)
    print(f"New rows added: {new_rows}")

    save_to_excel(merged_df)
    send_email(EXCEL_FILE, new_rows)

    print("Done.")


# ─────────────────────────────────────────
# MAIN — DATE RANGE VERSION
# use this as a backup or manual re-pull
# edit start_date and end_date as needed
# ─────────────────────────────────────────
def main_range():
    print("=" * 50)
    print("USL LEAGUE ONE ATTENDANCE SCRAPER — DATE RANGE")
    print(f"Run time: {datetime.now()}")
    print("=" * 50)

    # ── Edit these dates for your range ──
    start_date = datetime(2025, 3, 1)   # change as needed
    end_date = datetime.now()            # or set a specific end date

    existing_df = load_existing_data()
    print(f"Existing records: {len(existing_df)}")

    new_df = scrape_date_range(start_date, end_date)
    print(f"Scraped records in range: {len(new_df)}")

    if new_df.empty:
        print("No data in range — exiting")
        return

    merged_df = merge_data(existing_df, new_df)
    new_rows = len(merged_df) - len(existing_df)
    print(f"New rows added: {new_rows}")

    save_to_excel(merged_df)
    send_email(EXCEL_FILE, new_rows)

    print("Done.")


# ─────────────────────────────────────────
# ENTRY POINT
# change main_full() to main_range() 
# if you want the date range version
# ─────────────────────────────────────────
if __name__ == "__main__":
    main_full()
    # main_range()  # uncomment this and comment above for range version