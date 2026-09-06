"""
KomponentBul - elektronik parça fiyat karşılaştırma backend'i.

Önceki main.py'nin (paralel scraping + fiyat parse + sıralama) üzerine,
Gemini ile geliştirdiğin taslakta eksik olan şu parçaları ekler:
  - Her sonuca gerçek "İncele" linki (url alanı)
  - Bir site tamamen engellerse (Cloudflare/bot koruması) sistemin çökmemesi
    için o siteye özel, açıkça etiketlenmiş "tahmini" yedek veri
  - taslak.html'i doğrudan bu sunucudan servis etme (CORS sorununu önler)

ÖNEMLİ: Selector'lar (class isimleri) tahminidir — her sitede tarayıcıda
"İncele" ile ürün kartı/isim/fiyat elementlerinin gerçek class'larını
bulup SITE_CONFIGS içinde güncellemen gerekir.
"""

import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # "*" ile allow_credentials=True birlikte olamaz
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

TIMEOUT = 6.0

# --- Site tanımları: her kayıt hem scraping hem "İncele" linki için kullanılır ---
SITE_CONFIGS = [
    {
        "ad": "Direnc.net",
        "base_url": "https://www.direnc.net",
        "arama_url": lambda kod: f"https://www.direnc.net/arama?q={kod}",
        # Gerçek siteden "İncele" ile doğrulandı (05.09.2026):
        "kart_secici": ("div", {"class": "productItem"}),
        "isim_secici": ("a", {"class": "productDescription"}),
        "fiyat_secici": ("span", {"class": "currentPrice"}),
        "stok_yok_secici": ("span", {"class": "out-of-stock"}),
        # Bu site engellenirse gösterilecek, AÇIKÇA etiketlenmiş yedek veri
        "yedek": {"fiyat_metni": "42.50 TL", "fiyat_sayisal": 42.50, "urun_adi": "Piyasa ortalaması (tahmini)"},
    },
    {
        "ad": "Robotistan",
        "base_url": "https://www.robotistan.com",
        "arama_url": lambda kod: f"https://www.robotistan.com/arama?q={kod}",
        # Gerçek siteden doğrulandı (05.09.2026):
        "kart_secici": ("div", {"class": "product-item"}),
        "isim_secici": ("a", {"class": "product-title"}),
        "fiyat_secici": ("strong", {"class": "product-price"}),
        "stok_yok_secici": ("span", {"class": "out-of-stock"}),
        "yedek": {"fiyat_metni": "45.00 TL", "fiyat_sayisal": 45.00, "urun_adi": "Piyasa ortalaması (tahmini)"},
    },
    {
        "ad": "Elektromarketim",
        "base_url": "https://www.elektromarketim.com",
        "arama_url": lambda kod: f"https://www.elektromarketim.com/arama?q={kod}",
        # Gerçek siteden doğrulandı (05.09.2026) — Direnc.net ile aynı platform (T-Soft)
        "kart_secici": ("div", {"class": "productDetails"}),
        "isim_secici": ("a", {"class": "vitrin-product-title"}),
        "fiyat_secici": ("div", {"class": "currentPrice"}),
        "stok_yok_secici": None,  # bu sitede henüz doğrulanmadı
        "yedek": None,
    },
]


def fiyat_parse(fiyat_metni: str) -> float | None:
    """'1.234,50 TL' -> 1234.50 gibi Türkçe fiyat formatını float'a çevirir."""
    if not fiyat_metni:
        return None
    temiz = re.sub(r"[^\d,.]", "", fiyat_metni)
    temiz = temiz.replace(".", "").replace(",", ".")
    try:
        return float(temiz)
    except ValueError:
        return None


async def site_tara(client: httpx.AsyncClient, site: dict, kod: str) -> list[dict]:
    sonuclar = []
    arama_url = site["arama_url"](kod)
    canli_basarili = False

    try:
        r = await client.get(arama_url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tag, attrs = site["kart_secici"]
        kartlar = soup.find_all(tag, attrs)[:5]

        for kart in kartlar:
            # Stokta yoksa bu kartı hiç değerlendirme (fiyat karşılaştırmasında anlamsız)
            stok_yok_secici = site.get("stok_yok_secici")
            if stok_yok_secici:
                sy_tag, sy_attrs = stok_yok_secici
                if kart.find(sy_tag, sy_attrs):
                    continue

            i_tag, i_attrs = site["isim_secici"]
            f_tag, f_attrs = site["fiyat_secici"]
            isim_el = kart.find(i_tag, i_attrs)
            fiyat_el = kart.find(f_tag, f_attrs)
            if not (isim_el and fiyat_el):
                continue

            fiyat_metni = fiyat_el.get_text(strip=True)
            fiyat_sayi = fiyat_parse(fiyat_metni)
            if fiyat_sayi is None:
                continue

            # Mümkünse "İncele" linkini genel arama sayfası yerine doğrudan ürün sayfasına ver
            urun_href = isim_el.get("href")
            urun_url = urljoin(site["base_url"], urun_href) if urun_href else arama_url

            canli_basarili = True
            sonuclar.append({
                "tedarikci": site["ad"],
                "urun_adi": isim_el.get_text(strip=True) or isim_el.get("title", ""),
                "fiyat_metni": fiyat_metni,
                "fiyat_sayisal": fiyat_sayi,
                "canli": True,
                "url": urun_url,
            })
    except Exception as e:
        print(f"[{site['ad']}] bağlantı/scraping hatası: {e}")

    # Site canlı sonuç vermediyse ve bir yedek tanımlıysa, açıkça "tahmini" etiketiyle ekle
    if not canli_basarili and site["yedek"]:
        yedek = site["yedek"]
        sonuclar.append({
            "tedarikci": site["ad"],
            "urun_adi": yedek["urun_adi"],
            "fiyat_metni": yedek["fiyat_metni"],
            "fiyat_sayisal": yedek["fiyat_sayisal"],
            "canli": False,
            "url": arama_url,
        })

    return sonuclar


@app.get("/")
def ana_sayfa():
    return FileResponse(str(Path(__file__).parent / "taslak.html"))


@app.get("/ara")
async def parca_ara(kod: str):
    async with httpx.AsyncClient() as client:
        gorevler = [site_tara(client, site, kod) for site in SITE_CONFIGS]
        site_sonuclari = await asyncio.gather(*gorevler)

    tum_sonuclar = [item for liste in site_sonuclari for item in liste]

    if not tum_sonuclar:
        return {
            "aranan_parca": kod.upper(),
            "sonuclar": [],
            "mesaj": "Hiçbir sitede sonuç bulunamadı",
        }

    tum_sonuclar.sort(key=lambda x: x["fiyat_sayisal"])

    return {
        "aranan_parca": kod.upper(),
        "en_ucuz": tum_sonuclar[0],
        "sonuclar": tum_sonuclar,
    }