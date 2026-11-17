// NON TESTE : ecrit sans Unity sous la main, le 17/11/2026.
//
// Adaptateur Unity pour un dossier d'export Ayigba. Il ne fait que convertir :
// aucune logique de jeu.
//
// Prerequis : un paquet d'import glTF (par exemple glTFast, com.unity.cloud.gltfast).
// Sans lui, Unity ne sait pas lire carte.glb : le fichier est copie, mais aucun
// GameObject n'est cree et un avertissement est affiche.
//
// Reperes : glTF est main droite, Unity est main gauche. La conversion est faite
// par le paquet d'import ; ne rien inverser a la main (ni echelle negative, ni
// miroir). Unite : le metre, comme Unity.
//
// Installation : copier le dossier Editor dans Assets/ de votre projet.
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Ayigba
{
    [Serializable]
    public class AyigbaCouche
    {
        public string nom;
        public bool collision;
        public string contenu;
        public int triangles;
    }

    [Serializable]
    public class AyigbaRepere
    {
        public double origine_lon;
        public double origine_lat;
        public string unite;
        public string gltf;
    }

    [Serializable]
    public class AyigbaManifeste
    {
        public string generateur;
        public string projet;
        public string ville;
        public string quartier;
        public AyigbaRepere repere;
        public AyigbaCouche[] couches;
    }

    public static class AyigbaImporter
    {
        [MenuItem("Tools/Ayigba/Importer une carte...")]
        public static void ImporterCarte()
        {
            string dossier = EditorUtility.OpenFolderPanel("Dossier d'export Ayigba", "", "");
            if (string.IsNullOrEmpty(dossier)) return;
            Importer(dossier);
        }

        public static void Importer(string dossier)
        {
            string cheminManifeste = Path.Combine(dossier, "manifeste.json");
            string cheminGlb = Path.Combine(dossier, "carte.glb");
            if (!File.Exists(cheminManifeste) || !File.Exists(cheminGlb))
            {
                Debug.LogError("[Ayigba] manifeste.json ou carte.glb introuvable dans : " + dossier);
                return;
            }

            AyigbaManifeste manifeste;
            try
            {
                manifeste = JsonUtility.FromJson<AyigbaManifeste>(File.ReadAllText(cheminManifeste));
            }
            catch (Exception e)
            {
                Debug.LogError("[Ayigba] manifeste.json illisible : " + e.Message);
                return;
            }
            if (manifeste == null || manifeste.couches == null)
            {
                Debug.LogError("[Ayigba] manifeste.json ne contient pas de liste de couches.");
                return;
            }

            string projet = string.IsNullOrEmpty(manifeste.projet) ? "carte" : manifeste.projet;
            foreach (char c in Path.GetInvalidFileNameChars()) projet = projet.Replace(c, '_');

            string relDossier = "Assets/Ayigba/" + projet;
            Directory.CreateDirectory(Path.Combine(Application.dataPath, "Ayigba", projet));

            File.Copy(cheminGlb, Path.Combine(Application.dataPath, "Ayigba", projet, "carte.glb"), true);
            string cheminCredits = Path.Combine(dossier, "CREDITS.md");
            if (File.Exists(cheminCredits))
                File.Copy(cheminCredits, Path.Combine(Application.dataPath, "Ayigba", projet, "CREDITS.md"), true);
            else
                Debug.LogWarning("[Ayigba] CREDITS.md absent du dossier d'export : les credits restent obligatoires.");

            AssetDatabase.Refresh();

            string assetGlb = relDossier + "/carte.glb";
            GameObject modele = AssetDatabase.LoadAssetAtPath<GameObject>(assetGlb);
            if (modele == null)
            {
                Debug.LogWarning("[Ayigba] carte.glb a ete copie dans " + relDossier + " mais n'a pas pu etre charge comme GameObject. "
                    + "Installez un paquet d'import glTF (par exemple glTFast), puis relancez l'import.");
                return;
            }

            GameObject instance = PrefabUtility.InstantiatePrefab(modele) as GameObject;
            if (instance == null) instance = UnityEngine.Object.Instantiate(modele);
            instance.name = "Ayigba_" + projet;
            Undo.RegisterCreatedObjectUndo(instance, "Importer une carte Ayigba");

            int collisionneurs = 0;
            int couchesTrouvees = 0;
            foreach (AyigbaCouche couche in manifeste.couches)
            {
                if (!couche.collision) continue;
                Transform enfant = instance.transform.Find(couche.nom);
                if (enfant == null)
                {
                    Debug.LogWarning("[Ayigba] couche avec collision introuvable dans le modele : " + couche.nom);
                    continue;
                }
                couchesTrouvees++;
                foreach (MeshFilter mf in enfant.GetComponentsInChildren<MeshFilter>(true))
                {
                    if (mf.sharedMesh == null) continue;
                    MeshCollider mc = mf.gameObject.GetComponent<MeshCollider>();
                    if (mc == null) mc = mf.gameObject.AddComponent<MeshCollider>();
                    mc.sharedMesh = mf.sharedMesh;
                    collisionneurs++;
                }
            }

            Selection.activeGameObject = instance;
            Debug.Log("[Ayigba] Import termine : projet " + projet + ", " + manifeste.couches.Length + " couches, "
                + couchesTrouvees + " couches avec collision, " + collisionneurs + " MeshCollider ajoutes. "
                + "Les credits sont dans " + relDossier + "/CREDITS.md (a conserver).");
        }
    }
}
