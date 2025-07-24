#!/usr/bin/env python3
import os, asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from urllib.parse import urljoin

BASE_URL = "https://app.alifbee.com/en/lessons"
OUTPUT_DIR = "alifbee_export"
USER_DATA_DIR = "./user-data"
HEADLESS = False

# Shared stealth patch
async def stealth_patch(page):
    await page.add_init_script(
        """() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        }"""
    )

async def handle_login(page, context):
    print("🔐 Checking if login is required...")
    if await page.locator("a[href='/en/login']").is_visible():
        print("🔑 Login link found. Navigating to login page...")
        await page.click("a[href='/en/login']")
        await page.wait_for_load_state("domcontentloaded")

        print("🔍 Waiting for Google login button...")
        await page.wait_for_selector("img[alt='Google']", timeout=10000)

        print("🧠 Clicking Google login button...")
        async with page.expect_popup() as popup_info:
            await page.click("img[alt='Google']")
        popup = await popup_info.value
        await popup.wait_for_load_state()
        print("🧠 Google login popup opened.")


        print("⏳ Waiting for user to finish login...")

        for attempt in range(60):  # wait up to 180 seconds
            current_url = page.url
            if "/en/lessons" in current_url:
                print("✅ Redirected to lessons page.")
                break
            try:
                if await page.locator("h2.H2.purple-51").first.is_visible(timeout=3000):
                    print("✅ Login successful! Proceeding with scraping...")
                    break
            except:
                pass

            print(f"🕐 Still waiting for login... current URL: {current_url}")
            await asyncio.sleep(3)
        else:
            print("❌ Login failed or timeout occurred.")
            await context.close()
            return False

        # Save session
        await context.storage_state(path=USER_DATA_DIR)
    else:
        print("✅ Already logged in. Proceeding directly.")
    return True


async def save_html(html, chapter, lesson, question_num):
    folder = Path(OUTPUT_DIR) / chapter.strip() / lesson.strip()
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"question_{question_num:02}.html"
    out_path.write_text(html)

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--no-sandbox",
                "--disable-web-security",
                "--start-maximized",
                "--window-size=1280,720"
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0.5735.198 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            storage_state=USER_DATA_DIR if os.path.exists(USER_DATA_DIR) else None
        )

        page = await context.new_page()
        await stealth_patch(page)

        await page.goto(BASE_URL, timeout=0)

        login_success = await handle_login(page, context)
        if not login_success:
            return

        print("📖 Page ready. Starting to locate chapters and lessons...")
        chapter_els = await page.locator("h2.H2.purple-51").all()
        lesson_blocks = await page.locator("div.row.mt-3.scrolled-level.scrolled-level-page").all()
        print(f"🔍 Found {len(chapter_els)} chapters.")

        for i, chapter_el in enumerate(chapter_els):
            chapter_name = await chapter_el.inner_text()
            print(f"\n📘 Processing Chapter [{i+1}/{len(chapter_els)}]: {chapter_name}")

            lesson_links = await lesson_blocks[i].locator("div > a").all()
            print(f"   🔗 Found {len(lesson_links)} lessons in this chapter.")

            for lesson_link in lesson_links:
                href = await lesson_link.get_attribute("href")
                lesson_url = urljoin(BASE_URL, href)
                lesson_name = await lesson_link.inner_text()
                print(f"  📗 Lesson: {lesson_name} → {lesson_url}")

                try:
                    print(f"    🌐 Navigating to lesson URL...")
                    await page.goto(lesson_url, timeout=0)
                except Exception as e:
                    print(f"    ❌ Failed to load lesson page: {e}")
                    continue

                question_links = await page.locator("div.section-container a[href^='/en/questions/']").all()
                if not question_links:
                    print("    ⚠️ No questions found. Possibly a premium or malformed lesson.")
                    continue

                print(f"    🧩 Found {len(question_links)} questions in lesson.")
                for q_idx, question in enumerate(question_links):
                    question_href = await question.get_attribute("href")
                    question_url = urljoin(BASE_URL, question_href)
                    print(f"     ➤ Question {q_idx+1}: {question_url}")

                    try:
                        await page.goto(question_url, timeout=0)
                        await page.wait_for_selector("button.next-button", timeout=5000)
                        html = await page.content()
                        await save_html(html, chapter_name, lesson_name, q_idx + 1)
                        print(f"       ✅ Question {q_idx + 1} saved successfully.")
                    except Exception as e:
                        print(f"       ❌ Failed to process question {q_idx + 1}: {e}")
                        continue

        print("\n🛑 Closing browser...")
        await browser.close()
        print("✅ Scraping complete.")

if __name__ == "__main__":
    print("🔧 Starting scraper script...")
    asyncio.run(scrape())
    print("🎉 Script finished execution.")
