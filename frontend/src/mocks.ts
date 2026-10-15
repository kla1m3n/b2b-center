// Заглушки API на время, пока backend не отдаёт /api/classify, /api/jobs, /api/npa.
// Позиции ПП и коды ОКПД2 взяты из data/npa/pp1875.json и data/okpd2.csv (ред. на 30.09.2026).
import type {
  ClassificationResult,
  HealthOut,
  JobOut,
  NpaItemDetails,
  NpaMatch,
  NpaVersion,
  Regime,
} from "./types";

const SOURCE_URL = "https://docs.cntd.ru/document/1310667825";
const REGIME_BY_APPENDIX: Record<number, Regime> = { 1: "ban", 2: "restriction", 3: "advantage" };
const REGIME_ORDER: Record<Regime, number> = { ban: 0, restriction: 1, advantage: 2, none: 3 };

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface MockItem {
  id: number;
  appendix: number;
  item_no: string;
  title: string;
  codes: string[];
  quota: number | null;
  note?: string;
  has_conditions?: boolean;
}

const ITEMS: MockItem[] = [
  { id: 10, appendix: 1, item_no: "10", title: "Бумага и картон", codes: ["17.12"], quota: null },
  { id: 3, appendix: 1, item_no: "3", title: "Одежда, кроме одежды из меха", codes: ["14.1"], quota: null },
  {
    id: 146, appendix: 1, item_no: "146", title: "Программа для электронной вычислительной машины и (или) базы данных",
    codes: ["58.2", "61", "62", "63", "64"], quota: null,
    note: "(Позиция в редакции, введенной в действие с 19 июня 2025 года постановлением Правительства Российской Федерации от 10 июня 2025 года N 879)",
  },
  { id: 156, appendix: 2, item_no: "1", title: "Щебень", codes: ["08.12.12.140"], quota: null },
  { id: 294, appendix: 2, item_no: "139", title: "Мебель для офисов и предприятий торговли", codes: ["31.01.1"], quota: null },
  {
    id: 350, appendix: 2, item_no: "195",
    title: "Компьютеры портативные массой не более 10 кг, такие как ноутбуки, планшетные компьютеры, карманные компьютеры, в том числе совмещающие функции мобильного телефонного аппарата, электронные записные книжки и аналогичная компьютерная техника",
    codes: ["26.20.11"], quota: null,
  },
  {
    id: 354, appendix: 2, item_no: "199",
    title: "Машины вычислительные электронные цифровые прочие, содержащие или не содержащие в одном корпусе одно или два из следующих устройств для автоматической обработки данных: запоминающие устройства, устройства ввода, устройства вывода",
    codes: ["26.20.15"], quota: null,
  },
  { id: 540, appendix: 2, item_no: "385", title: "Иглы хирургические; инструменты колющие; шприцы", codes: ["32.50.13.110", "21.20.24.120", "32.50.50.190"], quota: null },
  {
    id: 455, appendix: 2, item_no: "300",
    title: "Эндоскопические комплексы, соответствующие кодам 271710, 271720, 271740 вида медицинского изделия в соответствии с номенклатурной классификацией медицинских изделий",
    codes: ["26.60.11.113", "26.60.12.110", "32.50.1", "32.50.21.112"], quota: null, has_conditions: true,
  },
  { id: 626, appendix: 3, item_no: "1", title: "Щебень", codes: ["08.12.12.140"], quota: 80 },
  { id: 638, appendix: 3, item_no: "13", title: "Бумага и картон", codes: ["17.12"], quota: 90 },
  {
    id: 662, appendix: 3, item_no: "37",
    title: "Компьютеры портативные массой не более 10 кг, такие как ноутбуки, планшетные компьютеры, карманные компьютеры, в том числе совмещающие функции мобильного телефонного аппарата, электронные записные книжки и аналогичная компьютерная техника",
    codes: ["26.20.11"], quota: 80,
  },
  {
    id: 667, appendix: 3, item_no: "42",
    title: "Машины вычислительные электронные цифровые прочие, содержащие или не содержащие в одном корпусе одно или два из следующих устройств для автоматической обработки данных: запоминающие устройства, устройства ввода, устройства вывода",
    codes: ["26.20.15"], quota: 70,
  },
  { id: 768, appendix: 3, item_no: "143", title: "Лифты", codes: ["28.22.16.110", "28.22.18.150"], quota: 90 },
  { id: 857, appendix: 3, item_no: "232", title: "Мебель деревянная для офисов", codes: ["31.01.12"], quota: 75 },
];

interface Rule {
  words: string[];
  code: string;
  title: string;
  confidence: number;
  alternatives?: [string, string, number][];
}

// Порядок важен: первое совпадение по корню слова.
const RULES: Rule[] = [
  { words: ["ноутбук", "ноут"], code: "26.20.11.110", title: "Ноутбуки, в том числе портативные в защищенном исполнении, предназначенные для работы в сложной среде эксплуатации", confidence: 0.93,
    alternatives: [["26.20.11.130", "Планшетные компьютеры", 0.05]] },
  { words: ["системный блок", "компьютер", "пк"], code: "26.20.15.120", title: "Системные блоки", confidence: 0.88 },
  { words: ["бумаг"], code: "17.12.14.110", title: "Бумага для печати", confidence: 0.91,
    alternatives: [["17.12.14.160", "Бумага для плоттеров", 0.04]] },
  { words: ["щебен", "щебн"], code: "08.12.12.140", title: "Щебень", confidence: 0.97 },
  { words: ["халат", "куртк", "костюм", "одежд"], code: "14.12.30.131", title: "Халаты, фартуки, жилеты и сорочки мужские производственные и профессиональные", confidence: 0.68,
    alternatives: [["14.12.30.130", "Одежда производственная и профессиональная мужская прочая", 0.21]] },
  { words: ["тумб", "стол офис", "шкаф офис", "мебел"], code: "31.01.12.150", title: "Тумбы офисные деревянные", confidence: 0.72 },
  { words: ["катетер", "шприц", "игл"], code: "32.50.13.110", title: "Шприцы, иглы, катетеры, канюли и аналогичные инструменты", confidence: 0.54,
    alternatives: [["32.50.50.190", "Изделия медицинские, в том числе хирургические, прочие, не включенные в другие группировки", 0.3]] },
  { words: ["программ", "windows", "антивирус", "операционн"], code: "58.29.11.000", title: "Системы операционные на электронном носителе", confidence: 0.81 },
  { words: ["лифт"], code: "28.22.16.110", title: "Лифты", confidence: 0.86 },
  { words: ["хлеб", "батон"], code: "10.71.11.110", title: "Хлеб недлительного хранения", confidence: 0.9 },
];

const covers = (parent: string, code: string) => code.replace(/\./g, "").startsWith(parent.replace(/\./g, ""));

function matchItems(code: string): NpaMatch[] {
  return ITEMS.flatMap((it) => {
    const covering = it.codes.find((c) => covers(c, code));
    if (!covering) return [];
    return [{
      item_id: it.id,
      regime: REGIME_BY_APPENDIX[it.appendix],
      appendix: it.appendix,
      item_no: it.item_no,
      title: it.title,
      matched_code: covering,
      quota: it.quota,
      has_conditions: Boolean(it.has_conditions),
      note: it.note ?? "",
      source_url: SOURCE_URL,
    }];
  }).sort((a, b) => REGIME_ORDER[a.regime] - REGIME_ORDER[b.regime] || a.appendix - b.appendix);
}

function verdictOf(matches: NpaMatch[]): Regime {
  return matches.reduce<Regime>((v, m) => (REGIME_ORDER[m.regime] < REGIME_ORDER[v] ? m.regime : v), "none");
}

export function classifySync(name: string): ClassificationResult {
  const norm = name.toLowerCase().replace(/ё/g, "е").trim();
  if (!/[a-zа-я]{2,}/.test(norm)) {
    return { input: name, okpd2: null, alternatives: [], confidence: 0, needs_review: true, npa_matches: [], verdict: "none", explanation: "", error: "Пустое или нераспознанное наименование" };
  }
  const rule = RULES.find((r) => r.words.some((w) => norm.includes(w)));
  if (!rule) {
    return {
      input: name,
      okpd2: { code: "32.99.59.000", title: "Изделия различные прочие, не включенные в другие группировки" },
      alternatives: [
        { code: "22.29.29.190", title: "Изделия пластмассовые прочие, не включенные в другие группировки", confidence: 0.07 },
        { code: "25.99.29.190", title: "Изделия прочие из недрагоценных металлов, не включенные в другие группировки", confidence: 0.05 },
      ],
      confidence: 0.09,
      needs_review: true,
      npa_matches: [],
      verdict: "none",
      explanation: "Наиболее близкое наименование ОКПД2: «Изделия различные прочие, не включенные в другие группировки». Вердикт по ПП № 1875: не подпадает.",
      error: null,
    };
  }
  const matches = matchItems(rule.code);
  const verdict = verdictOf(matches);
  const labels: Record<Regime, string> = { ban: "запрет", restriction: "ограничение", advantage: "преимущество", none: "не подпадает" };
  return {
    input: name,
    okpd2: { code: rule.code, title: rule.title },
    alternatives: (rule.alternatives ?? []).map(([code, title, confidence]) => ({ code, title, confidence })),
    confidence: rule.confidence,
    needs_review: rule.confidence < 0.6,
    npa_matches: matches,
    verdict,
    explanation: `Наиболее близкое наименование ОКПД2: «${rule.title}». Вердикт по ПП № 1875: ${labels[verdict]}.`,
    error: null,
  };
}

export async function getHealth(): Promise<HealthOut> {
  await delay(150);
  return { status: "ok", db: true, models: true, npa_version: "ПП РФ № 1875 от 23.12.2024 (ред. на 30 сентября 2026 года)" };
}

export async function classify(name: string): Promise<ClassificationResult> {
  await delay(300);
  return classifySync(name);
}

// --- пакеты: имитация очереди Celery, ~150 мс на товар ---

interface MockJob {
  names: string[];
  startedAt: number;
}

const jobs = new Map<string, MockJob>();
let jobSeq = 0;

export async function classifyBatch(names: string[]): Promise<{ job_id: string }> {
  await delay(200);
  if (names.length > 100) throw new Error("Не более 100 товаров за один запрос");
  const id = `mock-${++jobSeq}`;
  jobs.set(id, { names, startedAt: Date.now() });
  return { job_id: id };
}

const DEMO_FILE_NAMES = [
  "Ноутбук Lenovo IdeaPad Slim 3 15.6\"",
  "Бумага офисная А4, 500 л.",
  "Стул офисный",
  "Щебень гранитный фр. 20-40",
  "Катетер уретральный (является медицинским изделием)",
];

export async function classifyFile(file: File): Promise<{ job_id: string }> {
  // В заглушке .csv/.txt читаем построчно; .xlsx разбирает только backend — подставляем демо-список.
  let names = DEMO_FILE_NAMES;
  if (/\.(csv|txt)$/i.test(file.name)) {
    const text = await file.text();
    names = text.split(/\r?\n/).map((l) => l.split(/[;\t]/)[0].trim()).filter((l) => l.length >= 3);
  }
  return classifyBatch(names);
}

export async function getJob(id: string): Promise<JobOut> {
  await delay(100);
  const job = jobs.get(id);
  if (!job) throw new Error("Задача не найдена");
  const done = Math.min(job.names.length, Math.floor((Date.now() - job.startedAt) / 150));
  const finished = done >= job.names.length;
  return {
    status: finished ? "done" : done === 0 ? "queued" : "running",
    total: job.names.length,
    done,
    results: finished ? job.names.map(classifySync) : null,
  };
}

// --- база НПА ---

const versions: NpaVersion[] = [
  { id: 1, title: "ПП РФ № 1875 от 23.12.2024 (ред. на 30 сентября 2026 года)", uploaded_at: "2026-10-14T09:00:00Z", status: "ready", is_active: true, items_count: 902, error: null },
];

export async function getNpaVersions(): Promise<NpaVersion[]> {
  await delay(200);
  // «Разбор» новой версии занимает 3 секунды, затем она становится активной
  for (const v of versions) {
    if (v.status === "parsing" && Date.now() - Date.parse(v.uploaded_at) > 3000) {
      v.status = "ready";
      v.items_count = 902;
      versions.forEach((o) => (o.is_active = o.id === v.id));
    }
  }
  return [...versions].sort((a, b) => b.id - a.id);
}

export async function uploadNpa(file: File, title: string): Promise<{ version_id: number }> {
  await delay(400);
  const id = Math.max(...versions.map((v) => v.id)) + 1;
  const broken = !/\.(json|xlsx|docx)$/i.test(file.name);
  versions.push({
    id,
    title: title || file.name,
    uploaded_at: new Date().toISOString(),
    status: broken ? "failed" : "parsing",
    is_active: false,
    items_count: 0,
    error: broken ? "Неподдерживаемый формат файла: нужен JSON, XLSX или DOCX" : null,
  });
  return { version_id: id };
}

export async function getNpaItem(id: number): Promise<NpaItemDetails> {
  await delay(150);
  const it = ITEMS.find((i) => i.id === id);
  if (!it) throw new Error("Позиция не найдена");
  const appendixName = { 1: "Перечень товаров, в отношении которых устанавливается запрет", 2: "Перечень товаров, в отношении которых устанавливается ограничение", 3: "Минимальная обязательная доля закупок российских товаров" }[it.appendix];
  return {
    id: it.id,
    appendix: it.appendix,
    item_no: it.item_no,
    title: it.title,
    codes: it.codes,
    quota: it.quota,
    note: it.note ?? "",
    raw_text: `Приложение № ${it.appendix} (${appendixName}), пункт ${it.item_no}.\n${it.title}\nКоды ОКПД2: ${it.codes.join(", ")}${it.quota ? `\nМинимальная доля: ${it.quota}%` : ""}`,
    source_url: SOURCE_URL,
  };
}
