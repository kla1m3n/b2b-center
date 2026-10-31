"""
Генерация текстов для ноутбука через GigaChat API вместо Qwen.

Делает те же два файла, что ноутбук делает с Qwen, в тех же форматах:
  * synth.csv                  — синтетические наименования для обучения (кеш SYNTH_CACHE);
  * okpd2_generated_raw.csv    — формулировки doc2query для индекса (кеш DOC2Q_CACHE).
Загрузите их в датасет Kaggle и укажите в константах ноутбука: тогда Qwen не загружается и генерация пропускается.

Запуск (на своём компьютере; нужен Python 3.10+):
    pip install requests pandas numpy
    $env:GIGACHAT_CREDENTIALS = Read-Host "Ключ"           (PowerShell; cmd: set ...; Linux/macOS: export ...)
    python tools/gigachat_generate.py --data kaggle_dataset --dry-run
    python tools/gigachat_generate.py --data kaggle_dataset --ca-bundle certs/russian_trusted_root_ca.pem --limit 20 --out gigachat_trial
    python tools/gigachat_generate.py --data kaggle_dataset --ca-bundle certs/russian_trusted_root_ca.pem

Ключ авторизации — в личном кабинете developers.sber.ru (проект GigaChat API → «Получить ключ»).
Ключ берётся только из переменной окружения (или вводится скрытно) и никуда не записывается.

Если запуск оборвался — запустите ту же команду ещё раз: готовые коды пропускаются, генерация продолжится.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import random
import re
import sys
import time
import uuid

import pandas as pd
import requests

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1"

# Отбор кодов, карточки кодов («не путать»), промпты и разбор ответа — общие с ноутбуком, из pp1875_core.py
SEED, SYNTH_MAX_CODES, SYNTH_PER_CODE, DOC2Q_PER_CODE, N_NEIGHBORS = 42, 6500, 8, 6, 4
ONE_CODE = "{code}\n{task}\nПо одному на строку, без нумерации и пояснений."
MANY_CODES = ("Коды ОКПД2:\n{codes}\n\nДля КАЖДОГО кода: {task}\n"
              'Ответ — только JSON-объект без пояснений: {{"<код>": ["...", "..."], ...}}')
core = None                                                      # pp1875_core из --data, загружается в load_docs


def parse_lines(txt: str) -> list[str]:
    return core.parse_lines(txt)


def load_docs(data: str):
    global core, SYSTEM, SYNTH_TASK, D2Q_TASK
    sys.path.insert(0, data)
    import pp1875_core                                          # тот же файл, что в датасете Kaggle
    core = pp1875_core
    SYSTEM, SYNTH_TASK, D2Q_TASK = core.SYSTEM_PROMPT, core.SYNTH_TASK, core.D2Q_TASK
    okpd = pd.read_csv(os.path.join(data, "okpd2.csv"), dtype=str, sep=None, engine="python", encoding="utf-8-sig")
    okpd.columns = [c.replace("\ufeff", "").strip().lower() for c in okpd.columns]
    leaf = okpd[okpd["is_leaf"].astype(str) == "1"]
    docs = pd.DataFrame({"code": leaf["code"].map(core.norm_code), "name": leaf["title"]})
    docs = docs.dropna(subset=["code"]).drop_duplicates("code").reset_index(drop=True)
    pp_df = pd.read_csv(os.path.join(data, "pp1875.csv"), dtype=str, encoding="utf-8-sig")
    pp = core.PPIndex(pp_df, "", "")
    docs["outcome"] = docs["code"].map(pp.outcome)
    return docs, core.NONE_KEY


def real_counts(data: str, leaves: set[str]) -> dict[str, int]:
    """Реальные пары на код — те же шаги, что в ноутбуке до REAL_COUNTS (КТРУ + синонимы)."""
    parts = []
    tp = os.path.join(data, "train_pairs.csv")
    if os.path.exists(tp):
        t = pd.read_csv(tp, dtype=str, encoding="utf-8-sig")
        parts.append(pd.DataFrame({"text": t["text"], "code": t["okpd2"].map(core.norm_code)}))
    sp = os.path.join(data, "okpd2_synonyms.csv")
    if os.path.exists(sp):
        t = pd.read_csv(sp, dtype=str, sep=";", encoding="utf-8-sig")
        parts.append(pd.DataFrame({"text": t["text"], "code": t["code"].map(core.norm_code)}).dropna())
    real = pd.concat(parts, ignore_index=True)
    real["text"] = real["text"].map(core.normalize_text)
    real = real.dropna(subset=["code", "text"])
    real = real[real["text"].str.len() > 2].drop_duplicates(["text", "code"])
    return core.real_pair_counts(real, leaves)


def synth_targets(docs, data: str, max_codes=SYNTH_MAX_CODES):
    """Тот же отбор, что в ноутбуке: коды ПП без реальных пар, их соседи вне ПП, остальные коды ПП, 10% случайных."""
    return core.synth_targets(docs, real_counts(data, set(docs["code"])), max_codes, SEED)


def code_cards(docs) -> dict[str, str]:
    return core.code_cards(docs, N_NEIGHBORS)


# ----------------------------------------------------------------------------- GigaChat REST API
class GigaChat:
    def __init__(self, credentials, scope, model, verify, oauth_url=OAUTH_URL, api_url=API_URL, timeout=120):
        self.cred, self.scope, self.model, self.verify = credentials, scope, model, verify
        self.oauth_url, self.api_url, self.timeout = oauth_url, api_url.rstrip("/"), timeout
        self.token, self.expires, self.tokens_used = None, 0.0, 0

    def _auth(self):
        r = requests.post(self.oauth_url, data={"scope": self.scope}, timeout=30, verify=self.verify,
                          headers={"Authorization": f"Basic {self.cred}", "RqUID": str(uuid.uuid4()),
                                   "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        if r.status_code != 200:
            raise RuntimeError(f"Авторизация не прошла: HTTP {r.status_code} {r.text[:300]}")
        j = r.json()
        self.token = j["access_token"]
        self.expires = j.get("expires_at", (time.time() + 1800) * 1000) / 1000   # мс -> с; токен живёт 30 мин

    def chat(self, user: str, temperature: float, max_tokens: int) -> str | None:
        """Ответ модели; None — запрос заблокирован фильтром тем или пустой ответ."""
        for attempt in range(7):
            if self.token is None or time.time() > self.expires - 60:
                self._auth()
            try:
                r = requests.post(f"{self.api_url}/chat/completions", timeout=self.timeout, verify=self.verify,
                                  headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                                  json={"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                                        "messages": [{"role": "system", "content": SYSTEM},
                                                     {"role": "user", "content": user}]})
            except requests.exceptions.SSLError:
                raise
            except requests.exceptions.RequestException as e:            # сеть: подождать и повторить
                wait = min(60, 2 ** attempt); print(f"  сеть: {e.__class__.__name__}, повтор через {wait} с"); time.sleep(wait)
                continue
            if r.status_code == 401:                                       # токен истёк раньше срока
                self.token = None; continue
            if r.status_code == 429 or r.status_code >= 500:               # лимит / сбой сервера
                wait = min(60, 2 ** attempt); print(f"  HTTP {r.status_code}, повтор через {wait} с"); time.sleep(wait)
                continue
            if r.status_code == 402:
                raise RuntimeError("HTTP 402: закончились токены выбранной модели (см. личный кабинет)")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            j = r.json()
            self.tokens_used += int(j.get("usage", {}).get("total_tokens", 0))
            ch = j["choices"][0]
            if ch.get("finish_reason") == "blacklist":
                return None
            return ch["message"]["content"]
        print("  запрос не удался после повторов — пропускаю")
        return None


def parse_json_answer(txt: str, codes: list[str]) -> dict[str, list[str]] | None:
    """{"код": [...]} из ответа модели (допускает ```json и текст вокруг). None — разобрать не удалось."""
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    out = {}
    for c in codes:
        v = obj.get(c)
        if isinstance(v, list):
            out[c] = parse_lines("\n".join(str(x) for x in v))
    return out or None


# ----------------------------------------------------------------------------- генерация с продолжением
def done_codes(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    return set(pd.read_csv(path, dtype=str)["code"].dropna())


def append_rows(path: str, rows: list[tuple[str, str, str]]):
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["text", "code", "source"])
        w.writerows(rows)


def generate(api: GigaChat, docs, codes, task, n, batch, source, out_path, max_tokens_per_code, temperature):
    card = code_cards(docs)
    have = done_codes(out_path)
    todo = [c for c in codes if c not in have]
    print(f"{source}: всего кодов {len(codes)}, готово {len(codes) - len(todo)}, осталось {len(todo)}")
    t0, done_n, rows_n = time.time(), 0, 0
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        got: dict[str, list[str]] = {}
        if len(part) > 1:                                                  # несколько кодов в одном запросе — JSON
            prompt = MANY_CODES.format(codes="\n".join(card[c] for c in part), task=task.format(n=n))
            got = parse_json_answer(api.chat(prompt, temperature, max_tokens_per_code * len(part)), part) or {}
        for c in part:                                                     # не разобралось — по одному коду
            if not got.get(c):
                txt = api.chat(ONE_CODE.format(code="Код ОКПД2 " + card[c], task=task.format(n=n)), temperature,
                               max_tokens_per_code)
                got[c] = parse_lines(txt or "")
        rows = [(t, c, source) for c in part for t in got.get(c, [])[:n]]
        rows += [("", c, source) for c in part if not got.get(c)]          # пустая строка = код обработан, ответа нет
        append_rows(out_path, rows)
        done_n += len(part); rows_n += len(rows)
        el = time.time() - t0
        eta = el / done_n * (len(todo) - done_n)
        print(f"  {done_n}/{len(todo)} кодов | строк {rows_n} | токенов {api.tokens_used:,} | "
              f"прошло {el / 60:.0f} мин, осталось ~{eta / 60:.0f} мин", flush=True)


def write_reuse(synth_path: str, d2q_path: str, docs) -> list[str]:
    """Как в ноутбуке: для кодов с синтетикой формулировки doc2query берутся из неё (до 6 на код)."""
    if not os.path.exists(synth_path):
        return []
    s = pd.read_csv(synth_path, dtype=str).dropna(subset=["text", "code"])
    s = s[s["code"].isin(set(docs["code"])) & (s["text"].str.len() > 0)]
    reuse = s[~s["code"].isin(done_codes(d2q_path))].groupby("code").head(DOC2Q_PER_CODE)  # ещё не перенесённые
    if len(reuse):
        append_rows(d2q_path, list(zip(reuse["text"], reuse["code"], ["generated"] * len(reuse))))
        print(f"doc2query: взято из синтетики {len(reuse)} строк для {reuse['code'].nunique()} кодов")
    return sorted(set(s["code"]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default="kaggle_dataset", help="папка с okpd2.csv, pp1875.csv, pp1875_core.py")
    p.add_argument("--out", default="gigachat_out", help="куда писать synth.csv и okpd2_generated_raw.csv")
    p.add_argument("--what", choices=["all", "synth", "doc2query"], default="all")
    p.add_argument("--model", default="GigaChat-2-Pro", help="GigaChat-2 (Lite, быстрее) | GigaChat-2-Pro | GigaChat-2-Max")
    p.add_argument("--scope", default="GIGACHAT_API_PERS", help="GIGACHAT_API_PERS (физлицо) | GIGACHAT_API_B2B | GIGACHAT_API_CORP")
    p.add_argument("--ca-bundle", default=None, help="файл сертификата НУЦ Минцифры (Russian Trusted Root CA)")
    p.add_argument("--batch-synth", type=int, default=3, help="кодов в одном запросе для синтетики")
    p.add_argument("--batch-d2q", type=int, default=8, help="кодов в одном запросе для doc2query")
    p.add_argument("--limit", type=int, default=0, help="только первые N кодов каждого вида (пробный запуск)")
    p.add_argument("--dry-run", action="store_true", help="только посчитать коды и примерный расход токенов")
    p.add_argument("--oauth-url", default=OAUTH_URL)
    p.add_argument("--api-url", default=API_URL)
    a = p.parse_args()

    docs, none_key = load_docs(a.data)
    os.makedirs(a.out, exist_ok=True)
    synth_path, d2q_path = os.path.join(a.out, "synth.csv"), os.path.join(a.out, "okpd2_generated_raw.csv")
    s_codes = synth_targets(docs, a.data)
    if a.limit:
        s_codes = s_codes[:a.limit]

    if a.dry_run:
        n_d2q = len(docs) - len(s_codes)
        tok = len(s_codes) * (200 + SYNTH_PER_CODE * 30) + n_d2q * (160 + DOC2Q_PER_CODE * 15)  # + соседи в промпте
        print(f"Синтетика: {len(s_codes)} кодов | doc2query: ~{n_d2q} кодов | всего ~{tok / 1e6:.1f} млн токенов "
              f"(оценка; бесплатно физлицу на 12 мес.: Lite 250 млн, Pro 40 млн, Max 25 млн)")
        return

    cred = os.environ.get("GIGACHAT_CREDENTIALS") or getpass.getpass("Ключ авторизации GigaChat (ввод скрыт): ")
    api = GigaChat(cred.strip(), a.scope, a.model, a.ca_bundle or True, a.oauth_url, a.api_url)
    try:
        if a.what in ("all", "synth"):
            generate(api, docs, s_codes, SYNTH_TASK, SYNTH_PER_CODE, a.batch_synth, "synth", synth_path, 450, 0.9)
        if a.what in ("all", "doc2query"):
            covered = write_reuse(synth_path, d2q_path, docs)
            d_codes = [c for c in docs["code"] if c not in set(covered)]
            if a.limit:
                d_codes = d_codes[:a.limit]
            generate(api, docs, d_codes, D2Q_TASK, DOC2Q_PER_CODE, a.batch_d2q, "generated", d2q_path, 160, 0.9)
    except requests.exceptions.SSLError as e:
        sys.exit(f"\nОшибка сертификата: {e}\nAPI GigaChat использует сертификат НУЦ Минцифры. Скачайте "
                 "«Russian Trusted Root CA» (страница сертификатов НУЦ на Госуслугах) и передайте файл через --ca-bundle.")
    except KeyboardInterrupt:
        sys.exit(f"\nОстановлено (токенов израсходовано: {api.tokens_used:,}). "
                 "Запустите ту же команду снова — генерация продолжится.")
    except RuntimeError as e:
        sys.exit(f"\n{e}\nТокенов израсходовано: {api.tokens_used:,}. Готовое сохранено, повторный запуск продолжит.")
    print(f"Израсходовано токенов в этом запуске: {api.tokens_used:,}")
    print(f"\nГотово: {a.out}/synth.csv и {a.out}/okpd2_generated_raw.csv.\n"
          "Загрузите их в датасет Kaggle и укажите SYNTH_CACHE = \"synth.csv\", DOC2Q_CACHE = \"okpd2_generated_raw.csv\".")


if __name__ == "__main__":
    main()
