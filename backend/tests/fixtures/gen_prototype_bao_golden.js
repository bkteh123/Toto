// Generates prototype_bao_golden.json by running the ORIGINAL prototype's own baoSet() and
// its rule-check loop (copied verbatim from buildBao) on its embedded seed, header removed.
//
//   node gen_prototype_bao_golden.js "<path to Royal Yellow 彩票分析器.html>" prototype_bao_golden.json
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const top = script.slice(0, script.indexOf("/* ---------- events ---------- */"));
const bao = script.slice(script.indexOf("function comb(n,k)"), script.indexOf("function fillBaoEnd"));
const vals = { maxN: 45, pick: 6, skip: 0, w10: 40, w20: 25, w50: 20, w100: 15, mix: 50 };
const ctx = { document: { getElementById: id => ({ value: String(vals[id] ?? "") }) }, console, Math };
vm.createContext(ctx);
vm.runInContext(top + "\n" + bao + "\nthis.__api = {parse, baoSet, comb, SEED};", ctx);
const { parse, baoSet, comb, SEED } = ctx.__api;
const draws = parse(SEED.split("\n").slice(1).join("\n")).out;      // 122 draws, header removed
const N = 45, K = 6, out = { draws: draws.length, cases: [] };
const pad = x => x;
for (const size of [5, 7, 8, 9, 10, 12, 15, 18])
  for (const win of [5, 10, 20])
    for (const end of [121, 100, 60, 30]) {
      const hist = draws.slice(0, end + 1);
      if (hist.length < win) continue;
      const b = baoSet(hist, size, win);
      // rule check, verbatim from buildBao
      let tot = 0, n = 0, dist = new Array(K + 1).fill(0);
      for (let t = win; t < draws.length; t++) {
        const s = new Set(baoSet(draws.slice(0, t), size, win).set);
        const h = draws[t].nums.filter(x => s.has(x)).length; tot += h; n++; dist[h]++;
      }
      const lines = size === 5 ? null : comb(size, K);
      out.cases.push({ size, win, end, set: b.set, cut: b.cut, tiedOut: b.tiedOut, sureIn: b.sureIn,
        cnt: Object.fromEntries(b.set.map(x => [x, b.cnt[x]])),
        rule: { n, avg: tot / n, exp: size * K / N, dist } });
    }
fs.writeFileSync(process.argv[3], JSON.stringify(out));
console.log("cases:", out.cases.length, "| draws:", out.draws);
const ref = out.cases.find(c => c.size === 8 && c.win === 10 && c.end === 121);
console.log("reference S=8 W=10 end=latest:", JSON.stringify({ set: ref.set, tiedOut: ref.tiedOut, rule: ref.rule }));
