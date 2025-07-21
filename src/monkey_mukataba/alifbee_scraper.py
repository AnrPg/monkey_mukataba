#!/usr/bin/env python3

import os
import time
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from urllib.parse import urljoin, urlparse

BASE_URL = "https://app.alifbee.com/en/lessons"
OUTPUT_DIR = "alifbee_export"
USER_DATA_DIR = "./user-data"  # Persistent login
HEADLESS = False  # Set True to run in background

async def stealth_patch(page):
    print("🔧 Applying stealth patch to evade detection...")
    await page.add_init_script("""() => {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    }""")
    print("✅ Stealth patch applied successfully.")

async def save_html(content: str, chapter: str, lesson: str, question_index: int):
    print(f"💾 Preparing to save HTML content for question {question_index} in '{chapter} → {lesson}'...")
    safe_chapter = chapter.replace(" ", "_").replace("/", "-")
    safe_lesson = lesson.replace(" ", "_").replace("/", "-")
    path = Path(OUTPUT_DIR) / safe_chapter / safe_lesson
    path.mkdir(parents=True, exist_ok=True)
    filename = f"{question_index:02}.html"
    with open(path / filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📥 Saved HTML: {path / filename}")

async def handle_login(page):
    print("🔐 Checking if login is required...")
    if await page.locator("a[href='/en/login']").is_visible():
        print("🔑 Login link found. Navigating to login page...")
        await page.click("a[href='/en/login']")
        await page.wait_for_load_state("domcontentloaded")

        print("🔍 Waiting for Google login button...")
        await page.wait_for_selector("img[alt='Google']", timeout=10000)
        await page.click("img[alt='Google']")

        print("🧠 Please complete Google authentication manually in the browser popup.")
        print("⏳ Waiting for user to finish login...")

        while True:
            try:
                # If lessons page loads, we're in
                if await page.locator("h2.H2.purple-51").first.is_visible(timeout=10000):
                    print("✅ Login successful! Proceeding with scraping...")
                    break
            except:
                print("🕐 Still waiting for login... make sure you're completing the Google popup.")
                await asyncio.sleep(3)
    else:
        print("✅ Already logged in. Proceeding directly.")

async def scrape():
    print("🚀 Launching Playwright...")
    async with async_playwright() as p:
        print("🦊 Launching persistent Firefox context...")
        browser = await p.firefox.launch_persistent_context(
            USER_DATA_DIR,
            headless=HEADLESS
        )
        page = await browser.new_page()
        await stealth_patch(page)

        print(f"🌍 Navigating to base URL: {BASE_URL}")
        await page.goto(BASE_URL, timeout=0)

        await handle_login(page)

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
