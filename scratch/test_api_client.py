# scratch/test_api_client.py
import json
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar


def run_client_test():
    print("=== DÉBUT DU TEST API FRONTEND-BACKEND (URLLIB CLIENT) ===")
    
    # Créateur d'opener HTTP gérant les cookies automatiquement
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    urllib.request.install_opener(opener)

    base_url = "http://127.0.0.1:8000/api/v1"

    # 1. Login en tant que Caissier
    print("\n1. Connexion en tant que caissier (caisse@gmail.com)...")
    login_data = json.dumps({
        "email": "caisse@gmail.com",
        "mot_de_passe": "caisse123"
    }).encode("utf-8")
    
    try:
        # Envoyer les identifiants en JSON
        req = urllib.request.Request(
            f"{base_url}/auth/login",
            data=login_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            print("[OK] Connexion réussie !")
            print("Message :", res_data.get("message"))
            print("Utilisateur connecté :", res_data.get("user", {}).get("prenom"))
            
            # Les cookies d'authentification (access_token) sont gérés automatiquement par le CookieJar
            auth_headers = {"Content-Type": "application/json"}
    except Exception as e:
        print("[ERROR] Échec de connexion :", e)
        return

    # 2. Récupérer la caisse active
    print("\n2. Récupération de la caisse active...")
    try:
        req = urllib.request.Request(f"{base_url}/caisses/principale", headers=auth_headers)
        with urllib.request.urlopen(req) as response:
            caisse = json.loads(response.read().decode("utf-8"))
            id_caisse = caisse.get("id_caisse")
            solde_initial = float(caisse.get("solde_physique", 0.0))
            print(f"[OK] Caisse active ID: {id_caisse}, Solde actuel: {solde_initial} USD")
    except Exception as e:
        print("[ERROR] Échec de récupération de la caisse :", e)
        return

    # 3. Créer un approvisionnement (Entrée de fonds de 500 USD)
    print("\n3. Création d'un mouvement d'approvisionnement de 500 USD...")
    mvt_data = json.dumps({
        "id_caisse": id_caisse,
        "type_mouvement": "ENTREE",
        "montant": 500.0,
        "motif": "Approvisionnement test client",
        "origine_type": "BANQUE",
        "origine_id": 12,
        "mode_reglement": "ESPECES",
        "beneficiaire": "Caisse Principale"
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{base_url}/caisse/mouvements",
            data=mvt_data,
            headers=auth_headers,
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            mouvement = json.loads(response.read().decode("utf-8"))
            id_mouvement = mouvement.get("id_mouvement")
            print(f"[OK] Mouvement créé ID: {id_mouvement}, Numéro: {mouvement.get('numero_piece')}, Statut: {mouvement.get('statut')}")
    except Exception as e:
        print("[ERROR] Échec de création du mouvement :", e)
        return

    # 4. Valider le mouvement (approvisionnement) par le caissier
    print(f"\n4. Validation du mouvement {id_mouvement} par le caissier...")
    try:
        req = urllib.request.Request(
            f"{base_url}/caisse/mouvements/{id_mouvement}/valider",
            data=b"",  # POST sans corps
            headers=auth_headers,
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            mvt_valide = json.loads(response.read().decode("utf-8"))
            print(f"[OK] Mouvement validé avec succès ! Nouveau statut: {mvt_valide.get('statut')}")
    except urllib.error.HTTPError as e:
        print("[ERROR] Échec de validation du mouvement (HTTPError) :", e)
        print("Response detail :", e.read().decode("utf-8"))
        return
    except Exception as e:
        print("[ERROR] Échec de validation du mouvement :", e)
        return

    # 5. Vérifier le nouveau solde de la caisse active
    print("\n5. Vérification du nouveau solde de la caisse...")
    try:
        req = urllib.request.Request(f"{base_url}/caisses/principale", headers=auth_headers)
        with urllib.request.urlopen(req) as response:
            caisse = json.loads(response.read().decode("utf-8"))
            solde_final = float(caisse.get("solde_physique", 0.0))
            print(f"[OK] Caisse ID: {id_caisse}, Nouveau solde: {solde_final} USD")
            assert solde_final == solde_initial + 500.0, "Le solde n'a pas augmenté de 500 USD !"
            print("\n=== TEST COMPLET RÉUSSI AVEC SUCCÈS ! ===")
    except Exception as e:
        print("[ERROR] Échec de vérification du solde :", e)
        return


if __name__ == "__main__":
    run_client_test()
