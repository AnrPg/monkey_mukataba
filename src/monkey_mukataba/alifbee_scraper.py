#!/usr/bin/env python3
import os, asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from urllib.parse import urljoin

BASE_URL = "https://app.alifbee.com/"
OUTPUT_DIR = "alifbee_export"
USER_DATA_DIR = "./user-data"
HEADLESS = False

# ------------------ Stealth patch ------------------
async def stealth_patch(page):
    await page.add_init_script(
        """() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        }"""
    )

# ------------------ Save page HTML ------------------
async def save_page_html(page, base_folder, name="page"):
    html = await page.content()
    out_path = Path(base_folder) / f"{name}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    print(f"💾 Saved page to {out_path}")

# ------------------ Login logic ------------------
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
        for attempt in range(120):
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
            await asyncio.sleep(10)
        else:
            print("❌ Login failed or timeout occurred.")
            await context.close()
            return False

        await context.storage_state(path=USER_DATA_DIR)
    else:
        print("✅ Already logged in. Proceeding directly.")
    
    await save_page_html(page, OUTPUT_DIR, "homepage")
    return True

# # ------------------ Save question HTML ------------------
# async def save_html(html, chapter, lesson, question_num):
#     folder = Path(OUTPUT_DIR) / chapter.strip() / lesson.strip()
#     folder.mkdir(parents=True, exist_ok=True)
#     out_path = folder / f"question_{question_num:02}.html"
#     out_path.write_text(html)

# ------------------ Main scrape logic ------------------
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
        )

        page = await context.new_page()
        await stealth_patch(page)
        await page.goto(BASE_URL, timeout=0)

        login_success = await handle_login(page, context)
        if not login_success:
            return

        levels = await page.locator("h2.H2.purple-51").all()
        level = levels[0] if levels else None
        print(f"\n\t\t\tLEVEL: {await level.inner_text()}\n-------------------------------------------------------------------\n\n")
        print("📖 Page ready. Starting to locate lessons and sections...")
        
        # lesson_links = await page.locator("h3.H3.purple-51").all()
        # print(f"🔍 Found {len(lesson_links)} lessons.")
                    
        lesson_blocks = await page.locator("div.row.mt-3.scrolled-level.scrolled-level-page").all()
        lesson_count = await lesson_blocks[0].locator("div > a").count()  # Store the number of lessons

        for i in range(lesson_count):
            await page.goto(BASE_URL + "en/lessons", timeout=0)  # Go back to lessons page
            await page.wait_for_selector("div.row.mt-3.scrolled-level.scrolled-level-page", timeout=10000)

            lesson_blocks = await page.locator("div.row.mt-3.scrolled-level.scrolled-level-page").all()
            lesson_link = lesson_blocks[0].locator("div > a").nth(i)
            lesson_name = await lesson_link.locator("h3.H3").inner_text()
            lesson_url = urljoin(BASE_URL, await lesson_link.get_attribute("href"))
            print(f"  📗 Lesson {i+1}/{lesson_count}: {lesson_name} → {lesson_url}")

            try:
                print(f"    🌐 Navigating to lesson URL...")
                await page.goto(lesson_url, timeout=0)
                await save_page_html(page, Path(OUTPUT_DIR) / lesson_name.strip(), f"lesson - {lesson_name.strip()}")
            except Exception as e:
                print(f"    ❌ Failed to load lesson page: {e}")
                continue
            
            try:
                section_links = await page.wait_for_selector(".target-lesson-container .target-list a", timeout=10000)
                if not section_links:
                    print("    ⚠️ No sections found! Saving screenshot...")
                    await page.screenshot(path=f"{OUTPUT_DIR}/no_sections_{lesson_name.strip()}.png")

                for j, section_link in enumerate(section_links):
                    section_name = await section_link.locator("p").inner_text()
                    section_subtitle = await section_link.locator("h3.H3").inner_text()
                    section_url = urljoin(BASE_URL, await section_link.get_attribute("href"))
                    print(f"    📚 Section {j+1}/{len(section_links)}: {section_name} ({section_subtitle}) → {section_url}")

                    try:
                        print(f"    🌐 Navigating to section URL...")
                        await page.goto(section_url, timeout=0)
                        await save_page_html(page, Path(OUTPUT_DIR) / lesson_name.strip() / section_subtitle.strip(), f"section - {section_name.strip()} ({section_subtitle.strip()})")
                    except Exception as e:
                        print(f"    ❌ Failed to load section page: {e}")
                        continue

                
                    # question_links = await page.locator("div.container a[href^='/en/questions/']").all()
                    # if not question_links:
                    #     print("    ⚠️ No questions found. Possibly a premium or malformed lesson.")
                    #     continue

                    # print(f"    🧩 Found {len(question_links)} questions in lesson.")
                    # for q_idx, question in enumerate(question_links):
                    #     question_href = await question.get_attribute("href")
                    #     question_url = urljoin(BASE_URL, question_href)
                    #     print(f"     ➤ Question {q_idx+1}: {question_url}")

                    #     try:
                    #         await page.goto(question_url, timeout=0)
                    #         await save_page_html(page, Path(OUTPUT_DIR) / chapter_name.strip() / chapter_name.strip(), f"question_{q_idx + 1:02}")
                    #     except Exception as e:
                    #         print(f"       ❌ Failed to process question {q_idx + 1}: {e}")
                    #         continue
            except Exception as e:
                print(f"    ⚠️ Could not process sections for lesson '{lesson_name}': {e}")


        print("\n🛑 Closing browser...")
        await browser.close()
        print("✅ Scraping complete.")

# ------------------ Entrypoint ------------------
if __name__ == "__main__":
    print("🔧 Starting scraper script...")
    asyncio.run(scrape())
    print("🎉 Script finished execution.")

# TODO: sections aren't discovered. Check this ChatGPT convo: https://chatgpt.com/share/6883c74d-27e4-8003-8165-bc19c656fb8b