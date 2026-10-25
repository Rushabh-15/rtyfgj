// Fails when generated API types drift from the committed ones: `npm run check:types` in CI.
import { readFileSync, rmSync } from "node:fs";

const [committed, fresh] = process.argv.slice(2);
const same = readFileSync(committed, "utf8") === readFileSync(fresh, "utf8");
rmSync(fresh);
if (!same) {
  console.error(`${committed} is out of date: run \`npm run gen:types\` after \`windcast openapi\``);
  process.exit(1);
}
console.log(`${committed} matches the OpenAPI schema`);
