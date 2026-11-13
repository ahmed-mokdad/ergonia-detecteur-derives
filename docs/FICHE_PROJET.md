# Fiche projet (brouillon, une page)

**Nom** : Détecteur de dérives multifluides
**Équipe** : Ergonia — Ahmed, Ibrahima, Aziz, Fahd, Cédric
**Défi** : 4 · « Le détecteur de dérives »

**Réponse en une phrase** : un outil qui sépare d'abord les défauts de données des dérives, ne lève une alerte que si l'écart persiste une fois calendrier et météo retirés, puis classe les dérives en francs par mois avec, pour chacune, des causes à vérifier sur place.

**Ce qui est construit**
- Connecteurs de données avec liste blanche et empreintes SHA-256 (local, HTTP, emplacement API) : aucune donnée dans le dépôt ni dans l'app.
- Couche qualité : pas manquants (changement d'heure compris), doublons, échelle, valeur figée, contrôle physique du chauffage à distance, sources contradictoires de l'École du Centre.
- Détection : attendu journalier, CUSUM, persistance, double seuil, une alerte par cause et par site.
- Chiffrage kWh, CHF, CO₂ : constaté « au moins », borne prudente, projection à part, sans double compte.
- Causes et solutions : base de connaissances de dix signatures, indices pour et contre, fiche d'intervention exportable.
- Application Streamlit : Dérives, Causes et solutions, Qualité des données, Sites sains, Méthode et limites.

**Données** : jeux ouverts Rive-Claire (v2 mensuel, courbes électriques v1, fluides / PV / chauffage à distance v2, S04 v2), CC BY 4.0, Energ-IA Transition, Energ-IACK 2026. Température et rayonnement : MétéoSuisse, station Genève-Cointrin. Aucun jeu à accès restreint.

**Outils d'IA** : Claude Code (Claude Fable 5.2) pour écrire le code, les tests et la documentation sous la direction de l'équipe. Aucun LLM dans l'application : textes par gabarits, aucun chiffre généré par IA. Détail : `AI_USAGE.md`.

**Ce qui marche** : un détecteur qui n'utilise que le passé ; sur 2025, 9 dérives de contrôle sur 11 retrouvées (vérifiées après coup par le rapprochement avec le mensuel de l'année), 26 défauts de données classés à part ; une couche mensuelle sur tout le parc (102 séries : gaz de S22, COP de S09) ; 160 340 kWh de surplus constatés en 2025, 7,33 t de CO₂ direct, 16 966 CHF pour la seule électricité (seul prix donné par le jeu) ; 44 tests automatiques ; moteur figé en version 1.0.0.

**Ce qui ne marche pas encore** : 7 alertes sur 18 sont fausses, surtout aux changements de saison ; une dérive lente de 7 % et une dérive de gaz sont manquées, deux autres sont trouvées avec des mois de retard ; électricité et eau mensuelles 2021-2024 non rejouées ; causes non validées par un exploitant ; pas de LLM ; pas encore déployé en ligne.

**Ce que ça change** : l'exploitant ouvre une liste courte, triée par enjeu, avec la preuve et la première chose à vérifier, au lieu de centaines de courbes.

**Pour que la Ville le reprenne** : implémenter `ConnecteurAPI` sur sa télérelève, renseigner horaires et périodes de fermeture par site, faire valider les prix et la base de causes par ses exploitants. Code sous licence MIT.

**Lien du code** : à compléter (dépôt public à créer).
