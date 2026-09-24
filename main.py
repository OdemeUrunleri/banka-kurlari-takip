from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import PRODUCTS
from core.excel_writer import build_excel
from scrapers.doviz_com import scrape_all_products


LATEST_PATH = Path("data/latest_rates.csv")
HISTORY_PATH = Path("data/rates_history.csv")
EXCEL_PATH = Path("output/banka_kurlari.xlsx")

FIELDNAMES = [
    "run_at",
    "scraped_at",
    "product",
    "code",
    "provider",
    "buy",
    "sell",
    "spread",
    "spread_pct",
    "site_spread",
    "site_spread_pct",
    "source_url",
    "status",
    "note",
]


def decimal_text(value):
    if value is None:
        return ""
    return format(value, "f")


def serialize_row(row: dict) -> dict:
    output = {key: row.get(key, "") for key in FIELDNAMES}

    for key in (
        "buy",
        "sell",
        "spread",
        "spread_pct",
        "site_spread",
        "site_spread_pct",
    ):
        output[key] = decimal_text(row.get(key))

    return output


def write_latest(rows: list[dict]) -> None:
    """
    Son yapılan çekimi latest_rates.csv dosyasına yazar.
    Bu dosya her çalıştırmada tamamen yenilenir.
    """

    LATEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LATEST_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=FIELDNAMES,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                serialize_row(row)
            )


def append_history(rows: list[dict]) -> None:
    """
    Geçmiş verileri rates_history.csv dosyasında tutar.

    ÖZEL DURUM:
    24 Eylül 2026 tarihinde çalıştırıldığında,
    o güne ait daha önce yazılmış kayıtları siler
    ve yalnızca en son yapılan çekimi bırakır.

    Diğer bütün tarihlerde normal şekilde
    geçmiş dosyasının altına yeni veriler eklenir.
    """

    HISTORY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Sadece temizlemek istediğimiz tarih.
    target_date = "2026-09-24"

    # Şu an yapılan çekimin tarihi.
    current_run_date = ""

    if rows:
        current_run_date = str(
            rows[0].get("run_at", "")
        )[:10]

    # -------------------------------------------------
    # SADECE 24 EYLÜL 2026 İÇİN ÖZEL TEMİZLEME
    # -------------------------------------------------
    if current_run_date == target_date:

        old_rows = []
        removed_count = 0

        # Eski history dosyası varsa oku.
        if (
            HISTORY_PATH.exists()
            and HISTORY_PATH.stat().st_size > 0
        ):
            with HISTORY_PATH.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as handle:

                reader = csv.DictReader(handle)

                for old_row in reader:

                    old_run_at = str(
                        old_row.get("run_at", "")
                    )

                    old_date = old_run_at[:10]

                    # 24 Eylül kayıtlarını geçmişten çıkar.
                    if old_date == target_date:
                        removed_count += 1
                        continue

                    # Diğer bütün günleri koru.
                    old_rows.append(old_row)

        # History dosyasını yeniden oluştur.
        with HISTORY_PATH.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as handle:

            writer = csv.DictWriter(
                handle,
                fieldnames=FIELDNAMES,
            )

            writer.writeheader()

            # Önce 23 Eylül ve öncesindeki
            # bütün geçmiş verileri geri yaz.
            for old_row in old_rows:
                writer.writerow(
                    {
                        key: old_row.get(key, "")
                        for key in FIELDNAMES
                    }
                )

            # Ardından şu an yapılan
            # yeni 24 Eylül çekimini ekle.
            for row in rows:
                writer.writerow(
                    serialize_row(row)
                )

        print(
            f"[HISTORY] {target_date} tarihindeki "
            f"{removed_count} eski kayıt silindi."
        )

        print(
            f"[HISTORY] Yeni {target_date} çekimi eklendi: "
            f"{len(rows)} kayıt."
        )

    # -------------------------------------------------
    # DİĞER GÜNLERDE NORMAL ÇALIŞMA
    # -------------------------------------------------
    else:

        exists = (
            HISTORY_PATH.exists()
            and HISTORY_PATH.stat().st_size > 0
        )

        with HISTORY_PATH.open(
            "a",
            encoding="utf-8-sig",
            newline="",
        ) as handle:

            writer = csv.DictWriter(
                handle,
                fieldnames=FIELDNAMES,
            )

            if not exists:
                writer.writeheader()

            for row in rows:
                writer.writerow(
                    serialize_row(row)
                )

        print(
            f"[HISTORY] Yeni çekim geçmişe eklendi: "
            f"{len(rows)} kayıt."
        )


def main() -> None:

    print("=== Doviz.com Kur Takip v0.3 ===")
    print("Kapsam: USD + EUR + GRAM ALTIN")
    print("Sağlayıcı filtresi: YOK\n")

    # Türkiye saatine göre çekim zamanı.
    run_at = datetime.now(
        ZoneInfo("Europe/Istanbul")
    ).isoformat(
        timespec="seconds"
    )

    # Doviz.com üzerinden bütün ürünleri çek.
    rows, failures = scrape_all_products(
        PRODUCTS
    )

    # -------------------------------------------------
    # SAYFA HATASI KONTROLÜ
    # -------------------------------------------------

    # Herhangi bir ürün sayfasında hata oluşursa
    # eksik snapshot geçmişe yazılmasın.
    if failures:

        print("\n=== SAYFA HATALARI ===")

        for item in failures:
            print(
                f"{item['code']} | "
                f"{item['error']}"
            )

        raise SystemExit(2)

    # Hiç veri çekilemediyse dur.
    if not rows:
        raise SystemExit(
            "FATAL: Hiç veri çekilemedi."
        )

    # -------------------------------------------------
    # ÜRÜN EKSİKLİĞİ KONTROLÜ
    # -------------------------------------------------

    found_codes = {
        row.get("code")
        for row in rows
    }

    missing_codes = (
        set(PRODUCTS)
        - found_codes
    )

    if missing_codes:

        raise SystemExit(
            "FATAL: Şu ürünler tamamen eksik: "
            + ", ".join(
                sorted(missing_codes)
            )
        )

    # -------------------------------------------------
    # RUN_AT EKLE
    # -------------------------------------------------

    # Aynı çalıştırmanın bütün satırlarına
    # aynı çekim zamanı atanır.
    for row in rows:
        row["run_at"] = run_at

    # -------------------------------------------------
    # DOSYALARI OLUŞTUR
    # -------------------------------------------------

    # Son çekim snapshot'ı.
    write_latest(rows)

    # Geçmiş verisi.
    # 24 Eylül'de eski 24 Eylül verilerini temizler.
    append_history(rows)

    # History CSV'nin tamamından
    # Excel yeniden oluşturulur.
    build_excel(
        HISTORY_PATH,
        EXCEL_PATH,
    )

    # -------------------------------------------------
    # TERMINAL ÖZETİ
    # -------------------------------------------------

    for code in PRODUCTS:

        product_rows = [
            row
            for row in rows
            if row["code"] == code
        ]

        error_count = sum(
            row["status"] == "ERROR"
            for row in product_rows
        )

        control_count = sum(
            row["status"] == "KONTROL"
            for row in product_rows
        )

        print(
            f"\n[{code}] toplam sağlayıcı: "
            f"{len(product_rows)}"
        )

        print(
            f"[{code}] ERROR={error_count} | "
            f"KONTROL={control_count}"
        )

    print(
        f"\nÇekim zamanı (TR): "
        f"{run_at}"
    )

    print(
        f"Toplam kayıt: "
        f"{len(rows)}"
    )

    print(
        f"Güncel CSV: "
        f"{LATEST_PATH}"
    )

    print(
        f"Geçmiş CSV: "
        f"{HISTORY_PATH}"
    )

    print(
        f"Excel: "
        f"{EXCEL_PATH}"
    )

    # -------------------------------------------------
    # KONTROL / ERROR SATIRLARI
    # -------------------------------------------------

    control_rows = [
        row
        for row in rows
        if row["status"] != "OK"
    ]

    if control_rows:

        print(
            "\n=== KONTROL / ERROR KAYITLARI ==="
        )

        for row in control_rows:

            print(
                f"{row['code']} | "
                f"{row['provider']} | "
                f"{row['status']} | "
                f"{row['note']}"
            )


if __name__ == "__main__":
    main()
