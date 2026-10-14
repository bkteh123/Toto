// Generates prototype_scores_golden.json by running the ORIGINAL prototype's own scoring code
// (unchanged) on its embedded seed with the header line removed.
//
//   node gen_prototype_golden.js "<path to Royal Yellow 彩票分析器.html>" prototype_scores_golden.json
//
// Why the header is removed: the prototype's parser reads "date,n1,...,n6" as a draw
// 1-2-3-4-5-6 and so reports 123 draws; the real history is 122.
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const code = script.slice(0, script.indexOf("/* ---------- events ---------- */"));
const vals = { maxN: 45, pick: 6, skip: 0, w10: 40, w20: 25, w50: 20, w100: 15, mix: 50 };
const ctx = { document: { getElementById: id => ({ value: String(vals[id] ?? "") }) }, console, crypto: {}, Math };
vm.createContext(ctx);
vm.runInContext(code + "\nthis.__api = {parse, score, hyperStats, SEED};", ctx);
const { parse, score, hyperStats, SEED } = ctx.__api;
const pick = rows => rows.map(r => ({ n: r.n, cnt: r.cnt, gap: r.gap, rank: r.rank, hot: r.hot, cold: r.cold, comb: r.comb, cls: r.cls }));

// 1. what the prototype does with its own seed, header included
const shipped = parse(SEED);
const first = shipped.out[0];
console.log("shipped parse: draws =", shipped.out.length, "| bad =", shipped.bad, "| dated =", shipped.dated,
            "| first draw:", JSON.stringify({ label: first.label, nums: first.nums }));

// 2. clean data: the same seed without the header line
const clean = parse(SEED.split("\n").slice(1).join("\n")).out;
console.log("clean parse: draws =", clean.length);
const a = pick(score(shipped.out)), b = pick(score(clean));
let diffs = { cnt_windows: 0, gap: 0, rank: 0, hot: 0, cold: 0, comb: 0, cls: 0, all_count: 0 };
for (let i = 0; i < 45; i++) {
  const x = a[i], y = b[i];
  for (const p of ["10", "20", "50", "100"]) if (x.cnt[p] !== y.cnt[p]) diffs.cnt_windows++;
  if (x.cnt.all !== y.cnt.all) diffs.all_count++;
  if (x.gap !== y.gap) diffs.gap++; if (x.rank !== y.rank) diffs.rank++;
  if (Math.abs(x.hot - y.hot) > 1e-12) diffs.hot++; if (Math.abs(x.cold - y.cold) > 1e-12) diffs.cold++;
  if (Math.abs(x.comb - y.comb) > 1e-12) diffs.comb++; if (x.cls !== y.cls) diffs.cls++;
}
console.log("numbers (of 45) whose value differs, shipped(123) vs clean(122):", JSON.stringify(diffs));

// 3. golden values from CLEAN data
const result = { draws: clean.length, ending: pick(score(clean)), prefix: {}, hyper: hyperStats(45, 6) };
for (const T of [100, 60, 40, 12]) result.prefix[T] = pick(score(clean.slice(0, T)));
vals.w10 = 1; vals.w20 = 1; vals.w50 = 1; vals.w100 = 1; vals.mix = 30;
result.alt = { weights: [1, 1, 1, 1], mix: 0.3, rows: pick(score(clean)) };
fs.writeFileSync(process.argv[3], JSON.stringify(result));
console.log("golden written; hyper =", JSON.stringify(result.hyper));

