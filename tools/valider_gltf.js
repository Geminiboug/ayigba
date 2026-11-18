// Valide des fichiers .glb avec le validateur officiel Khronos (npm : gltf-validator).
// Le validateur est installé HORS du dépôt : cd /home/olympe/outils_valid && npm install gltf-validator
// Usage : node tools/valider_gltf.js projects/<projet>/out/neutre/carte.glb [autres.glb ...]
// Variable GLTF_VALIDATOR_DIR pour un autre emplacement.
const path = require('path');
const fs = require('fs');
const dir = process.env.GLTF_VALIDATOR_DIR || '/home/olympe/outils_valid';
const v = require(path.join(dir, 'node_modules', 'gltf-validator'));
(async () => {
  let echec = 0;
  for (const f of process.argv.slice(2)) {
    const r = await v.validateBytes(new Uint8Array(fs.readFileSync(f)), { uri: f, maxIssues: 0 });
    const i = r.issues;
    console.log(f, '| validateur', v.version(), '| erreurs', i.numErrors, '| avertissements', i.numWarnings, '| infos', i.numInfos, '| conseils', i.numHints);
    for (const m of i.messages) console.log('  ', m.severity, m.code, m.pointer, m.message);
    if (i.numErrors > 0) echec = 1;
  }
  process.exit(echec);
})();
