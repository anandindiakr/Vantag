// gen_zone_doc.js
// Generates Vantag_Zone_Configuration_Guide.docx using python-docx via Python subprocess

const { execSync } = require("child_process");
const path = require("path");

const dir = __dirname;
const pyScript = path.join(dir, "_gen_zone_doc_py.py");

console.log("Generating document via python-docx...");
const result = execSync(`python "${pyScript}"`, { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] });
console.log(result.trim());
