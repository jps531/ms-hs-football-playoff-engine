// Runs the site's pure modules on JSON input, for backend/tests/unit/renderer_parity_test.py:
// the Python pre-renderer (static_pages.py) mirrors these functions, and that test checks the
// two give the same answers on the same input. Not a *.test.mjs, so `node --test` skips it.
//
// stdin:  [{ "module": "scenarios", "fn": "completeScenarioCards", "args": [...] }, ...]
// stdout: [result, ...] in the same order (Maps as objects, Sets as arrays).
// An argument { "$call": {...}, "index": n } is that call's result (its nth item, with index).

const plain = (value) => {
  if (value instanceof Map) return Object.fromEntries([...value].map(([k, v]) => [k, plain(v)]));
  if (value instanceof Set) return [...value].map(plain);
  if (Array.isArray(value)) return value.map(plain);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, plain(v)]));
  return value === undefined ? null : value;
};

// An argument may itself be a call, { "$call": { module, fn, args } }, for functions that take
// another function's output (roundPicks takes a column of treeColumns(bracketStructure(games))).
const modules = {};
async function call({ module, fn, args }) {
  modules[module] ??= await import(new URL(`../../html/static/js/${module}.js`, import.meta.url));
  const f = modules[module][fn];
  if (typeof f !== "function") throw new Error(`${module}.js has no export ${fn}`);
  return f(...(await Promise.all(args.map(resolve))));
}
async function resolve(arg) {
  if (arg && typeof arg === "object" && !Array.isArray(arg) && "$call" in arg) {
    const value = await call(arg.$call);
    return "index" in arg ? value[arg.index] : value;
  }
  return arg;
}

let input = "";
for await (const chunk of process.stdin) input += chunk;
const out = [];
for (const c of JSON.parse(input)) out.push(plain(await call(c)));
process.stdout.write(JSON.stringify(out));
