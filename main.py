from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # "*" ile allow_credentials=True birlikte olamaz
    allow_methods=["*"],
    allow_headers=["*"],
)

# cloudscraper: Direnc.net'in Cloudflare korumasını aşmak için (Render'ın
# yurtdışı IP'si buna takılıyordu, log'da 403 Forbidden görmüştük)
scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

# --- GERÇEK ve DOĞRULANMIŞ selector'lar (sohbetimizde inspect edilen HTML'lerden) ---
SITE_CONFIGS = [
    {
        "ad": "Direnc.net",
        "base_url": "https://www.direnc.net",
        "arama_url": lambda kod: f"https://www.direnc.net/arama?q={kod}",
        "kart_secici": ("div", {"class": "productItem"}),
        "isim_secici": ("a", {"class": "productDescription"}),
        "fiyat_secici": ("span", {"class": "currentPrice"}),
        "stok_yok_secici": ("span", {"class": "out-of-stock"}),
    },
    {
        "ad": "Robotistan",
        "base_url": "https://www.robotistan.com",
        "arama_url": lambda kod: f"https://www.robotistan.com/arama?q={kod}",
        "kart_secici": ("div", {"class": "product-item"}),
        "isim_secici": ("a", {"class": "product-title"}),
        "fiyat_secici": ("strong", {"class": "product-price"}),
        "stok_yok_secici": ("span", {"class": "out-of-stock"}),
    },
    {
        "ad": "Elektromarketim",
        "base_url": "https://www.elektromarketim.com",
        "arama_url": lambda kod: f"https://www.elektromarketim.com/arama?q={kod}",
        "kart_secici": ("div", {"class": "productDetails"}),
        "isim_secici": ("a", {"class": "vitrin-product-title"}),
        "fiyat_secici": ("div", {"class": "currentPrice"}),
        "stok_yok_secici": None,  # bu sitede stok bilgisi 0,00 TL fiyatla anlaşılıyor
    },
]


def fiyat_parse(fiyat_metni: str):
    """'1.234,50 TL' -> 1234.50"""
    if not fiyat_metni:
        return None
    temiz = re.sub(r"[^\d,.]", "", fiyat_metni)
    temiz = temiz.replace(".", "").replace(",", ".")
    try:
        return float(temiz)
    except ValueError:
        return None


def site_tara(site: dict, kod: str) -> list[dict]:
    sonuclar = []
    arama_url = site["arama_url"](kod)

    try:
        r = scraper.get(arama_url, timeout=12)
        if r.status_code != 200:
            print(f"[{site['ad']}] engellendi, status: {r.status_code}")
            return sonuclar

        soup = BeautifulSoup(r.text, "html.parser")
        tag, attrs = site["kart_secici"]
        kartlar = soup.find_all(tag, attrs)[:5]

        for kart in kartlar:
            i_tag, i_attrs = site["isim_secici"]
            isim_el = kart.find(i_tag, i_attrs)
            if not isim_el:
                continue

            isim_metni = isim_el.get_text(strip=True) or isim_el.get("title", "")
            urun_href = isim_el.get("href")
            urun_url = urljoin(site["base_url"], urun_href) if urun_href else arama_url

            # 1. Sitede açık "stokta yok" etiketi var mı?
            stok_yok_secici = site.get("stok_yok_secici")
            stokta_yok = False
            if stok_yok_secici:
                sy_tag, sy_attrs = stok_yok_secici
                if kart.find(sy_tag, sy_attrs):
                    stokta_yok = True

            if stokta_yok:
                sonuclar.append({
                    "Tedarikci": site["ad"],
                    "Urun": isim_metni,
                    "Fiyat": "-",
                    "_fiyat_sayi": 999999999.0,
                    "Durum": "Stokta Yok",
                    "Link": urun_url,
                })
                continue

            # 2. Fiyat etiketini bul ve parse et
            f_tag, f_attrs = site["fiyat_secici"]
            fiyat_el = kart.find(f_tag, f_attrs)
            if not fiyat_el:
                continue

            fiyat_metni = fiyat_el.get_text(separator=" ", strip=True)
            fiyat_sayi = fiyat_parse(fiyat_metni)
            if fiyat_sayi is None:
                continue

            # 3. Fiyat 0 ise (Elektromarketim'in stok bitince yaptığı gibi) stokta yok kabul et
            if fiyat_sayi == 0:
                sonuclar.append({
                    "Tedarikci": site["ad"],
                    "Urun": isim_metni,
                    "Fiyat": "-",
                    "_fiyat_sayi": 999999999.0,
                    "Durum": "Stokta Yok",
                    "Link": urun_url,
                })
                continue

            if "TL" not in fiyat_metni and "₺" not in fiyat_metni:
                fiyat_metni = f"{fiyat_metni} TL"

            sonuclar.append({
                "Tedarikci": site["ad"],
                "Urun": isim_metni,
                "Fiyat": fiyat_metni,
                "_fiyat_sayi": fiyat_sayi,
                "Durum": "Canlı Veri",
                "Link": urun_url,
            })

    except Exception as e:
        print(f"[{site['ad']}] hata: {e}")

    return sonuclar


@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")


@app.get("/arama")
def arama_yap(q: str):
    tum_sonuclar = []
    for site in SITE_CONFIGS:
        tum_sonuclar.extend(site_tara(site, q))

    tum_sonuclar.sort(key=lambda x: x["_fiyat_sayi"])
    for s in tum_sonuclar:
        s.pop("_fiyat_sayi", None)

    return {"sonuclar": tum_sonuclar}
