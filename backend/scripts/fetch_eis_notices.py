"""Позиции реальных закупок из ЕИС (извещения 44-ФЗ) для пополнения наборов оценки.

Сервис отдачи информации getDocsIP: запрос getDocsByOrgRegion (регион заказчика × тип извещения × дата) → ссылки на
архивы → XML извещений → объекты закупки «наименование ; код ОКПД2». Нужен личный токен ЕИС (тот же, что для
выгрузки КТРУ): переменная EIS_TOKEN или скрытый ввод. В файлы и логи токен не пишется.

Результат — CSV в формате data/eval/zakupki_raw.csv (Наименование;Код ОКПД2;Ссылка;Сфера), дописывается
по мере выгрузки; повторный запуск пропускает уже обработанные «дата × регион × тип» (файл <out>.done).
Дальше — scripts/add_eval_rows.py.

    docker compose run --rm -e EIS_TOKEN -v ./backend:/app -v ./data:/datarw api \\
        python scripts/fetch_eis_notices.py --out /datarw/train/eis_notices.csv --days 10 [--sample]

--sample — выгрузить один архив и напечатать структуру первого XML (проверка разбора, ничего не записывает).
"""
import argparse
import csv
import datetime as dt
import getpass
import io
import os
import re
import sys
import time
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

URL = "https://int44.zakupki.gov.ru/eis-integration/services/getDocsIP"
NS_WS = "http://zakupki.gov.ru/fz44/get-docs-ip/ws"
# электронный аукцион и запрос котировок — основная масса закупок товаров
TYPES = {"epNotificationEF2020": "ea20", "epNotificationEZK2020": "zk20"}
# крупные регионы с разной структурой закупок: Москва, СПб, МО, Татарстан, Свердловская, Новосибирская,
# Краснодарский край, Башкортостан, Нижегородская, Ростовская
REGIONS = ["77", "78", "50", "16", "66", "54", "23", "02", "52", "61"]
PER_NOTICE = 5  # не больше позиций из одного извещения: иначе один заказчик заполнит набор однотипными строками
CODE_RE = re.compile(r"^\d{2}(\.\d{1,3}){1,3}$")

# сферы как в data/eval/zakupki_raw.csv; по первым цифрам кода ОКПД2, первое совпадение
SPHERES = [
    ("Медицина", ("32.50", "21.20", "26.60", "22.19.60")),
    ("ИТ", ("26.20", "26.30", "26.40", "58.29", "62.0")),
    ("Канцелярия", ("17.23", "22.29.25", "32.99.1", "25.71.11", "20.52")),
    ("Продукты", ("01.", "03.", "10.", "11.")),
    ("Мебель", ("31.",)),
    ("Одежда", ("13.92", "14.", "15.")),
    ("Стройка", ("08.", "16.2", "22.21", "22.23", "23.", "24.33", "25.1", "25.72")),
]

REQUEST = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ws="{ns}">
<soapenv:Header><individualPerson_token>{token}</individualPerson_token></soapenv:Header>
<soapenv:Body><ws:getDocsByOrgRegionRequest>
<index><id>{id}</id><createDateTime>{now}</createDateTime><mode>PROD</mode></index>
<selectionParams><orgRegion>{region}</orgRegion><subsystemType>PRIZ</subsystemType>
<documentType44>{doc_type}</documentType44><periodInfo><exactDate>{date}</exactDate></periodInfo></selectionParams>
</ws:getDocsByOrgRegionRequest></soapenv:Body></soapenv:Envelope>"""


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el if local(c.tag) == name), None)


def first(el: ET.Element, name: str) -> str:
    return next((e.text.strip() for e in el.iter() if local(e.tag) == name and e.text and e.text.strip()), "")


def sphere(code: str) -> str:
    return next((s for s, prefixes in SPHERES if code.startswith(prefixes)), "Прочее")


def purchase_objects(xml: bytes) -> tuple[str, list[tuple[str, str]]]:
    """Номер извещения и пары (наименование, код ОКПД2) объектов закупки — без учёта пространств имён.

    Наименование — элемент name объекта закупки (у позиции КТРУ — name внутри KTRU); код — OKPDCode,
    у позиции КТРУ — код КТРУ до «-» (26.20.11.110-00000001 → 26.20.11.110). Лекарства (drugPurchaseObject…)
    не берём: там МНН, а не наименования товаров.
    """
    root = ET.fromstring(xml)
    number = first(root, "purchaseNumber")
    out = []
    for obj in root.iter():
        if local(obj.tag) != "purchaseObject":
            continue
        ktru = child(obj, "KTRU")
        name_el = child(obj, "name")  # не «or»: элемент без дочерних узлов в Python ложен
        if name_el is None and ktru is not None:
            name_el = child(ktru, "name")
        name = " ".join((name_el.text or "").split()) if name_el is not None else ""
        code = first(obj, "OKPDCode") or (first(ktru, "code").split("-")[0] if ktru is not None else "")
        if name and CODE_RE.match(code):
            out.append((name, code))
    return number, out


def soap_request(session: requests.Session, token: str, region: str, doc_type: str, date: dt.date, verify) -> list[str]:
    body = REQUEST.format(ns=NS_WS, token=token, id=uuid.uuid4(), now=dt.datetime.now().isoformat(timespec="seconds"),
                          region=region, doc_type=doc_type, date=date.isoformat())
    for attempt in range(4):
        try:
            r = session.post(URL, data=body.encode("utf-8"), timeout=120, verify=verify,  # токен и в заголовке, как в dars
                             headers={"Content-Type": "text/xml; charset=utf-8", "individualPerson_token": token})
        except requests.exceptions.SSLError:
            raise
        except requests.RequestException as e:
            time.sleep(10 * (attempt + 1)); print(f"  сеть: {e.__class__.__name__}, повтор", flush=True)
            continue
        root = ET.fromstring(r.content)
        errors = [e.text for e in root.iter() if local(e.tag) in ("message", "faultstring") and e.text]
        if r.status_code != 200 or errors:
            print(f"  {region} {doc_type} {date}: HTTP {r.status_code} {'; '.join(errors)[:300]}", flush=True)
            return []
        return [e.text.strip() for e in root.iter() if local(e.tag) == "archiveUrl" and e.text]
    return []


def download(session: requests.Session, token: str, url: str, verify) -> bytes | None:
    for attempt in range(4):
        try:
            r = session.get(url, timeout=300, verify=verify, headers={"individualPerson_token": token})
            if r.status_code == 200 and r.content[:2] == b"PK":
                return r.content
            print(f"  архив: HTTP {r.status_code}", flush=True)
        except requests.RequestException as e:
            print(f"  архив: {e.__class__.__name__}, повтор", flush=True)
        time.sleep(10 * (attempt + 1))
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--days", type=int, default=7, help="сколько дней назад от --until (включительно)")
    p.add_argument("--until", default=(dt.date.today() - dt.timedelta(days=1)).isoformat())
    p.add_argument("--regions", default=",".join(REGIONS))
    p.add_argument("--types", default=",".join(TYPES))
    p.add_argument("--ca-bundle", default=None, help="файл корневого сертификата, если проверка TLS не проходит")
    p.add_argument("--sample", action="store_true", help="один архив: напечатать структуру XML и найденные позиции")
    a = p.parse_args()

    token = os.environ.get("EIS_TOKEN") or getpass.getpass("Токен ЕИС (ввод скрыт): ")
    verify = a.ca_bundle or True
    session = requests.Session()
    until = dt.date.fromisoformat(a.until)
    dates = [until - dt.timedelta(days=i) for i in range(a.days)]
    jobs = [(d, r, t) for d in dates for r in a.regions.split(",") for t in a.types.split(",")]

    if a.sample:
        for d, r, t in jobs:
            for url in soap_request(session, token, r, t, d, verify):
                data = download(session, token, url, verify)
                if not data:
                    continue
                z = zipfile.ZipFile(io.BytesIO(data))
                xml_name = next(n for n in z.namelist() if n.endswith(".xml"))
                xml = z.read(xml_name)
                tags = sorted({local(e.tag) for e in ET.fromstring(xml).iter()})
                print(f"{r} {t} {d}: архив {len(z.namelist())} файлов; {xml_name}\nтеги: {', '.join(tags)}")
                print("позиции:", purchase_objects(xml))
                return
        sys.exit("ни одного архива: проверьте токен, регионы и даты")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    done_path = a.out.with_name(a.out.name + ".done")
    done = set(done_path.read_text(encoding="utf-8").split()) if done_path.exists() else set()
    seen = set()
    if a.out.exists():
        with a.out.open(encoding="utf-8-sig") as f:
            seen = {(r[0], r[1]) for r in csv.reader(f, delimiter=";") if len(r) >= 2}
    new_file = not a.out.exists()
    with a.out.open("a", encoding="utf-8", newline="") as f, done_path.open("a", encoding="utf-8") as fd:
        w = csv.writer(f, delimiter=";")
        if new_file:
            w.writerow(["Наименование (как в закупке)", "Код ОКПД2", "Ссылка на закупку", "Сфера"])
        for i, (d, r, t) in enumerate(jobs, 1):
            key = f"{d}|{r}|{t}"
            if key in done:
                continue
            added = 0
            for url in soap_request(session, token, r, t, d, verify):
                data = download(session, token, url, verify)
                if not data:
                    continue
                z = zipfile.ZipFile(io.BytesIO(data))
                for xml_name in (n for n in z.namelist() if n.endswith(".xml")):
                    try:
                        number, objs = purchase_objects(z.read(xml_name))
                    except ET.ParseError:
                        continue
                    link = f"https://zakupki.gov.ru/epz/order/notice/{TYPES.get(t, 'ea20')}/view/common-info.html?regNumber={number}"
                    for name, code in objs[:PER_NOTICE]:
                        if (name, code) not in seen:
                            seen.add((name, code))
                            w.writerow([name, code, link, sphere(code)])
                            added += 1
            f.flush()
            fd.write(key + "\n"); fd.flush()
            print(f"[{i}/{len(jobs)}] {d} регион {r} {t}: +{added} позиций (всего {len(seen)})", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
