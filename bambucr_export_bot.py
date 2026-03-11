import os
import asyncio
from pathlib import Path

import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

LOGIN_URL = "https://bambucr.app/app/login/"
PRODUCTS_URL = "https://bambucr.app/app/modules/productos/?tt=adm-pro"
BACKEND_SYNC_URL = "https://laquintaentrada.com/admin/sync-upload"

EMAIL = os.getenv("BAMBUCR_EMAIL", "")
PASSWORD = os.getenv("BAMBUCR_PASSWORD", "")
SYNC_TOKEN = os.getenv("ADMIN_SYNC_TOKEN", "")

DOWNLOAD_DIR = Path("downloads")
XLSX_FILENAME = "bambucr_productos.xlsx"

HEADLESS = True
TIMEOUT_MS = 120000


async def first_visible_frame(page):
    for _ in range(30):
        for frame in page.frames:
            try:
                user_count = await frame.locator(
                    'input[name*="user" i], input[type="email"], input[autocomplete="username"]'
                ).count()
                pass_count = await frame.locator('input[type="password"]').count()

                if user_count > 0 and pass_count > 0:
                    return frame
            except Exception:
                pass

        await page.wait_for_timeout(500)

    return page.main_frame


async def fill_user_and_password(frame, email: str, password: str):
    user_selectors = [
        'input[type="email"]',
        'input[name*="user" i]',
        'input[name*="correo" i]',
        'input[name*="email" i]',
        'input[id*="user" i]',
        'input[id*="correo" i]',
        'input[id*="email" i]',
        'input[placeholder*="correo" i]',
        'input[placeholder*="usuario" i]',
        'input[autocomplete="username"]',
        'input[type="text"]',
    ]

    pass_selectors = [
        'input[type="password"]',
        'input[name*="pass" i]',
        'input[name*="clave" i]',
        'input[id*="pass" i]',
        'input[id*="clave" i]',
        'input[placeholder*="contraseña" i]',
        'input[autocomplete="current-password"]',
    ]

    user_ok = False
    last_user_error = None
    for sel in user_selectors:
        try:
            loc = frame.locator(sel).first
            await loc.wait_for(state="visible", timeout=4000)
            await loc.fill(email)
            print(f"✅ Usuario con selector: {sel}")
            user_ok = True
            break
        except Exception as e:
            last_user_error = e

    if not user_ok:
        raise RuntimeError(f"No encontré el campo de usuario. Último error: {last_user_error}")

    pass_ok = False
    last_pass_error = None
    for sel in pass_selectors:
        try:
            loc = frame.locator(sel).first
            await loc.wait_for(state="visible", timeout=4000)
            await loc.fill(password)
            print(f"✅ Contraseña con selector: {sel}")
            pass_ok = True
            break
        except Exception as e:
            last_pass_error = e

    if not pass_ok:
        raise RuntimeError(f"No encontré el campo de contraseña. Último error: {last_pass_error}")


async def click_login(frame):
    selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Iniciar")',
        'button:has-text("Ingresar")',
        'button:has-text("Entrar")',
        'text="Iniciar sesión"',
        'text="Ingresar"',
    ]

    last_error = None
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            await loc.wait_for(state="visible", timeout=4000)
            await loc.click()
            print(f"✅ Login con selector: {sel}")
            return
        except Exception as e:
            last_error = e

    raise RuntimeError(f"No encontré el botón de login. Último error: {last_error}")


async def click_more_options(page):
    print("➡️ Abriendo menú 'Más opciones'...")

    mas_opciones = [
        'text="MÁS OPCIONES"',
        'text="Más opciones"',
        'text="MAS OPCIONES"',
        'a:has-text("MÁS OPCIONES")',
        'a:has-text("Más opciones")',
        'button:has-text("MÁS OPCIONES")',
        'button:has-text("Más opciones")',
    ]

    last_error = None
    for sel in mas_opciones:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=5000)
            await loc.click()
            print(f"✅ Más opciones con selector: {sel}")
            await page.wait_for_timeout(1500)
            return
        except Exception as e:
            last_error = e

    await page.screenshot(path="debug_productos.png", full_page=True)
    raise RuntimeError(f"No se pudo abrir 'Más opciones'. Último error: {last_error}")


async def download_excel(page):
    print("➡️ Descargando Excel...")

    excel_options = [
        'text="Exportar Excel de los productos"',
        'a:has-text("Exportar Excel de los productos")',
        'button:has-text("Exportar Excel de los productos")',
    ]

    last_error = None
    for sel in excel_options:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=10000)

            async with page.expect_download(timeout=2000000) as download_info:
                await loc.click()

            download = await download_info.value
            print(f"✅ Exportación iniciada con selector: {sel}")
            return download

        except Exception as e:
            last_error = e

    await page.screenshot(path="debug_menu_excel.png", full_page=True)
    raise RuntimeError(f"No se pudo descargar el Excel. Último error: {last_error}")


def enviar_xlsx_al_backend(xlsx_path: Path):
    print("➡️ Enviando XLSX al backend...")

    with xlsx_path.open("rb") as f:
        resp = requests.post(
            BACKEND_SYNC_URL,
            data={"token": SYNC_TOKEN},
            files={
                "file": (
                    xlsx_path.name,
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            timeout=600,
        )

    print("➡️ Respuesta backend:", resp.status_code, resp.text)
    resp.raise_for_status()
    print("✅ Sincronización enviada correctamente al backend")


async def export_excel_and_send():
    if not EMAIL or not PASSWORD or not SYNC_TOKEN:
        raise RuntimeError("Faltan variables de entorno: BAMBUCR_EMAIL, BAMBUCR_PASSWORD o ADMIN_SYNC_TOKEN")

    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        try:
            print("➡️ Abriendo login...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            frame = await first_visible_frame(page)
            print(f"➡️ Usando frame: {frame.url}")

            if "/login" not in frame.url:
                print("➡️ No cayó en login, redirigiendo manualmente...")
                await page.goto(LOGIN_URL, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                frame = await first_visible_frame(page)
                print(f"➡️ Reintentando frame login: {frame.url}")

            print("➡️ Llenando credenciales...")
            await fill_user_and_password(frame, EMAIL, PASSWORD)

            print("➡️ Enviando login...")
            await click_login(frame)

            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(4000)

            print("➡️ Entrando a productos...")
            await page.goto(PRODUCTS_URL, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(3000)

            await click_more_options(page)
            download = await download_excel(page)

            final_path = DOWNLOAD_DIR / XLSX_FILENAME
            await download.save_as(str(final_path))
            print(f"✅ XLSX guardado en: {final_path.resolve()}")

        except PlaywrightTimeoutError:
            print("⛔ Se agotó el tiempo de espera.")
            raise
        finally:
            await context.close()
            await browser.close()

    enviar_xlsx_al_backend(final_path)
    print("✅ Flujo completo terminado.")


if __name__ == "__main__":
    asyncio.run(export_excel_and_send())