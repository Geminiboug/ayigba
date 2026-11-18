// NON TESTE DANS UNITY : ecrit sans Unity sous la main (18/11/2026). Ne pas presenter comme verifie.
//
// Equivalent Unity de adapters/godot/ayigba_carte.gd : charge les zones d'une carte ayigba autour d'une cible,
// les libere au loin, ajoute les collisions des couches qui en demandent, regle les niveaux de detail.
// Aucune logique de jeu.
//
// Contrat de donnees (zones.json dans le dossier d'export) :
//   emprise [ouest, sud, est, nord] en metres, repere local (x est, y nord) ; fichier "zones/z_00_00.glb" ;
//   couches [{nom, collision, visible: "toujours" | "pres" | "loin"}] ; distance_detail_m.
// Repere glTF des fichiers : X = est, Y = haut, Z = sud, metres.
//
// Prerequis : paquet glTFast (com.unity.cloud.gltfast, espace de noms GLTFast). Le dossier d'export doit etre
// lisible par chemin de fichier (par exemple copie dans StreamingAssets/ayigba/<projet>).
//
// Conversion de repere : glTFast convertit la main droite de glTF vers la main gauche d'Unity. Le SENS exact
// (quel axe est inverse) n'a PAS ete verifie ici : si la cible n'est pas au bon endroit, basculer `inverserX`.
using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using GLTFast;
using UnityEngine;

namespace Ayigba
{
    [Serializable] public class ZoneCouche { public string nom; public bool collision; public string visible; public int triangles; }

    [Serializable]
    public class ZoneInfo
    {
        public string nom;
        public string fichier;
        public float[] emprise;
        public ZoneCouche[] couches;
    }

    [Serializable]
    public class ZonesIndex
    {
        public float taille_zone_m;
        public float distance_detail_m = 350f;
        public ZoneInfo[] zones;
    }

    public class AyigbaCarte : MonoBehaviour
    {
        [Tooltip("Dossier d'export (contient zones.json et zones/). Chemin de fichier absolu ou relatif a StreamingAssets.")]
        public string dossier = "";
        public Transform cible;
        public float rayonChargement = 600f;
        public float margeLiberation = 150f;
        public bool toutCharger = false;
        public bool avecCollisions = true;
        [Tooltip("Hypothese non verifiee : glTFast inverse X en passant en main gauche.")]
        public bool inverserX = true;

        ZonesIndex _index;
        readonly Dictionary<string, GameObject> _zones = new Dictionary<string, GameObject>();
        readonly HashSet<string> _enCours = new HashSet<string>();
        float _attente;

        string Dossier => Path.IsPathRooted(dossier) ? dossier : Path.Combine(Application.streamingAssetsPath, dossier);

        async void Start()
        {
            string chemin = Path.Combine(Dossier, "zones.json");
            if (!File.Exists(chemin)) { Debug.LogError("[Ayigba] zones.json introuvable : " + chemin); return; }
            _index = JsonUtility.FromJson<ZonesIndex>(File.ReadAllText(chemin));
            if (_index == null || _index.zones == null) { Debug.LogError("[Ayigba] zones.json illisible"); return; }
            if (toutCharger)
                foreach (ZoneInfo z in _index.zones) await ChargerZone(z);
        }

        // Centre de la zone dans le repere Unity (voir l'avertissement sur inverserX).
        Vector3 Centre(ZoneInfo z)
        {
            float est = (z.emprise[0] + z.emprise[2]) * 0.5f;
            float nord = (z.emprise[1] + z.emprise[3]) * 0.5f;
            // glTF : X = est, Z = -nord ; Unity apres conversion par glTFast : X = -est (hypothese), Z = -nord
            return new Vector3(inverserX ? -est : est, 0f, -nord);
        }

        void Update()
        {
            if (toutCharger || cible == null || _index == null) return;
            _attente -= Time.deltaTime;
            if (_attente > 0f) return;
            _attente = 0.5f;
            Vector3 p = transform.InverseTransformPoint(cible.position);
            foreach (ZoneInfo z in _index.zones)
            {
                Vector3 c = Centre(z);
                float d = new Vector2(p.x - c.x, p.z - c.z).magnitude;
                if (d <= rayonChargement && !_zones.ContainsKey(z.nom) && !_enCours.Contains(z.nom))
                {
                    _ = ChargerZone(z);
                    return; // une zone par passage
                }
                if (d > rayonChargement + margeLiberation && _zones.ContainsKey(z.nom)) LibererZone(z.nom);
            }
        }

        public async Task ChargerZone(ZoneInfo z)
        {
            if (_zones.ContainsKey(z.nom) || !_enCours.Add(z.nom)) return;
            try
            {
                string chemin = Path.Combine(Dossier, z.fichier);
                var gltf = new GltfImport();
                if (!await gltf.Load(new Uri(chemin).AbsoluteUri))
                {
                    Debug.LogError("[Ayigba] zone illisible : " + chemin);
                    return;
                }
                var racine = new GameObject(z.nom);
                racine.transform.SetParent(transform, false);
                if (!await gltf.InstantiateMainSceneAsync(racine.transform))
                {
                    Debug.LogError("[Ayigba] instanciation impossible : " + chemin);
                    Destroy(racine);
                    return;
                }
                var parNom = new Dictionary<string, ZoneCouche>();
                foreach (ZoneCouche c in z.couches) parNom[c.nom] = c;

                foreach (MeshRenderer mr in racine.GetComponentsInChildren<MeshRenderer>(true))
                {
                    // glTFast peut nommer le GameObject d'apres le noeud (= la couche) ; sinon la couche est ignoree (avertissement).
                    if (!parNom.TryGetValue(mr.gameObject.name, out ZoneCouche c))
                    {
                        Debug.LogWarning("[Ayigba] couche inconnue dans " + z.nom + " : " + mr.gameObject.name);
                        continue;
                    }
                    if (avecCollisions && c.collision)
                    {
                        var mf = mr.GetComponent<MeshFilter>();
                        if (mf != null && mf.sharedMesh != null) mr.gameObject.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
                    }
                    // Niveaux de detail "pres"/"loin" : Unity n'a pas de plage de visibilite par objet comme Godot.
                    // On utilise un LODGroup a un seul niveau pour "pres" ; "loin" est active par distance dans MettreAJourDetail.
                    if (c.visible == "pres" || c.visible == "loin") _detail.Add((mr, c.visible == "pres"));
                }
                _zones[z.nom] = racine;
            }
            finally { _enCours.Remove(z.nom); }
        }

        readonly List<(MeshRenderer, bool)> _detail = new List<(MeshRenderer, bool)>();

        void LateUpdate()
        {
            if (cible == null || _index == null) return;
            float seuil = _index.distance_detail_m;
            _detail.RemoveAll(t => t.Item1 == null);
            foreach ((MeshRenderer mr, bool pres) in _detail)
            {
                float d = Vector3.Distance(mr.bounds.center, cible.position);
                // approximation : distance au centre de la boite du maillage de la couche dans la zone
                mr.enabled = pres ? d <= seuil : d > seuil;
            }
        }

        public void LibererZone(string nom)
        {
            if (!_zones.TryGetValue(nom, out GameObject go)) return;
            Destroy(go);
            _zones.Remove(nom);
        }

        public ICollection<string> ZonesChargees() => _zones.Keys;
    }
}
